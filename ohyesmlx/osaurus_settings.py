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

**The pin, one definition for the harness and the app.** :func:`pin` copies both files and the
baseline the drift guard reads byte-exact into ``backup_dir`` -- or a ``baseline.absent`` marker
when no baseline exists, so a restore removes the one the pin wrote instead of leaving a gate
where there was none -- applies the run's settings (``modelIdleResidencyPolicy.seconds = 900``
and both caches off), and records the baseline. :func:`restore` puts all three back and returns
``True`` only when each is byte-identical to its backup, removing the backups on success;
:func:`recover` is the same restore for a backup a crash left behind, and a no-op without one.
Every write here is a temp file in the same directory followed by ``os.replace``, so a kill
mid-write never leaves a half-written file, and the backup directory is created ``0700``. The
shell runner (``scripts/osaurus-pin.sh``) calls these functions rather than carrying its own
copy of the edit.
"""

from __future__ import annotations

import filecmp
import json
import os
import plistlib
import sys
from pathlib import Path

from ohyesmlx import app_support_dir, writable_root

DEFAULT_CONFIG_DIR = Path.home() / ".osaurus" / "config"

# The drift guard's baseline: beside the package in a checkout, under Application Support in
# an installed app. `writable_root` is the one definition of which of the two this is.
BASELINE_PATH = writable_root() / "config" / "osaurus-settings-baseline.json"

# The app's own preferences, where Osaurus keeps per-model options that no config file and no
# start command shows: `model_options_<model id>` holds a JSON blob whose `options` carry
# `disableThinking` (and, for some models, `reasoningEffort`). The thinking switch decides
# whether the served model emits a reasoning run at all, so it is attested per model (Fable
# S5-F9, Jason 2026-11-16). docs/runtimes/osaurus.md section 3.6 has the decoded shape.
# ponytail: reads the plist file, not cfprefsd; a just-toggled switch can lag until the app
# flushes it. Upgrade: `defaults export com.dinoki.osaurus -` if that lag is ever seen.
PREFERENCES_PLIST = Path.home() / "Library" / "Preferences" / "com.dinoki.osaurus.plist"
MODEL_OPTIONS_PREFIX = "model_options_"

# The two host files `pin` backs up and edits: the caches live in one, the idle residency
# policy in the other. A backup of one without the other could not restore a host.
PIN_FILES = ("server-runtime.json", "server.json")

# The baseline belongs to the backup set too: every pin overwrites it, so a copy is what puts
# the guard's gate back byte-exact. The marker records that there was no baseline to copy, and
# a restore of it deletes the one the pin wrote rather than leaving a gate where there was none.
BASELINE_BACKUP = "baseline.json"
BASELINE_ABSENT = "baseline.absent"

# The backup directory holds copies of the user's own settings, so nobody else gets to read it.
BACKUP_DIR_MODE = 0o700

# The one backup location, defined once and used by every caller: the shell wrapper
# (scripts/osaurus-pin.sh), quickbench and the app's launch recovery. Two locations is how a
# crashed shell pin's originals became invisible to the app, which then copied the *pinned*
# files as the user's own and reported them restored (Fable S5-F6). Beside the host config, so
# it sits next to the files it is a copy of and outside the directory Osaurus itself rewrites.
BACKUP_DIR = DEFAULT_CONFIG_DIR.with_name("config.ohyesmlx-backup")

# Where earlier versions kept the same backup, each with its own caller:
#   <config dir>.phase4-orig -- scripts/osaurus-pin.sh before 05-12, a sibling of the config
#                              directory it pinned, which is why it is derived from that root
#                              rather than hard-coded: a scratch config dir gets its own.
#   <app support>/quickbench/osaurus-backup -- quickbench's DEFAULT_BACKUP_DIR before 05-12.
# Recovery reads them so a backup a crash left in one is not stranded, and pin refuses over
# any of them. A function rather than a constant so a patched HOME or app-support directory is
# seen (app_support_dir answers about the home at call time), and so the list is one definition
# instead of a copy per caller.
def legacy_backup_dirs(config_dir: Path | None = None) -> tuple[Path, ...]:
    """The backup directories earlier versions used, for *config_dir*'s host."""
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    return (
        root.with_name("config.phase4-orig"),
        app_support_dir() / "quickbench" / "osaurus-backup",
    )

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
    ("server-runtime.json", "concurrency.smeltMode"),
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

# The three tracked keys `pin` sets, and their pinned values. One definition: the pin writes
# them to the host and the baseline records them, so the two cannot disagree about what was
# pinned or to what.
PINNED_KEYS: dict[str, object] = {
    "server-runtime.json:cache.blockDisk.enabled": False,
    "server-runtime.json:cache.prefix.enabled": False,
    "server.json:modelIdleResidencyPolicy.seconds": 900,
}


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


