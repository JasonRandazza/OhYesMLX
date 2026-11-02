"""Osaurus host-settings attestation.

Osaurus is the one runtime whose measured behaviour is not expressed in its start
command. ``osaurus serve --port 1337 --yes`` carries no model and no tuning flags;
everything that decides what a cell measures -- caching, concurrency, memory guards, KV
size, thread count -- lives in host-local files under ``~/.osaurus/config``. There are no
flags to pin, so this module attests instead: it reads the measurement-relevant keys, and
a recorded baseline lets the runtime refuse to start when the host has drifted away from
the configuration the baseline was taken under.

Ported from LMRE's ``osaurus_settings.py``; ``TRACKED_KEYS`` is unchanged.

**Scope, deliberately narrow.** This gates *drift*, not *correctness*. The baseline
records what the settings were, not what they ought to be. Notably the disk block cache
and the prefix cache are on by default, which is the same class of defect that made oMLX
get ``--no-cache`` pinned; deciding whether they should be off is a separate call this
module does not make.

**The pin, one definition for the harness and the app.** :func:`pin` copies both files
byte-exact into ``backup_dir``, applies the run's settings -- ``modelIdleResidencyPolicy.seconds
= 900`` and both caches off -- and records the baseline the drift guard reads. :func:`restore`
puts both files back and returns ``True`` only when each is byte-identical to its backup,
removing the backup on success; :func:`recover` is the same restore for a backup a crash left
behind, and a no-op without one. Every write here is a temp file in the same directory followed
by ``os.replace``, so a kill mid-write never leaves a half-written Osaurus config, and the
backup directory is created ``0700``. The shell runner (``scripts/osaurus-pin.sh``) calls these
functions rather than carrying its own copy of the edit.
"""

from __future__ import annotations

import filecmp
import json
import os
import sys
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".osaurus" / "config"

BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "osaurus-settings-baseline.json"
)

# The two host files `pin` backs up and edits: the caches live in one, the idle residency
# policy in the other. A backup of one without the other could not restore a host.
PIN_FILES = ("server-runtime.json", "server.json")

# The backup directory holds copies of the user's own settings, so nobody else gets to read it.
BACKUP_DIR_MODE = 0o700

# (file, dotted key path) for every setting that can move a measurement.
# Kept explicit rather than hashing whole files: Osaurus writes UI state, window sizes
# and appearance into the same directory, and drift there is noise.
TRACKED_KEYS: tuple[tuple[str, str], ...] = (
    ("server-runtime.json", "cache.blockDisk.enabled"),
    ("server-runtime.json", "cache.blockDisk.maxSizePercent"),
    ("server-runtime.json", "cache.prefix.enabled"),
    ("server-runtime.json", "cache.defaultMaxKVSize"),
    ("server-runtime.json", "cache.pagedKV.enabled"),
    ("server-runtime.json", "cache.storedKVCodec"),
    ("server-runtime.json", "cache.liveKVCodec"),
    ("server-runtime.json", "cache.longPromptMultiplier"),
    ("server-runtime.json", "concurrency.maxConcurrentSequences"),
    ("server-runtime.json", "concurrency.continuousBatching"),
    ("server-runtime.json", "memorySafety.mode"),
    ("server-runtime.json", "memorySafety.slider"),
    ("server-runtime.json", "mtp.mode"),
    ("server-runtime.json", "performance.compiledDecode"),
    ("server-runtime.json", "performance.tiedHeadCodec"),
    ("server-runtime.json", "generation.streamInterval"),
    ("server.json", "numberOfThreads"),
    ("server.json", "modelLoadRAMSoftThreshold"),
    ("server.json", "modelLoadRAMHardThreshold"),
    ("server.json", "modelEvictionPolicy"),
    ("server.json", "modelIdleResidencyPolicy.mode"),
    ("server.json", "modelIdleResidencyPolicy.seconds"),
    ("server.json", "backlog"),
)

MISSING = "<missing>"
UNREADABLE = "<unreadable>"


def _dig(payload: object, dotted: str) -> object:
    cursor = payload
    for part in dotted.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return MISSING
        cursor = cursor[part]
    return cursor


