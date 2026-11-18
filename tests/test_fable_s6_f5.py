"""S6-F5: the clean-account smoke spawns the built bundle, not a wheel console script.

The finding: `scripts/smoke_clean_account.py` started ``<venv>/bin/ohyesmlx app`` -- a console
script under whatever interpreter ran the client, no ``-I``, no ``-B``, no built environment
-- while ``app/Sources/OhYesMLXKit/BackendLauncher.swift`` starts
``[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]`` under a four-key environment, and
05-06-PLAN AC-6 asks for the latter.

The tests below assert the repair. Their earlier versions pinned the old spawn ("no flag that
could point it at a bundle", "inherits the client's environment"), so each one is inverted here
rather than deleted: a regression back to a console script fails them again.

No network, no subprocess, no sudo: ``Popen`` is replaced and the child's stdout is a pipe
whose write end is already closed, so the launch read returns at EOF and ``main`` takes its
launch-error path (SKIPs + AC-6 shutdown) without opening a socket.
"""

from __future__ import annotations

import importlib.util
import io
import os
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "smoke_clean_account.py"
DRIVER = REPO / "scripts" / "smoke_clean_account.sh"
LAUNCHER = REPO / "app" / "Sources" / "OhYesMLXKit" / "BackendLauncher.swift"

_spec = importlib.util.spec_from_file_location("smoke_s6f5", SCRIPT)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

TEST_APP = "/Users/Shared/oymlx-smoke/OhYesMLX.app"
TEST_PYTHON = f"{TEST_APP}/Contents/Resources/python/bin/python3"


class _FakeProcess:
    """Enough of ``subprocess.Popen`` for ``main``'s launch-error path."""

    def __init__(self, stdout_fd: int):
        self.stdin = io.BytesIO()
        self.stdout = os.fdopen(stdout_fd, "rb", buffering=0)
        self.killed = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def _spawned(monkeypatch, tmp_path, python=TEST_PYTHON) -> dict:
    """Run ``main`` once and return what it handed ``Popen``."""
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        captured["argv"] = list(argv)
        captured["kwargs"] = dict(kwargs)
        return _FakeProcess(read_fd)

    monkeypatch.setattr(smoke.subprocess, "Popen", fake_popen)
    code = smoke.main(
        [
            "--out", str(tmp_path),
            "--head", "0" * 40,
            "--forbid", "/Users/jrazz",
            "--model", "mlx-community/Qwen3-0.6B-4bit",
            "--python", python,
            "--artifact", TEST_APP,
            "--ports", "1337 8000 8080 8081 8100 8200",
        ]
    )
    assert captured, f"main never spawned a child (exit {code})"
    return captured


def test_the_smoke_spawns_the_launchers_argv_with_the_bundles_interpreter(monkeypatch, tmp_path):
    """The child is ``[bundle python, -I, -B, -m ohyesmlx.cli, app]`` -- the launcher's spawn."""
    argv = _spawned(monkeypatch, tmp_path)["argv"]

    assert argv == [TEST_PYTHON, "-I", "-B", "-m", "ohyesmlx.cli", "app"]
    assert os.path.join(smoke.sys.prefix, "bin", "ohyesmlx") not in argv, (
        "a console script under the client's interpreter is the artifact S6-F5 found the "
        "smoke running instead of the bundle"
    )
    assert "OhYesMLX.app/Contents/Resources/python" in argv[0]


def test_the_smoke_passes_the_launchers_environment_not_its_own(monkeypatch, tmp_path):
    """``env=`` is the launcher's, read off ``BackendLauncher``'s own constants."""
    source = LAUNCHER.read_text(encoding="utf-8")
    path_match = re.search(r'public static let pathForChild = "([^"]+)"', source)
    keys_match = re.search(r"public static let inheritedKeys = \[(.*?)\]", source, re.S)
    assert path_match is not None and keys_match is not None
    declared_path = path_match.group(1)
    declared_keys = set(re.findall(r'"([A-Z]+)"', keys_match.group(1)))

    kwargs = _spawned(monkeypatch, tmp_path)["kwargs"]
    environment = kwargs["env"]
    assert environment["PATH"] == declared_path
    assert declared_path == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert set(environment) - {"PATH"} <= declared_keys
    for inherited in declared_keys:
        if inherited in os.environ:
            assert environment[inherited] == os.environ[inherited], inherited
    assert "/opt/homebrew" not in environment["PATH"]
    assert kwargs["stdin"] is smoke.subprocess.PIPE
    assert kwargs["stdout"] is smoke.subprocess.PIPE


def test_the_smoke_argv_matches_the_launchers_declared_argv(monkeypatch, tmp_path):
    """Read from the Swift source rather than restated: the tokens are the same, in order."""
    source = LAUNCHER.read_text(encoding="utf-8")
    match = re.search(r"let argv = \[(.*?)\]", source, re.S)
    assert match is not None, "BackendLauncher has no single argv definition"
    declared = [part.strip() for part in match.group(1).split(",")]
    # The launcher appends `--lock-dir <app support>`; the smoke's launch line is read
    # without it, so only the backend's own argv is compared.
    assert declared[:6] == [
        "interpreter.path",
        '"-I"',
        '"-B"',
        '"-m"',
        '"ohyesmlx.cli"',
        '"app"',
    ]
    smoke_argv = _spawned(monkeypatch, tmp_path)["argv"]
    assert smoke_argv[1:] == ["-I", "-B", "-m", "ohyesmlx.cli", "app"]


def test_the_client_takes_the_bundle_interpreter_and_records_the_artifact(monkeypatch, capsys, tmp_path):
    """``--python`` and ``--artifact`` exist, are required, and the results name the artifact."""
    with pytest.raises(SystemExit) as exit_info:
        smoke.main(["--help"])
    assert exit_info.value.code == 0
    usage = capsys.readouterr().out
    for flag in ("--out", "--head", "--forbid", "--model", "--ports", "--python", "--artifact"):
        assert flag in usage

    _spawned(monkeypatch, tmp_path)
    results = list(tmp_path.glob("*.json"))
    assert len(results) == 1
    import json

    payload = json.loads(results[0].read_text(encoding="utf-8"))
    assert payload["artifact"] == TEST_APP


def test_the_driver_copies_the_bundle_and_runs_it_with_its_own_interpreter():
    """The other half of the claim, on the .sh: the built bundle is copied and drives the run."""
    driver = DRIVER.read_text(encoding="utf-8")

    assert not re.search(r"^PY=/opt/homebrew/bin/python3\.\d+$", driver, re.M)
    assert 'ditto "$REPO/dist/$APP_NAME" "$TEST_APP"' in driver
    assert "git -C \"$REPO\" archive --format=tar HEAD" not in driver
    assert "uv build --wheel" not in driver
    assert 'Contents/Resources/python/bin/python3' in driver
    assert '--python "$TEST_PYTHON"' in driver
    assert '--artifact "$artifact"' in driver
    assert "smoke_clean_account.py" in driver
