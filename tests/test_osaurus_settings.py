"""Checks for ``osaurus_settings.pin``, ``restore`` and ``recover`` (plans 04-03a, 04-03c).

Every path in this file is a pytest scratch directory. Nothing here reads or writes
``~/.osaurus``, and nothing starts a runtime: the pin is exercised against a copy of the two
config files, never the host's own.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from ohyesmlx import osaurus_settings

# The two files a pin touches, shaped the way the host writes them: unrelated keys on both
# sides of the ones the pin changes, so a test can tell "edited the pin" from "rewrote the file".
CONFIG_SERVER = {
    "backlog": 256,
    "modelEvictionPolicy": "unload_after_idle",
    "modelIdleResidencyPolicy": {"mode": "after_seconds", "seconds": 30},
    "modelLoadRAMHardThreshold": 0.9,
    "modelLoadRAMSoftThreshold": 0.8,
    "numberOfThreads": 12,
}
CONFIG_RUNTIME = {
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

# A baseline as the guard left it before a pin: not the bytes `write_baseline` produces, so a
# restore that wrote the pinned baseline again instead of the backup is visible.
BASELINE_SENTINEL = b'{"settings": {"server.json:numberOfThreads": 12}}\n'


@pytest.fixture
def config_dir(tmp_path):
    root = tmp_path / "config"
    root.mkdir()
    (root / "server.json").write_text(json.dumps(CONFIG_SERVER))
    (root / "server-runtime.json").write_text(json.dumps(CONFIG_RUNTIME))
    return root


@pytest.fixture
def backup_dir(tmp_path):
    return tmp_path / "backup"


@pytest.fixture
def baseline_path(tmp_path):
    return tmp_path / "baseline.json"


def originals(config_dir) -> dict[str, bytes]:
    return {name: (config_dir / name).read_bytes() for name in osaurus_settings.PIN_FILES}


def pin(config_dir, backup_dir, baseline_path) -> None:
    osaurus_settings.pin(
        config_dir, backup_dir=backup_dir, baseline_path=baseline_path
    )


# --------------------------------------------------------------------------------------
# pin
# --------------------------------------------------------------------------------------


def test_pin_backs_up_both_configs_byte_exact_and_applies_the_run_settings(
    config_dir, backup_dir, baseline_path
):
    before = originals(config_dir)

    pin(config_dir, backup_dir, baseline_path)

    for name, original in before.items():
        assert (backup_dir / name).read_bytes() == original, name

    runtime = json.loads((config_dir / "server-runtime.json").read_text())
    assert runtime["cache"]["prefix"]["enabled"] is False
    assert runtime["cache"]["blockDisk"]["enabled"] is False
    # Everything the pin does not name is left as the host had it.
    assert runtime["cache"]["defaultMaxKVSize"] == 65536
    assert runtime["cache"]["blockDisk"]["maxSizePercent"] == 10

    server = json.loads((config_dir / "server.json").read_text())
    assert server["modelIdleResidencyPolicy"]["seconds"] == 900
    assert server["modelIdleResidencyPolicy"]["mode"] == "after_seconds"
    assert server["numberOfThreads"] == 12


def test_pin_writes_the_baseline_the_drift_guard_reads_to_the_given_path(
    config_dir, backup_dir, baseline_path
):
    pin(config_dir, backup_dir, baseline_path)

    baseline = osaurus_settings.load_baseline(baseline_path)
    assert baseline["server.json:modelIdleResidencyPolicy.seconds"] == 900
    assert baseline["server-runtime.json:cache.prefix.enabled"] is False
    assert baseline["server-runtime.json:cache.blockDisk.enabled"] is False
    assert (
        osaurus_settings.diff_against_baseline(
            osaurus_settings.capture_osaurus_settings(config_dir), baseline
        )
        == ()
    )


def test_pin_never_writes_the_default_baseline_unless_it_is_passed(
    config_dir, backup_dir, baseline_path, tmp_path, monkeypatch
):
    default = tmp_path / "default-baseline.json"
    monkeypatch.setattr(osaurus_settings, "BASELINE_PATH", default)

    pin(config_dir, backup_dir, baseline_path)

    assert not default.exists(), "the pin wrote a baseline nobody passed"


def test_the_backup_directory_is_created_0700(config_dir, backup_dir, baseline_path):
    pin(config_dir, backup_dir, baseline_path)

    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700


def test_a_second_pin_refuses_rather_than_overwriting_the_users_original(
    config_dir, backup_dir, baseline_path
):
    before = originals(config_dir)
    pin(config_dir, backup_dir, baseline_path)

    with pytest.raises(ValueError) as raised:
        pin(config_dir, backup_dir, baseline_path)

    message = str(raised.value)
    assert str(backup_dir) in message
    assert "already holds a backup" in message
    for name, original in before.items():
        assert (backup_dir / name).read_bytes() == original, "the original was overwritten"


@pytest.mark.parametrize(
    "name", [osaurus_settings.BASELINE_BACKUP, osaurus_settings.BASELINE_ABSENT]
)
def test_a_pin_refuses_over_a_leftover_baseline_backup_or_marker(
    config_dir, backup_dir, baseline_path, name
):
    """The baseline backup is part of the set: pinning over it would destroy the only copy of
    a baseline the user had before the crashed run."""
    backup_dir.mkdir()
    (backup_dir / name).write_bytes(b"")
    before = originals(config_dir)

    with pytest.raises(ValueError) as raised:
        pin(config_dir, backup_dir, baseline_path)

    assert "already holds a backup" in str(raised.value)
    assert originals(config_dir) == before
    assert not baseline_path.exists()


def test_a_pin_that_killed_the_write_between_temp_and_replace_leaves_the_files_intact(
    config_dir, backup_dir, baseline_path, monkeypatch
):
    """A kill mid-write must not leave a half-written Osaurus config, so the write lands in a
    temp file and the original is only replaced once it is whole."""
    before = originals(config_dir)
    real_replace = os.replace

    def killed(source, target):
        if Path(target).parent == config_dir:
            raise OSError("killed between temp and replace")
        return real_replace(source, target)

    monkeypatch.setattr(osaurus_settings.os, "replace", killed)

    with pytest.raises(OSError):
        pin(config_dir, backup_dir, baseline_path)

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name
        assert not (config_dir / f"{name}.pin-tmp").exists(), "a stale temp was left behind"


# --------------------------------------------------------------------------------------
# restore
# --------------------------------------------------------------------------------------


def test_restore_puts_every_file_back_byte_exact_and_removes_the_backup(
    config_dir, backup_dir, baseline_path
):
    before = originals(config_dir)
    pin(config_dir, backup_dir, baseline_path)

    assert (
        osaurus_settings.restore(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is True
    )

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name
    assert not baseline_path.exists(), "a baseline the pin wrote was left behind"
    assert not backup_dir.exists(), "the backup survived a verified restore"


def test_restore_puts_the_baseline_back_byte_exact_after_a_later_write(
    config_dir, backup_dir, baseline_path
):
    """`osaurus_set_seqs` re-records the baseline mid-run; restore must return the pre-pin
    bytes, not whatever the run last wrote."""
    before = originals(config_dir)
    baseline_path.write_bytes(BASELINE_SENTINEL)
    pin(config_dir, backup_dir, baseline_path)
    assert (
        backup_dir / osaurus_settings.BASELINE_BACKUP
    ).read_bytes() == BASELINE_SENTINEL

    osaurus_settings.write_baseline(baseline_path, config_dir)
    assert baseline_path.read_bytes() != BASELINE_SENTINEL

    assert (
        osaurus_settings.restore(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is True
    )

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name
    assert baseline_path.read_bytes() == BASELINE_SENTINEL
    assert not backup_dir.exists()


def test_a_pin_with_no_baseline_restore_leaves_the_guard_ungated(
    config_dir, backup_dir, baseline_path
):
    """No baseline at pin time means no gate to put back: the pin's own baseline is deleted,
    and the marker is what says so."""
    before = originals(config_dir)
    assert not baseline_path.exists()

    pin(config_dir, backup_dir, baseline_path)

    assert (backup_dir / osaurus_settings.BASELINE_ABSENT).exists()
    assert osaurus_settings.load_baseline(baseline_path) is not None, "the pin writes one"

    assert (
        osaurus_settings.restore(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is True
    )

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name
    assert not baseline_path.exists(), "the guard is as ungated as it was before the pin"
    assert not backup_dir.exists()


def test_restore_returns_false_and_keeps_every_backup_when_a_file_is_not_byte_identical(
    config_dir, backup_dir, baseline_path, monkeypatch
):
    """False is not a failure mode to shrug at: nothing was put back, so the only copy of the
    user's settings stays where a later restore can find it."""
    before = originals(config_dir)
    pin(config_dir, backup_dir, baseline_path)
    monkeypatch.setattr(osaurus_settings, "_write_atomic", lambda target, data: None)

    assert (
        osaurus_settings.restore(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is False
    )

    for name, original in before.items():
        assert not (config_dir / name).read_bytes() == original, "nothing was restored"
        assert (backup_dir / name).read_bytes() == original, name


def test_a_baseline_that_does_not_match_after_restore_returns_false_and_keeps_the_backups(
    config_dir, backup_dir, baseline_path, monkeypatch
):
    """The baseline is verified like the configs: one mismatch keeps all three backups, the
    two configs included, so a retry has the whole set."""
    before = originals(config_dir)
    baseline_path.write_bytes(BASELINE_SENTINEL)
    pin(config_dir, backup_dir, baseline_path)
    real_write = osaurus_settings._write_atomic

    def skip_the_baseline(target, data):
        if Path(target) == baseline_path:
            return
        real_write(target, data)

    monkeypatch.setattr(osaurus_settings, "_write_atomic", skip_the_baseline)

    assert (
        osaurus_settings.restore(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is False
    )

    assert baseline_path.read_bytes() != BASELINE_SENTINEL
    for name, original in before.items():
        assert (backup_dir / name).read_bytes() == original, name
    assert (
        backup_dir / osaurus_settings.BASELINE_BACKUP
    ).read_bytes() == BASELINE_SENTINEL


def test_restore_without_a_backup_refuses(config_dir, backup_dir, baseline_path):
    with pytest.raises(ValueError) as raised:
        osaurus_settings.restore(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )

    assert str(backup_dir) in str(raised.value)
    assert "no backup" in str(raised.value)


def test_pin_and_restore_accept_the_strings_the_shell_hands_them(
    config_dir, backup_dir, baseline_path
):
    """`scripts/osaurus-pin.sh` interpolates its paths into a `python -c` string, so the
    functions have to take the strings that arrive rather than only `Path` objects."""
    before = originals(config_dir)

    osaurus_settings.pin(
        str(config_dir), backup_dir=str(backup_dir), baseline_path=str(baseline_path)
    )
    assert osaurus_settings.load_baseline(baseline_path) is not None
    assert (
        osaurus_settings.restore(
            str(config_dir),
            backup_dir=str(backup_dir),
            baseline_path=str(baseline_path),
        )
        is True
    )

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name


# --------------------------------------------------------------------------------------
# recover: a crash between pin and restore must not strand the user's settings
# --------------------------------------------------------------------------------------


def test_recover_restores_a_backup_a_crash_left_behind(
    config_dir, backup_dir, baseline_path
):
    before = originals(config_dir)
    pin(config_dir, backup_dir, baseline_path)
    # The crash: the pin applied and nothing called restore. `recover` is what 04-03b calls
    # before its next pin, and what the app calls at launch.
    assert json.loads((config_dir / "server.json").read_text())[
        "modelIdleResidencyPolicy"
    ]["seconds"] == 900

    assert (
        osaurus_settings.recover(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is True
    )

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name
    assert not backup_dir.exists()


def test_recover_restores_the_baseline_with_the_configs(
    config_dir, backup_dir, baseline_path
):
    before = originals(config_dir)
    baseline_path.write_bytes(BASELINE_SENTINEL)
    pin(config_dir, backup_dir, baseline_path)

    assert (
        osaurus_settings.recover(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is True
    )

    for name, original in before.items():
        assert (config_dir / name).read_bytes() == original, name
    assert baseline_path.read_bytes() == BASELINE_SENTINEL
    assert not backup_dir.exists()


def test_recover_is_a_no_op_without_a_backup(config_dir, backup_dir, baseline_path):
    before = originals(config_dir)

    assert (
        osaurus_settings.recover(
            config_dir, backup_dir=backup_dir, baseline_path=baseline_path
        )
        is False
    )

    assert originals(config_dir) == before
    assert not baseline_path.exists()
    assert not backup_dir.exists()


# --------------------------------------------------------------------------------------
# the record: one JSON line per pin and restore, names and outcome, never the contents
# --------------------------------------------------------------------------------------


def test_pin_and_restore_each_write_one_json_line_naming_the_files_and_the_outcome(
    config_dir, backup_dir, baseline_path, capsys
):
    files = [
        *(str(config_dir / name) for name in osaurus_settings.PIN_FILES),
        str(baseline_path),
    ]

    pin(config_dir, backup_dir, baseline_path)
    lines = capsys.readouterr().err.strip().splitlines()
    assert len(lines) == 1
    pinned = json.loads(lines[0])
    assert pinned == {
        "action": "pin",
        "outcome": "pinned",
        "files": files,
        "backup_dir": str(backup_dir),
    }

    osaurus_settings.restore(
        config_dir, backup_dir=backup_dir, baseline_path=baseline_path
    )
    lines = capsys.readouterr().err.strip().splitlines()
    assert len(lines) == 1
    restored = json.loads(lines[0])
    assert restored == {
        "action": "restore",
        "outcome": "restored byte-exact",
        "files": files,
        "backup_dir": str(backup_dir),
    }
