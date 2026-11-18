"""S5-F8: ``pin`` re-records the baseline from the live host, so the drift gate compares the
host to itself and the committed baseline binds nothing.

The claim has two halves. The first is checkable here: a pin taken against a host that differs
from the recorded baseline writes the *host's* values as the new baseline, so
``diff_against_baseline(capture, load_baseline())`` is empty immediately afterwards and stays
empty for the whole pinned run -- the 20 tracked keys the pin does not set are never compared
with the conditions an earlier table was measured under. The second half, that no results
directory keeps the snapshot, is evidence in the report rather than a test: it is an absence.
"""

from __future__ import annotations

import json

import pytest

from ohyesmlx import osaurus_settings


HOST_THREADS = 4
COMMITTED_THREADS = 8


def _write_config(root):
    runtime = {
        "cache": {
            "blockDisk": {"enabled": True, "maxSizePercent": 10},
            "defaultMaxKVSize": 65536,
            "liveKVCodec": "engine_selected",
            "longPromptMultiplier": 2,
            "pagedKV": {"enabled": False},
            "prefix": {"enabled": True},
            "storedKVCodec": "auto",
        },
        "concurrency": {"continuousBatching": True, "maxConcurrentSequences": 1},
        "generation": {"streamInterval": 1},
        "memorySafety": {"mode": "safe_auto", "slider": 2},
        "mtp": {"mode": "auto"},
        "performance": {"compiledDecode": False, "tiedHeadCodec": "q6"},
    }
    server = {
        "backlog": 256,
        "modelEvictionPolicy": "unload_after_idle",
        "modelIdleResidencyPolicy": {"mode": "after_seconds", "seconds": 30},
        "modelLoadRAMHardThreshold": 0.9,
        "modelLoadRAMSoftThreshold": 0.8,
        "numberOfThreads": HOST_THREADS,
    }
    (root / "server-runtime.json").write_text(json.dumps(runtime))
    (root / "server.json").write_text(json.dumps(server))


def test_pin_replaces_the_committed_baseline_with_the_live_host(tmp_path):
    """The gate must still name a key the pin never touches, and today it names nothing."""
    root = tmp_path / "config"
    root.mkdir()
    _write_config(root)

    baseline_path = tmp_path / "baseline.json"
    committed = {
        key: value for key, value in osaurus_settings.capture_osaurus_settings(root).items()
    }
    committed["server.json:numberOfThreads"] = COMMITTED_THREADS
    baseline_path.write_text(json.dumps({"settings": committed}, indent=2) + "\n")

    osaurus_settings.pin(
        root, backup_dir=tmp_path / "backup", baseline_path=baseline_path
    )

    drift = osaurus_settings.diff_against_baseline(
        osaurus_settings.capture_osaurus_settings(root),
        osaurus_settings.load_baseline(baseline_path),
    )
    assert [name for name, _expected, _actual in drift] == ["server.json:numberOfThreads"], (
        "the pin wrote the live host over the recorded baseline, so the 20 keys it does not "
        "set are never compared with what the earlier table ran under"
    )


def test_pin_sets_exactly_three_of_the_tracked_keys(tmp_path):
    """The 20-vs-3 split the finding rests on, measured rather than quoted from a docstring."""
    root = tmp_path / "config"
    root.mkdir()
    _write_config(root)

    osaurus_settings.pin(
        root, backup_dir=tmp_path / "backup", baseline_path=tmp_path / "baseline.json"
    )

    baseline = osaurus_settings.load_baseline(tmp_path / "baseline.json")
    # 24 tracked keys since 05-07 attested `concurrency.smeltMode` (Fable S5-F9); the count was
    # 23 when this finding was written. What this test asserts is the 3-vs-rest split, not the
    # number: three keys are the pin's, every other tracked key keeps the host's own value.
    assert len(baseline) == len(osaurus_settings.TRACKED_KEYS) == 24
    pinned = {
        "server-runtime.json:cache.blockDisk.enabled",
        "server-runtime.json:cache.prefix.enabled",
        "server.json:modelIdleResidencyPolicy.seconds",
    }
    untouched = set(baseline) - pinned
    assert len(untouched) == 21
    # The untouched keys carry the live host's values, not the values an earlier table was
    # measured under: that is the whole of the finding. Nothing here asserts the *absence* of
    # drift, so this check stays true under the fix direction as well.
    assert baseline["server.json:numberOfThreads"] == HOST_THREADS
