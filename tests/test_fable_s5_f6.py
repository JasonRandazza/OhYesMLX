"""S5-F6: the shell pin and the app pin keep "the only copy" in two different directories.

``scripts/osaurus-pin.sh`` backs the user's Osaurus settings up to
``~/.osaurus/config.phase4-orig`` and traps ``INT TERM HUP`` only; ``quickbench`` backs up and
recovers in ``<Application Support>/quickbench/osaurus-backup``. ``pin`` refuses only over a
backup in the directory it was handed, so a shell runner killed outside its trap leaves the host
pinned with the originals in a directory the app never looks at. The app's launch ``recover``
then finds nothing, its cell ``pin`` copies the *already pinned* files as "the user's settings",
and ``restore`` verifies byte-exact against that copy and reports success.

Every path here is a pytest scratch directory; nothing reads or writes ``~/.osaurus``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohyesmlx import osaurus_settings, quickbench

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "osaurus-pin.sh"

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


@pytest.fixture
def config_dir(tmp_path):
    root = tmp_path / "config"
    root.mkdir()
    (root / "server.json").write_text(json.dumps(CONFIG_SERVER))
    (root / "server-runtime.json").write_text(json.dumps(CONFIG_RUNTIME))
    return root


def originals(config_dir) -> dict[str, bytes]:
    return {name: (config_dir / name).read_bytes() for name in osaurus_settings.PIN_FILES}


def shell_backup_dir() -> Path:
    """The backup directory ``scripts/osaurus-pin.sh`` hands both calls."""
    for row in SCRIPT.read_text().splitlines():
        if row.startswith("BACKUP_DIR="):
            value = row.split("=", 1)[1].strip().strip('"')
            return Path(
                value.replace("$HOME", str(Path.home())).replace(
                    "$CONFIG_DIR", str(Path.home() / ".osaurus" / "config")
                )
            )
    raise AssertionError(f"no BACKUP_DIR in {SCRIPT}")


def test_a_pin_refuses_over_a_backup_in_another_directory(config_dir, tmp_path):
    """The finding's own test idea: the refusal is keyed on the directory it was handed."""
    shell_backup = tmp_path / "config.phase4-orig"
    app_backup = tmp_path / "quickbench" / "osaurus-backup"
    baseline = tmp_path / "baseline.json"
    before = originals(config_dir)

    osaurus_settings.pin(config_dir, backup_dir=shell_backup, baseline_path=baseline)
    assert originals(config_dir) != before, "the first pin did not take effect"

    with pytest.raises(ValueError, match="already holds a backup"):
        osaurus_settings.pin(config_dir, backup_dir=app_backup, baseline_path=baseline)


def test_a_crashed_shell_pin_does_not_let_the_app_report_the_pinned_state_restored(
    config_dir, tmp_path, monkeypatch
):
    """The whole failure, through the app's own two directories.

    Run order is the app's: launch ``recover`` into ``quickbench.DEFAULT_BACKUP_DIR``, then a
    cell's ``recover`` and ``pin``, then ``restore``. The user's originals must be back
    afterwards; a ``True`` restore that leaves idle 900 in place is the reported lie.
    """
    shell_backup = tmp_path / "config.phase4-orig"
    app_backup = tmp_path / "quickbench" / "osaurus-backup"
    monkeypatch.setattr(quickbench, "DEFAULT_BACKUP_DIR", str(app_backup))
    baseline = tmp_path / "baseline.json"

    before = originals(config_dir)
    # The shell runner pinned and then died outside its trap.
    osaurus_settings.pin(config_dir, backup_dir=shell_backup, baseline_path=baseline)
    assert originals(config_dir) != before

    # Launch recovery looks only in the app's own directory.
    osaurus_settings.recover(
        config_dir,
        backup_dir=quickbench.DEFAULT_BACKUP_DIR,
        baseline_path=baseline,
    )
    # The cell's own recover, then its pin.
    osaurus_settings.recover(
        config_dir,
        backup_dir=quickbench.DEFAULT_BACKUP_DIR,
        baseline_path=baseline,
    )
    osaurus_settings.pin(
        config_dir,
        backup_dir=quickbench.DEFAULT_BACKUP_DIR,
        baseline_path=baseline,
    )
    restored = osaurus_settings.restore(
        config_dir,
        backup_dir=quickbench.DEFAULT_BACKUP_DIR,
        baseline_path=baseline,
    )

    assert (restored, originals(config_dir)) == (True, before), (
        "restore() reported success while the host stayed at the crashed shell pin's "
        f"settings (idle {json.loads((config_dir / 'server.json').read_text())['modelIdleResidencyPolicy']['seconds']} s)"
    )


def test_the_shell_pin_and_the_app_pin_name_one_backup_directory():
    """One location, or the recovery above cannot find the other runner's backup."""
    assert shell_backup_dir() == Path(quickbench.DEFAULT_BACKUP_DIR)


def test_the_shell_pin_restores_on_a_plain_exit():
    """A ``set -u`` abort, a failed command and a normal return all end in exit, not a signal;
    SIGKILL, SIGQUIT and a panic end in neither. Only an EXIT trap covers the first three."""
    traps = [
        row.strip() for row in SCRIPT.read_text().splitlines() if row.lstrip().startswith("trap ")
    ]
    assert traps, "the script no longer traps anything; this check's premise is stale"
    assert any("EXIT" in row and "osaurus_restore" in row for row in traps), (
        "no EXIT trap restores the pin, so a shell runner that exits outside "
        f"INT/TERM/HUP leaves the host pinned: {traps}"
    )