def capture_osaurus_settings(config_dir: Path | None = None) -> dict[str, object]:
    """Read the tracked Osaurus settings from *config_dir*.

    Never raises. A file that is absent or unparseable yields sentinel values for its
    keys, so an unreadable host is visibly unreadable rather than silently
    indistinguishable from a default one.
    """
    root = config_dir if config_dir is not None else DEFAULT_CONFIG_DIR
    documents: dict[str, object] = {}
    for filename in {name for name, _ in TRACKED_KEYS}:
        path = root / filename
        try:
            documents[filename] = json.loads(path.read_text())
        except (OSError, ValueError):
            documents[filename] = UNREADABLE

    settings: dict[str, object] = {}
    for filename, dotted in TRACKED_KEYS:
        document = documents[filename]
        key = f"{filename}:{dotted}"
        if document == UNREADABLE:
            settings[key] = UNREADABLE
        else:
            settings[key] = _dig(document, dotted)
    return settings


def load_baseline(path: Path | None = None) -> dict[str, object] | None:
    """Return the recorded baseline, or None when none has been recorded."""
    target = path if path is not None else BASELINE_PATH
    try:
        text = target.read_text()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError(f"invalid Osaurus baseline at {target}: {error}") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError(f"invalid Osaurus baseline at {target}: {error}") from error
    settings = payload.get("settings") if isinstance(payload, dict) else None
    if not isinstance(settings, dict):
        raise ValueError(f"invalid Osaurus baseline at {target}: missing settings object")
    return settings


def write_baseline(
    path: Path | None = None,
    config_dir: Path | None = None,
) -> dict[str, object]:
    """Record the host's current settings as the baseline, and return them."""
    target = path if path is not None else BASELINE_PATH
    settings = capture_osaurus_settings(config_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"settings": settings}, indent=2, sort_keys=True) + "\n")
    return settings