def capture_model_options(plist_path: Path | None = None) -> dict[str, object] | str:
    """Every model's per-model options from the app plist, keyed by model id.

    Never raises. No plist is no options (``{}``: the app has saved none); a plist that
    cannot be read is :data:`UNREADABLE`, and one model whose blob does not decode is
    :data:`UNREADABLE` for that model alone.
    """
    path = plist_path if plist_path is not None else PREFERENCES_PLIST
    try:
        payload = plistlib.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, plistlib.InvalidFileException):
        return UNREADABLE
    options: dict[str, object] = {}
    for key, blob in payload.items():
        if not isinstance(key, str) or not key.startswith(MODEL_OPTIONS_PREFIX):
            continue
        try:
            decoded = json.loads(blob)
            options[key[len(MODEL_OPTIONS_PREFIX):]] = decoded.get("options", MISSING)
        except (TypeError, ValueError, AttributeError):
            options[key[len(MODEL_OPTIONS_PREFIX):]] = UNREADABLE
    return options


def model_options_for(model_id: str, captured: dict[str, object] | str) -> object:
    """One model's entry in a :func:`capture_model_options` result, with the sentinels."""
    if not isinstance(captured, dict):
        return captured
    return captured.get(model_id, MISSING)


def load_baseline_model_options(path: Path | None = None) -> dict[str, object] | str | None:
    """The per-model options recorded with the baseline; ``None`` when there is no baseline.

    A baseline recorded before model options were attested has no such object, and that is
    returned as :data:`MISSING` rather than as "no options": the gate cannot vouch for a
    switch the baseline never saw.
    """
    payload = _load_baseline_payload(path)
    if payload is None:
        return None
    return payload.get("model_options", MISSING)


def load_baseline(path: Path | None = None) -> dict[str, object] | None:
    """Return the recorded baseline, or None when none has been recorded."""
    payload = _load_baseline_payload(path)
    return None if payload is None else payload["settings"]


def _load_baseline_payload(path: Path | None = None) -> dict | None:
    """The whole baseline document, validated, or None when none has been recorded."""
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
    return payload


def write_baseline(
    path: Path | None = None,
    config_dir: Path | None = None,
) -> dict[str, object]:
    """Record the host's current settings as the baseline, and return them.

    This is the ``rebaseline=True`` rule -- the live host, recorded whole -- and it stays the
    definition of it: :func:`pin` and :func:`set_key` call it rather than copying it.
    """
    target = path if path is not None else BASELINE_PATH
    settings = capture_osaurus_settings(config_dir)
    document = {"settings": settings, "model_options": capture_model_options()}
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(target, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode())
    return settings


def _record_baseline(
    path: Path,
    config_dir: Path | None,
    overrides: dict[str, object],
    *,
    rebaseline: bool,
) -> dict[str, object]:
    """Write the baseline under the rule in :func:`pin`'s docstring, and return it.

    ``rebaseline=True`` records the live host whole (:func:`write_baseline`). ``False`` keeps
    an existing baseline and replaces only *overrides* in it, never reading the live host for
    any other key -- that is what leaves the drift gate something to compare against. With no
    baseline yet there is nothing to keep, so the live host is recorded, which is the only
    honest answer: the gate cannot attest conditions that were never written down.
    """
    if rebaseline:
        return write_baseline(path, config_dir)
    try:
        existing = _load_baseline_payload(path)
    except ValueError:
        # An unreadable baseline cannot be edited in place, and silently replacing it would
        # destroy the only record of the conditions earlier runs were measured under.
        raise
    if existing is None:
        return write_baseline(path, config_dir)
    settings = dict(existing["settings"])
    settings.update(overrides)
    document = {
        "settings": settings,
        "model_options": existing.get("model_options", MISSING),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode())
    return settings


