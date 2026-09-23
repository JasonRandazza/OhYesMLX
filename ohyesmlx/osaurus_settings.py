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
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".osaurus" / "config"

BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "osaurus-settings-baseline.json"
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
