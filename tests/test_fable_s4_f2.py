"""Fable 5.2 S4-F2: a pip engine reads as installed yet no start can reach it.

The claim: a venv script under the app's engines directory (or a global install) makes
``detect_all`` say ``installed: true`` and ``install`` refuse ``already_installed`` for
ever, while ``runtimes._engine_env`` prefixes only *recorded* lab paths -- so on the app's
PATH (``/usr/bin:/bin:/usr/sbin:/sbin``, ``BackendLauncher.swift:116``) the script is
unreachable and ``_resolve_program`` has no bundle executable to fall back to.

These checks assert what the finding says should hold: that a state detection calls
"installed" is a state a start can reach, or that ``install`` is still allowed to repair
it. They fail on the code as reviewed. Nothing here launches a process: the unreachable
name is demonstrated with ``shutil.which`` and ``_resolve_program``, and ``install`` runs
with every side effect faked.
"""

from __future__ import annotations

import os
import shutil
from types import SimpleNamespace

import pytest

from ohyesmlx import app_support_dir, engines, runtimes
from ohyesmlx.engines import detect_all, install

HOME = "/Users/test"
APP_SUPPORT = str(app_support_dir(HOME))
ENGINES_DIR = os.path.join(APP_SUPPORT, "engines")
LAB_PATHS = os.path.join(APP_SUPPORT, "lab-paths.json")

# The PATH a launchd-started app hands its backend.
APP_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


class FixtureEnv:
    """A filesystem made of the literal paths it is given; nothing else exists."""

    def __init__(self, home=HOME, files=None, links=None, dirs=()):
        self.home = home
        self.files = dict(files or {})
        self.links = dict(links or {})
        self.dirs = set(dirs)

    def exists(self, path):
        return path in self.files or path in self.links or path in self.dirs

    def read_text(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def listdir(self, path):
        prefix = path.rstrip("/") + "/"
        return sorted({p[len(prefix):].split("/")[0] for p in self.files if p.startswith(prefix)})

    def realpath(self, path):
        seen = set()
        while path in self.links and path not in seen:
            seen.add(path)
            path = self.links[path]
        return path


def app_venv(script_name, package, version):
    """A venv under the app's engines directory with *script_name* installed and a version."""
    root = os.path.join(ENGINES_DIR, f"{package}-{version}")
    python = "3.12.9"
    return {
        "root": root,
        "files": {
            os.path.join(root, "bin", script_name): "#!/bin/sh\n",
            os.path.join(root, "pyvenv.cfg"): f"version = {python}\n",
            os.path.join(
                root, "lib", f"python{python}", "site-packages", "_version.py"
            ): f'__version__ = "{version}"\n',
        },
    }


class RecordingRun:
    """The subprocess seam: records what would run, creates the venv a real step creates."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, timeout, env):
        self.calls.append(list(argv))
        root = engines._venv_root(list(argv))
        if root is not None:
            os.makedirs(os.path.join(root, "bin"), exist_ok=True)
        return 0, ""


class FreeLock:
    """The lock seam: always acquirable."""

    def acquire(self, engine):
        return True

    def release(self, engine):
        pass


def run_install(tmp_path, detect, engine="mlxlm"):
    """Call ``install`` with every side effect faked; return ``(result, events, runner)``."""
    events = []
    runner = RecordingRun()
    ok = install(
        engine,
        True,
        macos_major=15,
        detect=detect,
        run=runner,
        open_url=lambda url: None,
        emit=events.append,
        log_path=str(tmp_path / "install-log.jsonl"),
        lock=FreeLock(),
        python="/fake/python",
        engines_dir=str(tmp_path / "engines"),
        hardware=lambda: SimpleNamespace(disk_free_bytes=500 * 1024**3),
        sleep=lambda seconds: None,
    )
    return ok, events, runner


def error_codes(events):
    return [event["payload"]["code"] for event in events if event["type"] == "error"]


def start_environment(tmp_path):
    """What a start would see on the app's PATH, with no lab record written."""
    return runtimes._engine_env(lab_paths_path=str(tmp_path / "lab-paths.json"))


def test_an_app_venv_with_no_lab_record_is_startable_or_installable_again(tmp_path, monkeypatch):
    venv = app_venv("mlx_lm.server", "mlxlm", engines.TESTED_VERSIONS["mlxlm"])
    env = FixtureEnv(files=venv["files"], dirs={venv["root"]})
    status = next(item for item in detect_all(env) if item.name == "mlxlm")
    # 05-11 T2: the fixture's environment has no PATH and no lab record reaches the script,
    # so detection no longer calls it installed (the fix); install must then repair it.
    assert status.installed is False

    monkeypatch.setenv("PATH", APP_PATH)
    started = start_environment(tmp_path)
    reachable = shutil.which("mlx_lm.server", path=started["PATH"])

    ok, events, runner = run_install(tmp_path, lambda: detect_all(env))

    assert reachable is not None or ok is True, (
        "detection reports the app venv script installed and no lab path records it: "
        f"the start PATH is {started['PATH']!r}, which cannot reach "
        f"{venv['root']!r}; install answered {error_codes(events)!r} and ran "
        f"{len(runner.calls)} step(s), so neither a start nor a reinstall can repair it"
    )


def test_a_global_install_detected_but_not_on_the_app_path_is_startable_or_installable(tmp_path,
                                                                                    monkeypatch):
    root = os.path.join(HOME, "Dev", "tools", "mlx-optiq", ".venv")
    env = FixtureEnv(
        files={
            os.path.join(root, "pyvenv.cfg"): "version_info = 3.12.13\n",
            os.path.join(os.path.dirname(root), "pyproject.toml"):
                f'[project]\nname = "mlx-optiq"\nversion = "{engines.TESTED_VERSIONS["optiq"]}"\n',
        },
        links={os.path.join(root, "bin", "optiq"): "/opt/homebrew/bin/optiq"},
        dirs={root},
    )
    status = next(item for item in detect_all(env) if item.name == "optiq")
    # 05-11 T2: a global install off the start PATH is no longer reported installed.
    assert status.installed is False

    monkeypatch.setenv("PATH", APP_PATH)
    started = start_environment(tmp_path)
    assert "optiq" not in runtimes.ENGINE_BUNDLE_EXECUTABLES
    resolved = runtimes._resolve_program(("optiq", "serve"), started)

    ok, events, runner = run_install(tmp_path, lambda: detect_all(env), engine="optiq")

    assert shutil.which(resolved[0], path=started["PATH"]) is not None or ok is True, (
        f"optiq is at {root!r}, the app's PATH is "
        f"{started['PATH']!r}, {resolved[0]!r} resolves to {resolved!r} (no bundle fallback) "
        f"and install answered {error_codes(events)!r} with {len(runner.calls)} step(s)"
    )