def _read_object(path: Path) -> dict:
    """One Osaurus config as a JSON object, or ``ValueError`` naming the file."""
    try:
        text = path.read_text()
    except OSError as error:
        raise ValueError(f"cannot read the Osaurus config {path}: {error}") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError(f"the Osaurus config {path} is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"the Osaurus config {path} does not hold a JSON object")
    return payload


def _write_atomic(target: Path, data: bytes) -> None:
    """Replace *target*'s bytes through a temp file in its own directory.

    A kill between the write and the ``os.replace`` leaves the original file exactly as it
    was, and the temp is removed rather than left beside it: a half-written Osaurus config
    is a host that will not start, and a leftover ``.pin-tmp`` is a file nobody would
    recognise as stale.
    """
    temporary = target.with_name(target.name + ".pin-tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            # The replace installs the temp's mode too, and the user's own file mode is not
            # this module's to change.
            os.chmod(temporary, target.stat().st_mode & 0o7777)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _backups(backup_dir: Path) -> list[Path]:
    """The backups present in *backup_dir*, in the pin's own file order."""
    return [path for name in PIN_FILES if (path := backup_dir / name).exists()]


def _log(action: str, outcome: str, files: list[Path], backup_dir: Path) -> None:
    """One JSON line per pin or restore: the files and the outcome, never their contents."""
    print(
        json.dumps(
            {
                "action": action,
                "outcome": outcome,
                "files": [str(path) for path in files],
                "backup_dir": str(backup_dir),
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def pin(
    config_dir: Path | None = None,
    *,
    backup_dir: Path,
    baseline_path: Path | None = None,
) -> None:
    """Pin Osaurus's measurement-relevant host settings, backing the originals up first.

    Both ``PIN_FILES`` are copied byte-exact into *backup_dir* (created ``0700``, refused if a
    backup is already there, because overwriting it would destroy the only copy of the user's
    own settings), then ``cache.prefix.enabled`` and ``cache.blockDisk.enabled`` are set false
    and ``modelIdleResidencyPolicy.seconds`` to 900, and the baseline the drift guard reads is
    written to *baseline_path* -- ``BASELINE_PATH`` by default, which is the harness's copy in
    the repo; the app passes its own.

    Both configs are parsed before either is replaced, so an unreadable file leaves its
    neighbour untouched, and every write is atomic.
    """
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    backups = Path(backup_dir)
    baseline = (
        Path(baseline_path) if baseline_path is not None else BASELINE_PATH
    )

    existing = _backups(backups)
    if existing:
        raise ValueError(
            f"refusing to pin Osaurus settings: {backups} already holds a backup "
            f"({', '.join(path.name for path in existing)}); restore it, or call "
            "osaurus_settings.recover, rather than overwriting the user's original settings"
        )
    sources = [Path(root) / name for name in PIN_FILES]
    missing = [path for path in sources if not path.exists()]
    if missing:
        raise ValueError(
            "refusing to pin Osaurus settings: "
            f"{', '.join(str(path) for path in missing)} does not exist"
        )

    runtime = _read_object(sources[0])
    server = _read_object(sources[1])

    backups.mkdir(parents=True, exist_ok=True)
    os.chmod(backups, BACKUP_DIR_MODE)
    for source in sources:
        _write_atomic(backups / source.name, source.read_bytes())

    runtime.setdefault("cache", {}).setdefault("prefix", {})["enabled"] = False
    runtime["cache"].setdefault("blockDisk", {})["enabled"] = False
    server.setdefault("modelIdleResidencyPolicy", {})["seconds"] = 900
    _write_atomic(sources[0], json.dumps(runtime, indent=2).encode())
    _write_atomic(sources[1], json.dumps(server, indent=2).encode())

    write_baseline(baseline, root)
    _log("pin", "pinned", sources, backups)


def _put_back(root: Path, backups: Path, present: list[Path], *, action: str) -> bool:
    """Copy each backup back, verify it byte-exact, and remove the backups only when they match."""
    restored = [Path(root) / backup.name for backup in present]
    for backup, target in zip(present, restored):
        _write_atomic(target, backup.read_bytes())
    mismatched = [
        target
        for backup, target in zip(present, restored)
        if not filecmp.cmp(target, backup, shallow=False)
    ]
    if mismatched:
        _log(
            action,
            "not byte-identical, so the backup is kept: "
            + ", ".join(str(path) for path in mismatched),
            restored,
            backups,
        )
        return False
    for backup in present:
        backup.unlink()
    try:
        backups.rmdir()
    except OSError:
        pass  # something else is in the directory; the backups themselves are gone
    _log(action, "restored byte-exact", restored, backups)
    return True


def restore(config_dir: Path | None = None, *, backup_dir: Path) -> bool:
    """Put both config files back from *backup_dir*; ``True`` only when each is byte-exact.

    ``False`` leaves the backup in place, so a restore that did not take effect can be
    retried or examined rather than reported as done. A directory holding no backup at all
    raises: unlike :func:`recover`, a caller that asks to restore has said a backup exists.
    """
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    backups = Path(backup_dir)
    present = _backups(backups)
    if not present:
        raise ValueError(
            f"refusing to restore Osaurus settings: {backups} holds no backup to restore"
        )
    return _put_back(root, backups, present, action="restore")


def recover(config_dir: Path | None = None, *, backup_dir: Path) -> bool:
    """Restore a backup that a crash between pin and restore left behind.

    ``True`` when a leftover backup was put back byte-exact and removed, ``False`` when there
    was nothing to recover -- the ordinary case, and deliberately not an error: this runs at
    launch and before a pin. A restore that does not verify keeps the backup and returns
    ``False`` exactly as :func:`restore` does.
    """
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    backups = Path(backup_dir)
    present = _backups(backups)
    if not present:
        return False
    return _put_back(root, backups, present, action="recover")


def diff_against_baseline(
    settings: dict[str, object],
    baseline: dict[str, object],
) -> tuple[tuple[str, object, object], ...]:
    """Return ``(key, baseline_value, captured_value)`` for every difference.

    Keys present in only one side are reported with ``MISSING`` on the other, so a
    baseline written by an older version of this module surfaces rather than being
    silently skipped.
    """
    drift: list[tuple[str, object, object]] = []
    for key in sorted(set(baseline) | set(settings)):
        expected = baseline.get(key, MISSING)
        actual = settings.get(key, MISSING)
        if expected != actual:
            drift.append((key, expected, actual))
    return tuple(drift)


def describe_drift(drift: tuple[tuple[str, object, object], ...]) -> str:
    """One human-readable line per drifted key."""
    return "\n".join(
        f"  {key}: baseline {expected!r}, host {actual!r}"
        for key, expected, actual in drift
    )
