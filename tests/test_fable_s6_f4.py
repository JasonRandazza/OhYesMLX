"""Fable 5.2 S6-F4: a stranded app-managed venv still reads installed, and install refuses.

An app-managed engine venv is built from ``sys.executable``, a path inside the app bundle
(``engines.install``'s ``python=`` default). Moving the app -- or replacing it with a build
carrying a different Python -- leaves the venv's ``bin/python`` symlink dangling while the
console script, ``pyvenv.cfg`` and the version file are all still regular files under
Application Support. Detection reads only those, and ``install`` refuses anything detection
calls installed.

The assertions below encode the repair the finding asks for (a dead interpreter is an
incomplete install, and install must redo it), so they fail on the current code. The
with-a-live-interpreter control passes, which is what makes the dangling link the only
difference between the two fixtures.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ohyesmlx import engines
from ohyesmlx.engines import detect_all, install

HOME = "/Users/test"
APP_SUPPORT = f"{HOME}/Library/Application Support/OhYesMLX"
ENGINES = f"{APP_SUPPORT}/engines"
LAB_PATHS = f"{APP_SUPPORT}/lab-paths.json"

# A copy run from Downloads without the quarantine flag: not translocated, so the
# `/AppTranslocation/` guard does not fire, and every app-managed venv points here.
BUNDLE = f"{HOME}/Downloads/OhYesMLX.app"
BASE_PYTHON = f"{BUNDLE}/Contents/Resources/python/bin/python3"

PYVENV_CFG = (
    f"home = {BUNDLE}/Contents/Resources/python/bin\n"
    f"executable = {BASE_PYTHON}\n"
    "version = 3.14.7\n"
)

# What each pip engine's app-managed venv holds: the console script pip writes, which is a
# regular file whose shebang names the venv's own interpreter.
CASES = {
    "mlxlm": {
        "script": "mlx_lm.server",
        "version_path": "lib/python3.14/site-packages/mlx_lm/_version.py",
        "version_text": f'__version__ = "{engines.TESTED_VERSIONS["mlxlm"]}"\n',
    },
    "optiq": {
        "script": "optiq",
        "version_path": (
            "lib/python3.14/site-packages/"
            f"mlx_optiq-{engines.TESTED_VERSIONS['optiq']}.dist-info/METADATA"
        ),
        "version_text": (
            "Metadata-Version: 2.4\n"
            "Name: mlx-optiq\n"
            f"Version: {engines.TESTED_VERSIONS['optiq']}\n"
        ),
    },
}


class FakeEnv:
    """The filesystem the real one would be after the app moved, and nothing else.

    ``exists`` follows links the way ``os.path.exists`` does: a link whose target is gone
    does not exist. ``realpath`` resolves links without requiring the target, the way
    ``os.path.realpath`` does.
    """

    def __init__(self, home=HOME, files=None, links=None, dirs=()):
        self.home = home
        self.files = dict(files or {})
        self.links = dict(links or {})
        self.dirs = set(dirs)

    def exists(self, path):
        if path in self.files or path in self.dirs:
            return True
        if path in self.links:
            target = self.realpath(path)
            return target in self.files or target in self.dirs
        return False

    def read_text(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        value = self.files[path]
        if isinstance(value, Exception):
            raise value
        return value

    def listdir(self, path):
        prefix = path.rstrip("/") + "/"
        names = {p[len(prefix):].split("/")[0] for p in self.files if p.startswith(prefix)}
        return sorted(names)

    def realpath(self, path):
        seen = set()
        while path in self.links and path not in seen:
            seen.add(path)
            path = self.links[path]
        return path


def stranded_env(name, *, interpreter=True):
    """*name*'s app-managed venv, installed before the app moved.

    With ``interpreter=False`` the recorded base interpreter is gone, so ``bin/python``
    dangles exactly as it does after the bundle is moved or replaced. The lab-paths entry
    ``install`` writes on success is present in both variants, so detection takes the same
    route a real post-install machine does.
    """
    case = CASES[name]
    root = f"{ENGINES}/{name}-{engines.TESTED_VERSIONS[name]}"
    files = {
        f"{root}/bin/{case['script']}": f"#!{root}/bin/python\n",
        f"{root}/pyvenv.cfg": PYVENV_CFG,
        f"{root}/{case['version_path']}": case["version_text"],
        LAB_PATHS: json.dumps({name: f"{root}/bin"}),
    }
    if interpreter:
        files[BASE_PYTHON] = "#!/bin/sh\n"
    return FakeEnv(files=files, links={f"{root}/bin/python": BASE_PYTHON})


def status_of(env, name):
    return {status.name: status for status in detect_all(env)}[name]


class FakeRun:
    """The install subprocess seam: records each call and leaves what a venv step would."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, timeout, env):
        self.calls.append(list(argv))
        root = engines._venv_root(argv)
        if root is not None and not os.path.lexists(root):
            (Path(root) / "bin").mkdir(parents=True, exist_ok=True)
        return 0, ""


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_live_interpreter_makes_the_same_venv_installed_and_tested(name):
    status = status_of(stranded_env(name), name)
    assert status.installed is True
    assert status.version == engines.TESTED_VERSIONS[name]
    assert status.tested is True


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_venv_whose_interpreter_moved_with_the_app_is_not_installed(name):
    status = status_of(stranded_env(name, interpreter=False), name)
    assert status.installed is False, (
        f"detection reports {name} installed at {status.path!r} (version {status.version!r}, "
        f"tested={status.tested}) although {BASE_PYTHON} is gone, so every script in the "
        "venv has a dead shebang"
    )


def test_install_redoes_a_venv_whose_interpreter_moved_with_the_app(tmp_path):
    env = stranded_env("mlxlm", interpreter=False)
    run = FakeRun()
    events = []

    ok = install(
        "mlxlm",
        True,
        macos_major=15,
        run=run,
        open_url=lambda url: pytest.fail("a pip plan opens no page"),
        emit=events.append,
        detect=lambda: detect_all(env),
        hardware=lambda: SimpleNamespace(disk_free_bytes=500 * 1024**3),
        log_path=str(tmp_path / "install-log.jsonl"),
        lock=engines.EngineLocks(),
        python="/fake/python",
        engines_dir=str(tmp_path / "engines"),
    )

    codes = [event["payload"]["code"] for event in events if event["type"] == "error"]
    assert "already_installed" not in codes, (
        f"install refused the only repair the app has with {codes}; there is no uninstall "
        "surface, so the user's only way out is deleting the engines directory by hand"
    )
    assert ok is True
    # The venv step and the pip step both ran, the way a fresh install does.
    assert len(run.calls) == 2