def set_key(
    key: str,
    value: object,
    *,
    config_dir: Path | None = None,
    baseline_path: Path | None = None,
) -> object:
    """Set one ``file:dotted`` host key atomically, read it back, and record the baseline.

    The shell wrapper's ``osaurus_set_seqs`` is the caller: a concurrency sweep needs
    ``concurrency.maxConcurrentSequences`` set to its own N on a host that takes no such flag.
    The edit is :func:`_write_atomic`'s -- the same temp-and-replace :func:`pin` uses on the
    same file -- so a kill mid-write leaves the user's config whole rather than truncated
    (Fable S5-F12). The value is written before anything reads it back, and a read-back that
    does not match raises rather than leaving a baseline that describes a host nobody has.

    The baseline is recorded under :func:`pin`'s rule with this one key overridden, so the
    drift gate still holds every other tracked key to the conditions the run was pinned under.
    Returns the value read back.
    """
    filename, _separator, dotted = key.partition(":")
    if not dotted:
        raise ValueError(
            f"refusing to set an Osaurus key: {key!r} is not 'file:dotted.key'"
        )
    if filename not in PIN_FILES:
        raise ValueError(
            f"refusing to set an Osaurus key in {filename!r}: only {', '.join(PIN_FILES)} "
            "are the host files this module owns"
        )
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    target = root / filename
    baseline = Path(baseline_path) if baseline_path is not None else BASELINE_PATH

    document = _read_object(target)
    _set_by_path(document, dotted, value)
    _write_atomic(target, json.dumps(document, indent=2).encode())

    read_back = capture_osaurus_settings(root)[key]
    if read_back != value:
        raise ValueError(
            f"osaurus_set_seqs: {key} reads back {read_back!r}, not {value!r}"
        )
    _record_baseline(baseline, root, {key: value}, rebaseline=False)
    return read_back


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


