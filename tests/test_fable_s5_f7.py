"""S5-F7: a failed Osaurus restore is reported as success on both shell paths.

One line: ``scripts/osaurus-pin.sh``'s ``osaurus_restore_check`` (``:69-84``) ends in the
``trap ... INT TERM HUP`` statement, so after its own ``RESTORE FAILED`` branch it still
returns 0 and disarms the restoring trap; ``osaurus_restore`` (``:24-29``), the only restore
the signal trap (``:32``) runs, discards ``osaurus_settings.restore``'s boolean (``|| return
1`` sees only an exception), so an aborted run leaves the host pinned, prints no verdict and
exits 130 regardless.

``osaurus_settings.restore`` is stubbed with a scratch module on ``PYTHONPATH`` -- the real
one is exercised by ``tests/test_osaurus_settings.py`` and needs a real backup tree. Every
path here is a pytest scratch directory; nothing reads or writes ``~/.osaurus``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "osaurus-pin.sh"

STUB = """\
def pin(config_dir=None, *, backup_dir, baseline_path=None):
    return None


def restore(config_dir=None, *, backup_dir, baseline_path=None):
    return {restore_returns}
"""


def _run(tmp_path, *, restore_returns, body):
    """Source the script in a scratch tree and run *body* against a stubbed restore."""
    config = tmp_path / "config"
    backup = tmp_path / "config.phase4-orig"
    stub_pkg = tmp_path / "stub" / "ohyesmlx"
    work = tmp_path / "work"
    home = tmp_path / "home"
    for directory in (config, backup, work, home, stub_pkg):
        directory.mkdir(parents=True)
    for name in ("server.json", "server-runtime.json"):
        (config / name).write_text("{}\n")
        (backup / name).write_bytes((config / name).read_bytes())
    (stub_pkg / "__init__.py").write_text("")
    (stub_pkg / "osaurus_settings.py").write_text(
        STUB.format(restore_returns=restore_returns)
    )

    shell = f"""\
sweep() {{ :; }}
source "$1" || {{ echo SOURCE-FAILED; exit 97; }}
CONFIG_DIR="$2"
BACKUP_DIR="$3"
CONF="$CONFIG_DIR/server-runtime.json"
SERVER="$CONFIG_DIR/server.json"
CONF_ORIG="$BACKUP_DIR/server-runtime.json"
SERVER_ORIG="$BACKUP_DIR/server.json"
{body}
printf 'STATUS=%s\\n' "$?"
trap -p INT
"""
    env = {
        **os.environ,
        "PY": sys.executable,
        "PYTHONPATH": str(stub_pkg.parent),
        "HOME": str(home),
    }
    return subprocess.run(
        ["bash", "-c", shell, "_", str(SCRIPT), str(config), str(backup)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )


def _output(result) -> str:
    return result.stdout + result.stderr


def _function_status(result) -> int:
    match = re.search(r"^STATUS=(\d+)$", result.stdout, re.M)
    assert match, f"the function did not return; output was:\n{_output(result)}"
    return int(match.group(1))


def test_a_failed_restore_check_exits_non_zero(tmp_path):
    """``osaurus_restore_check``'s last command is its ``trap`` line, so it returns 0 even
    after printing ``RESTORE FAILED``; a caller that checks the status sees a clean run."""
    result = _run(tmp_path, restore_returns="False", body="osaurus_restore_check")
    assert "RESTORE FAILED" in _output(result), (
        "the scratch harness did not reach the failure branch:\n" + _output(result)
    )
    assert _function_status(result) != 0, (
        "osaurus_restore_check returned 0 after a restore that did not verify, so "
        "run_canary.sh prints DONE and the script exits 0:\n" + _output(result)
    )


def test_a_failed_restore_check_leaves_the_restoring_trap_armed(tmp_path):
    """The trailing ``trap ... sweep; exit 130`` replaces the restoring trap, so after a
    failed restore an interrupt no longer attempts one."""
    result = _run(tmp_path, restore_returns="False", body="osaurus_restore_check")
    traps = [
        row
        for row in result.stdout.splitlines()
        if row.startswith("trap --") and row.rstrip().endswith("INT")
    ]
    assert traps, "the function left no INT trap; output was:\n" + _output(result)
    assert any("osaurus_restore" in row for row in traps), (
        "a failed restore disarmed the restoring trap, so a later interrupt cannot retry "
        f"it: {traps}"
    )


def test_osaurus_restore_reports_a_failed_restore(tmp_path):
    """``osaurus_restore`` discards the boolean, so a restore that did not verify exits 0."""
    result = _run(tmp_path, restore_returns="False", body="osaurus_restore")
    assert _function_status(result) != 0, (
        "osaurus_restore returned 0 for a restore that did not verify:\n" + _output(result)
    )


def test_osaurus_restore_prints_a_verdict_when_the_restore_fails(tmp_path):
    """The trap path prints only ``ABORTED``; the restore's own outcome is never said."""
    result = _run(tmp_path, restore_returns="False", body="osaurus_restore")
    assert "RESTORE FAILED" in _output(result), (
        "osaurus_restore said nothing about the restore it could not verify:\n"
        + _output(result)
    )


def test_the_signal_trap_reports_the_restore_outcome(tmp_path):
    """End to end: ``osaurus_pin`` installs the trap, ``kill -INT $$`` runs it, and the
    script exits 130 with no verdict, so the exit code cannot distinguish a restore that
    took from one that left the host pinned."""
    result = _run(
        tmp_path,
        restore_returns="False",
        body="osaurus_pin\nkill -INT $$\necho TRAP-DID-NOT-RUN",
    )
    assert "TRAP-DID-NOT-RUN" not in result.stdout, _output(result)
    assert result.returncode == 130, (
        f"expected the trap's own exit 130, got {result.returncode}:\n" + _output(result)
    )
    assert "RESTORE FAILED" in _output(result), (
        "the abort path exited 130 without saying whether the restore verified:\n"
        + _output(result)
    )


def test_a_successful_restore_check_still_exits_zero_and_says_so(tmp_path):
    """Guard: the failure assertions above must not be satisfied by breaking success."""
    result = _run(tmp_path, restore_returns="True", body="osaurus_restore_check")
    assert _function_status(result) == 0, _output(result)
    assert "restored byte-exact" in _output(result), _output(result)