def _set_by_path(document: dict, dotted: str, value: object) -> None:
    """Set *dotted* in *document*, creating the objects on the way."""
    cursor = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        if not isinstance(cursor.get(part), dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value


def _backups(backup_dir: Path) -> list[Path]:
    """The backups present in *backup_dir*, in the pin's own file order."""
    return [
        path
        for name in (*PIN_FILES, BASELINE_BACKUP, BASELINE_ABSENT)
        if (path := backup_dir / name).exists()
    ]


def backup_dirs_holding(
    config_dir: Path | None = None, *, backup_dir: Path | None = None
) -> list[Path]:
    """Every backup location that holds a backup, the caller's first and then the legacy ones.

    One definition of "where a backup could be", so :func:`pin`'s refusal, :func:`recover`'s
    search and the app's launch message cannot disagree about it. Duplicates are dropped: the
    caller's directory is often one of the legacy ones, and the same backup counted twice
    would read as the two-directory ambiguity recovery refuses over.
    """
    locations: list[Path] = []
    if backup_dir is not None:
        locations.append(Path(backup_dir))
    for location in legacy_backup_dirs(config_dir):
        if location not in locations:
            locations.append(location)
    return [location for location in locations if _backups(location)]


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
    rebaseline: bool = False,
) -> dict[str, object]:
    """Pin Osaurus's measurement-relevant host settings, backing the originals up first.

    Both ``PIN_FILES`` and the baseline at *baseline_path* are copied byte-exact into
    *backup_dir* (created ``0700``, refused while a backup is already there in this directory or
    either legacy one, because overwriting it would destroy the only copy of the user's own
    settings); with no baseline there, a ``baseline.absent`` marker is written instead. Then
    ``cache.prefix.enabled`` and ``cache.blockDisk.enabled`` are set false and
    ``modelIdleResidencyPolicy.seconds`` to 900, and the baseline the drift guard reads is
    written to *baseline_path* -- ``BASELINE_PATH`` by default, which is the harness's copy in
    the repo; the app passes its own.

    *rebaseline* decides what that baseline is. ``False`` -- the harness default, and what
    ``scripts/osaurus-pin.sh`` and a CLI run get -- keeps a baseline that already exists and
    overrides only the three keys this function pins, so a host that differs from the committed
    baseline on any other tracked key is still caught by ``check_host_state``. Re-recording the
    live host here is what made the drift gate compare the host with itself for the whole
    pinned run (Fable S5-F8). ``True`` -- quickbench, because another Mac has no committed
    baseline and today's live host is the only thing there is -- records the live host exactly
    as this function always did.

    Returns the settings that were recorded as the baseline, which is the condition record a
    caller writes beside its results; the app keeps it as ``summary["osaurus"]["snapshot"]``.
    One capture serves both, so the recorded snapshot and what the gate checks are the same
    values rather than two reads of a host that may have moved between them.

    Both configs are parsed before either is replaced, so an unreadable file leaves its
    neighbour untouched, and every write is atomic.
    """
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    backups = Path(backup_dir)
    baseline = (
        Path(baseline_path) if baseline_path is not None else BASELINE_PATH
    )

    held = backup_dirs_holding(root, backup_dir=backups)
    if held:
        raise ValueError(
            "refusing to pin Osaurus settings: "
            + "; ".join(
                f"{location} already holds a backup "
                f"({', '.join(path.name for path in _backups(location))})"
                for location in held
            )
            + "; restore it, or call osaurus_settings.recover, rather than overwriting the "
            "user's original settings"
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
    if baseline.exists():
        _write_atomic(backups / BASELINE_BACKUP, baseline.read_bytes())
    else:
        _write_atomic(backups / BASELINE_ABSENT, b"")

    documents = {source.name: document for source, document in zip(sources, (runtime, server))}
    for key, value in PINNED_KEYS.items():  # the one definition of what a pin sets
        filename, _separator, dotted = key.partition(":")
        _set_by_path(documents[filename], dotted, value)
    _write_atomic(sources[0], json.dumps(runtime, indent=2).encode())
    _write_atomic(sources[1], json.dumps(server, indent=2).encode())

    recorded = _record_baseline(baseline, root, PINNED_KEYS, rebaseline=rebaseline)
    _log("pin", "pinned", [*sources, baseline], backups)
    return recorded


def _put_back(
    root: Path,
    backups: Path,
    present: list[Path],
    *,
    baseline: Path,
    action: str,
) -> bool:
    """Copy each backup back, verify it byte-exact, and remove the backups only when they match.

    The two configs go back to *root* and the baseline to *baseline*; a ``baseline.absent``
    marker deletes the baseline the pin wrote and verifies that it is gone. Every backup is
    kept on any mismatch, so a retry still has the original bytes.
    """
    restored: list[tuple[Path, Path]] = []
    for backup in present:
        if backup.name == BASELINE_ABSENT:
            baseline.unlink(missing_ok=True)
            restored.append((backup, baseline))
            continue
        target = baseline if backup.name == BASELINE_BACKUP else root / backup.name
        _write_atomic(target, backup.read_bytes())
        restored.append((backup, target))
    mismatched = []
    for backup, target in restored:
        if backup.name == BASELINE_ABSENT:
            if target.exists():
                mismatched.append(target)
        elif not filecmp.cmp(target, backup, shallow=False):
            mismatched.append(target)
    files = [target for _backup, target in restored]
    if mismatched:
        _log(
            action,
            "not byte-identical, so the backup is kept: "
            + ", ".join(str(path) for path in mismatched),
            files,
            backups,
        )
        return False
    for backup in present:
        backup.unlink()
    try:
        backups.rmdir()
    except OSError:
        pass  # something else is in the directory; the backups themselves are gone
    _log(action, "restored byte-exact", files, backups)
    return True


def restore(
    config_dir: Path | None = None,
    *,
    backup_dir: Path,
    baseline_path: Path | None = None,
) -> bool:
    """Put every backed-up file back from *backup_dir*; ``True`` only when each is byte-exact.

    The two configs go back to *config_dir* and the baseline to *baseline_path* --
    ``BASELINE_PATH`` by default -- with a ``baseline.absent`` marker deleting the baseline the
    pin wrote. ``False`` leaves the backups in place, so a restore that did not take effect can
    be retried or examined rather than reported as done. A directory holding no backup at all
    raises: unlike :func:`recover`, a caller that asks to restore has said a backup exists.
    """
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    backups = Path(backup_dir)
    baseline = Path(baseline_path) if baseline_path is not None else BASELINE_PATH
    present = _backups(backups)
    if not present:
        raise ValueError(
            f"refusing to restore Osaurus settings: {backups} holds no backup to restore"
        )
    return _put_back(root, backups, present, baseline=baseline, action="restore")


def recover(
    config_dir: Path | None = None,
    *,
    backup_dir: Path,
    baseline_path: Path | None = None,
) -> bool:
    """Restore a backup that a crash between pin and restore left behind.

    The backup is looked for in *backup_dir* and then in every legacy location
    (:func:`legacy_backup_dirs`), so a backup the shell wrapper left in its old directory is
    not stranded by the app looking only in its own (Fable S5-F6). ``baseline_path`` is the
    same one :func:`restore` takes, ``BASELINE_PATH`` by default.

    ``True`` when every leftover backup was put back byte-exact and removed, ``False`` when
    there was nothing to recover -- the ordinary case, and deliberately not an error: this runs
    at launch and before a pin. A restore that does not verify keeps the backup and returns
    ``False`` exactly as :func:`restore` does.

    Two locations holding a backup at once means the files were pinned twice without a restore
    between, so which copy is the user's original cannot be known. That raises and names every
    location rather than picking one or merging them: a wrong guess here overwrites the only
    copy of the user's settings.
    """
    root = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    baseline = Path(baseline_path) if baseline_path is not None else BASELINE_PATH
    held = backup_dirs_holding(root, backup_dir=Path(backup_dir))
    if not held:
        return False
    if len(held) > 1:
        raise ValueError(
            "refusing to recover Osaurus settings: more than one directory holds a backup "
            f"({', '.join(str(location) for location in held)}); which one is the user's "
            "original cannot be known from here, so nothing was restored. Restore or remove "
            "the copies by hand, then pin again."
        )
    backups = held[0]
    present = _backups(backups)
    return _put_back(root, backups, present, baseline=baseline, action="recover")


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
