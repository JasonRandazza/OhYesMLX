"""Checks for ohyesmlx.engines.

Every check drives ``detect_all`` through a fake filesystem: ``files`` maps a path to
the literal text at it (or to the exception reading it raises), ``links`` maps a path
to the target ``realpath`` follows, and ``dirs`` are empty directories. Nothing is
launched, no real file is read, and no expected value is computed from the code under
test.
"""

from __future__ import annotations

import inspect
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import FrozenInstanceError, fields
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ohyesmlx import engines
from ohyesmlx.engines import EngineLocks, Plan, Step, detect_all, install, install_plan
from ohyesmlx.runtimes import RUNTIMES

HOME = "/Users/test"

# install_plan takes no env: the venv it names is under the real user's home.
ENGINES_DIR = os.path.expanduser("~/Library/Application Support/OhYesMLX/engines")

# The committed constraints files live beside the package, in ohyesmlx/constraints/.
CONSTRAINTS = Path(__file__).resolve().parent.parent / "ohyesmlx" / "constraints"

OSAURUS_BUNDLE = "/Applications/osaurus.app"
OMLX_BUNDLE = "/Applications/oMLX.app"
OMLX_SHIM = f"{HOME}/.omlx/bin/omlx"
VMLX_BUNDLE = "/Applications/vMLX.app"
VMLX_ENGINE_INIT = (
    f"{VMLX_BUNDLE}/Contents/Resources/vmlx-engine-source/vmlx_engine/__init__.py"
)
OPTIQ_VENV = f"{HOME}/Dev/tools/mlx-optiq/.venv"
MLXLM_VENV = f"{HOME}/.local/share/ohyesmlx/mlx-lm-0.31.3"

VERSIONS = {
    "osaurus": "0.25.29",
    "omlx": "0.7.3",
    "optiq": "0.5.13",
    "mlxlm": "0.31.3",
    "vmlx": "1.6.59",
}

# The date each version was adopted, as the shipped manifest records it.
VERIFIED = {
    "mlxlm": "2026-10-29",
    "osaurus": "2026-11-02",
    "omlx": "2026-11-02",
    "optiq": "2026-10-29",
    "vmlx": "2026-10-29",
}


def app_plist(version):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleShortVersionString</key>
    <string>{version}</string>
</dict>
</plist>
"""


class FakeEnv:
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


def installed_env(versions=VERSIONS):
    """Every engine installed at ``versions[name]``, at the paths the research found.

    Each venv records its interpreter the way the tool that made it does: ``version``
    from the stdlib's venv, ``version_info`` from uv.
    """
    return FakeEnv(
        files={
            f"{OSAURUS_BUNDLE}/Contents/Info.plist": app_plist(versions["osaurus"]),
            f"{OMLX_BUNDLE}/Contents/Info.plist": app_plist(versions["omlx"]),
            f"{OPTIQ_VENV}/pyvenv.cfg": "home = /opt/homebrew/opt/python@3.12/bin\n"
            "version_info = 3.12.13\n",
            # The checkout is editable: the version lives in the pyproject beside .venv,
            # and OptiQ's own `__init__` computes it at import, so no literal is there.
            f"{OPTIQ_VENV[:-len('/.venv')]}/pyproject.toml": (
                f'[project]\nname = "mlx-optiq"\nversion = "{versions["optiq"]}"\n'
            ),
            f"{MLXLM_VENV}/bin/mlx_lm.server": "#!/bin/sh\n",
            f"{MLXLM_VENV}/pyvenv.cfg": "version = 3.14.7\n",
            f"{MLXLM_VENV}/lib/python3.14/site-packages/mlx_lm/_version.py": (
                f'__version__ = "{versions["mlxlm"]}"\n'
            ),
            VMLX_ENGINE_INIT: f'__version__ = "{versions["vmlx"]}"\n',
        },
        links={
            OMLX_SHIM: f"{OMLX_BUNDLE}/Contents/MacOS/omlx-cli",
            f"{HOME}/.local/bin/optiq": f"{OPTIQ_VENV}/bin/optiq",
        },
        dirs={OSAURUS_BUNDLE, OMLX_BUNDLE, VMLX_BUNDLE},
    )


def test_names_are_the_five_onboarding_engines_from_the_registry():
    names = [status.name for status in detect_all(FakeEnv())]
    assert names == ["mlxlm", "osaurus", "omlx", "optiq", "vmlx"]
    assert "mtplx" in RUNTIMES


def test_only_omlx_present_resolves_its_real_path_and_ignores_a_stale_osaurus_link():
    env = FakeEnv(
        files={f"{OMLX_BUNDLE}/Contents/Info.plist": app_plist("0.7.2")},
        links={
            OMLX_SHIM: f"{OMLX_BUNDLE}/Contents/MacOS/omlx-cli",
            # The cask-era link that survives the app it pointed at (research §6.2).
            "/opt/homebrew/bin/osaurus": "/Applications/osaurus.app/Contents/Helpers/osaurus",
        },
        dirs={OMLX_BUNDLE},
    )
    statuses = {status.name: status for status in detect_all(env)}
    assert statuses["omlx"].installed is True
    assert statuses["omlx"].path == f"{OMLX_BUNDLE}/Contents/MacOS/omlx-cli"
    assert [name for name, status in statuses.items() if status.installed] == ["omlx"]
    assert statuses["osaurus"].installed is False


def test_each_version_is_the_one_the_installed_files_carry():
    statuses = {status.name: status for status in detect_all(installed_env())}
    assert all(status.installed for status in statuses.values())
    assert {name: status.version for name, status in statuses.items()} == VERSIONS


@pytest.mark.parametrize("bundle", ["/Applications/osaurus.app", "/Applications/Osaurus.app"])
def test_osaurus_is_detected_under_either_bundle_spelling(bundle):
    """The DMG leaves `osaurus.app` and the cask's artifact is `Osaurus.app`; on a
    case-sensitive volume only one exists, and both are a real install."""
    env = FakeEnv(
        files={f"{bundle}/Contents/Info.plist": app_plist("0.25.29")},
        dirs={bundle},
    )

    statuses = {status.name: status for status in detect_all(env)}

    assert statuses["osaurus"].installed is True
    assert statuses["osaurus"].path == bundle
    assert statuses["osaurus"].version == "0.25.29"


def test_an_unreadable_version_file_leaves_version_none_and_installed_true():
    env = installed_env()
    env.files[f"{OSAURUS_BUNDLE}/Contents/Info.plist"] = PermissionError("denied")
    env.files[f"{MLXLM_VENV}/lib/python3.14/site-packages/mlx_lm/_version.py"] = (
        PermissionError("denied")
    )
    statuses = {status.name: status for status in detect_all(env)}
    assert statuses["osaurus"].installed is True
    assert statuses["osaurus"].version is None
    assert statuses["mlxlm"].installed is True
    assert statuses["mlxlm"].version is None


def test_tested_is_true_when_the_installed_versions_match_the_harness_table():
    statuses = detect_all(installed_env())
    assert [status.tested for status in statuses] == [True, True, True, True, True]


def test_tested_is_false_when_an_installed_version_differs():
    versions = {**VERSIONS, "omlx": "0.7.4", "mlxlm": "0.32.2"}
    statuses = {status.name: status for status in detect_all(installed_env(versions))}
    assert statuses["omlx"].version == "0.7.4"
    assert statuses["omlx"].tested is False
    assert statuses["mlxlm"].version == "0.32.2"
    assert statuses["mlxlm"].tested is False
    assert statuses["osaurus"].tested is True


def test_a_wheel_installed_optiq_reads_its_version_from_dist_info_metadata():
    base = f"{HOME}/Library/Application Support/OhYesMLX/engines/optiq"
    env = FakeEnv(
        files={
            f"{base}/bin/optiq": "#!/bin/sh\n",
            f"{base}/pyvenv.cfg": "version = 3.12.13\n",
            f"{base}/lib/python3.12/site-packages/mlx_optiq-0.7.8.dist-info/METADATA": (
                "Metadata-Version: 2.4\nName: mlx-optiq\nVersion: 0.7.8\n"
            ),
        },
    )
    optiq = {status.name: status for status in detect_all(env)}["optiq"]
    assert optiq.installed is True
    assert optiq.version == "0.7.8"
    assert optiq.tested is False


def test_app_engines_are_guided_downloads_with_a_page_then_a_verify_step():
    sources = {
        "osaurus": "https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29",
        "omlx": "https://github.com/jundot/omlx/releases/tag/v0.7.3",
        "vmlx": "https://github.com/jjang-ai/vmlx/releases/tag/v1.6.59",
    }
    for name, source_url in sources.items():
        plan = install_plan(name, 15)
        assert plan.engine == name
        assert plan.kind == "guided_download"
        assert plan.source_url == source_url
        assert [step.id for step in plan.steps] == ["open-page", "verify-install"]
        assert [step.command for step in plan.steps] == [None, None]
        assert "detected" in plan.steps[1].label


def test_guided_source_urls_pin_the_three_tested_releases_and_never_latest():
    """AC-3: the URL is the tested build's tag page, not whatever shipped last (139)."""
    assert install_plan("osaurus", 15).source_url == (
        "https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29"
    )
    assert install_plan("omlx", 26).source_url == (
        "https://github.com/jundot/omlx/releases/tag/v0.7.3"
    )
    assert install_plan("vmlx", 15).source_url == (
        "https://github.com/jjang-ai/vmlx/releases/tag/v1.6.59"
    )
    for name in ("osaurus", "omlx", "vmlx"):
        assert "/releases/latest" not in install_plan(name, 15).source_url


def test_a_tested_version_bump_moves_the_guided_url_with_no_other_edit(monkeypatch):
    prefixes = {"osaurus": "", "omlx": "v", "vmlx": "v"}
    for name, prefix in prefixes.items():
        monkeypatch.setitem(engines.TESTED_VERSIONS, name, "9.9.9")
        url = install_plan(name, 15).source_url
        assert url.endswith(f"/releases/tag/{prefix}9.9.9")


def test_mlxlm_plan_creates_the_pinned_venv_then_installs_the_tested_version():
    venv = f"{ENGINES_DIR}/mlxlm-0.31.3"
    plan = install_plan("mlxlm", 15)
    assert plan.engine == "mlxlm"
    assert plan.kind == "command"
    assert plan.source_url == "https://pypi.org/project/mlx-lm/"
    assert [step.command for step in plan.steps] == [
        ["{python}", "-m", "venv", venv],
        [
            f"{venv}/bin/python",
            "-m",
            "pip",
            "install",
            "--no-input",
            "--disable-pip-version-check",
            "mlx-lm==0.31.3",
            "-c",
            str(CONSTRAINTS / "mlxlm-0.31.3.txt"),
        ],
    ]
    assert (CONSTRAINTS / "mlxlm-0.31.3.txt").is_file()


def test_optiq_plan_creates_the_pinned_venv_then_installs_the_tested_version():
    venv = f"{ENGINES_DIR}/optiq-0.5.13"
    plan = install_plan("optiq", 15)
    assert plan.engine == "optiq"
    assert plan.kind == "command"
    assert plan.source_url == "https://pypi.org/project/mlx-optiq/"
    assert [step.command for step in plan.steps] == [
        ["{python}", "-m", "venv", venv],
        [
            f"{venv}/bin/python",
            "-m",
            "pip",
            "install",
            "--no-input",
            "--disable-pip-version-check",
            "mlx-optiq==0.5.13",
            # The constraints file pins mlx-lm for OptiQ, because OptiQ serves through
            # mlx_lm.server and does not pin it: unpinned, pip resolved mlx-lm 0.32.2 and
            # every chat request answered HTTP 404 (2026-10-30 lab copy).
            "-c",
            str(CONSTRAINTS / "optiq-0.5.13.txt"),
        ],
    ]
    install_argv = plan.steps[1].command
    assert (CONSTRAINTS / "optiq-0.5.13.txt").is_file()
    assert [token for token in install_argv if token.startswith("mlx-lm==")] == []


def test_a_tested_version_without_a_constraints_file_raises_before_a_plan_exists(monkeypatch):
    for name in engines._PIP_PACKAGES:
        monkeypatch.setitem(engines.TESTED_VERSIONS, name, "9.9.9")
        with pytest.raises(ValueError, match=rf"{name}-9\.9\.9\.txt"):
            install_plan(name, 15)


def test_every_pip_engine_has_a_constraints_file_for_its_tested_version():
    assert set(engines._PIP_PACKAGES) == {"mlxlm", "optiq"}
    for name in engines._PIP_PACKAGES:
        path = CONSTRAINTS / f"{name}-{engines.TESTED_VERSIONS[name]}.txt"
        assert path.is_file(), (
            f"{name} {engines.TESTED_VERSIONS[name]} has no constraints file at {path}; "
            "freeze the lab venv (docs/runtimes/lab-copies.md §4) with the bump"
        )


def test_omlx_asset_and_size_follow_the_macos_generation():
    assert install_plan("omlx", 15).size_bytes_estimate == 837_800_000
    assert "oMLX-<ver>-macos15-sequoia.dmg" in install_plan("omlx", 15).steps[0].label
    assert install_plan("omlx", 25).size_bytes_estimate == 837_800_000
    assert install_plan("omlx", 26).size_bytes_estimate == 875_200_000
    assert "oMLX-<ver>-macos26-27.dmg" in install_plan("omlx", 26).steps[0].label
    assert install_plan("omlx", 27).size_bytes_estimate == 875_200_000


def test_vmlx_asset_and_size_follow_the_macos_generation():
    assert install_plan("vmlx", 15).size_bytes_estimate == 579_000_000
    assert "vMLX-<ver>-sequoia-arm64.dmg" in install_plan("vmlx", 15).steps[0].label
    assert install_plan("vmlx", 26).size_bytes_estimate == 604_500_000
    assert "vMLX-<ver>-tahoe-arm64.dmg" in install_plan("vmlx", 26).steps[0].label


def test_osaurus_has_one_asset_and_one_size_on_every_macos():
    for macos_major in (15, 26):
        plan = install_plan("osaurus", macos_major)
        assert plan.size_bytes_estimate == 85_900_000
        assert "Osaurus.dmg" in plan.steps[0].label


def test_unknown_clean_install_sizes_are_none_not_a_guess():
    assert install_plan("mlxlm", 15).size_bytes_estimate is None
    assert install_plan("optiq", 15).size_bytes_estimate is None
    assert install_plan("mlxlm", 26).size_bytes_estimate is None
    assert install_plan("optiq", 26).size_bytes_estimate is None


def test_no_install_route_needs_an_admin_password():
    for name in ("mlxlm", "osaurus", "omlx", "optiq", "vmlx"):
        for macos_major in (15, 26):
            assert install_plan(name, macos_major).needs_admin is False


def test_an_engine_outside_the_onboarding_five_raises_value_error():
    with pytest.raises(ValueError, match="mtplx"):
        install_plan("mtplx", 15)
    with pytest.raises(ValueError, match="nonsense"):
        install_plan("nonsense", 26)


def test_plan_and_step_carry_the_pinned_frozen_fields():
    assert [field.name for field in fields(Plan)] == [
        "engine",
        "kind",
        "source_url",
        "size_bytes_estimate",
        "needs_admin",
        "steps",
    ]
    assert [field.name for field in fields(Step)] == ["id", "label", "command"]
    plan = install_plan("osaurus", 15)
    with pytest.raises(FrozenInstanceError):
        plan.kind = "command"
    with pytest.raises(FrozenInstanceError):
        plan.steps[0].label = "other"


def test_omlx_guided_step_tells_the_user_to_skip_release_candidates():
    plan = install_plan("omlx", 15)
    assert "not a release candidate" in plan.steps[0].label
    assert "release candidate" not in install_plan("osaurus", 15).steps[0].label


# ---------------------------------------------------------------------------
# engines.install -- the consent-gated installer (plan 02-03)
#
# Every side effect is a fake: run replays literal (code, output) pairs, detect
# answers from a script, hardware reports a literal free disk, and the lock, opener,
# emitter and sleep only record what they were handed.
# ---------------------------------------------------------------------------


class FakeRun:
    """The subprocess seam: records each call and replays the given results."""

    def __init__(self, results=None, on_call=None):
        self.calls = []
        self.results = list(results or [])
        self.on_call = on_call

    def __call__(self, argv, timeout, env):
        self.calls.append({"argv": list(argv), "timeout": timeout, "env": dict(env)})
        if self.on_call is not None:
            self.on_call(argv)
        return self.results.pop(0) if self.results else (0, "")


class FakeDetect:
    """Detection answers from a script; polling past the allowance is a test failure.

    The allowance is what a buggy poll loop (one without its timeout) trips over.
    """

    def __init__(self, engine, answers=(False,), limit=50):
        self.engine = engine
        self.answers = list(answers)
        self.last = self.answers[-1] if self.answers else False
        self.limit = limit
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls > self.limit:
            raise AssertionError("detect was polled past the timeout allowance")
        if self.answers:
            self.last = self.answers.pop(0)
        return [SimpleNamespace(name=self.engine, installed=self.last)]


class FakeLock:
    """The lock seam: records acquire/release and answers availability as given."""

    def __init__(self, available=True):
        self.available = available
        self.acquired = []
        self.released = []

    def acquire(self, engine):
        self.acquired.append(engine)
        return self.available

    def release(self, engine):
        self.released.append(engine)


def log_lines(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def do_install(tmp_path, engine="mlxlm", confirmed=True, *, run=None, detect=None,
               open_url=None, free_bytes=500 * 1024**3, lock=None, **overrides):
    """Call install with every side effect faked; return what the fakes observed."""
    events = []
    opened = []
    sleeps = []
    kwargs = dict(
        macos_major=15,
        run=run if run is not None else FakeRun(),
        open_url=open_url if open_url is not None else opened.append,
        emit=events.append,
        detect=detect if detect is not None else FakeDetect(engine),
        hardware=lambda: SimpleNamespace(disk_free_bytes=free_bytes),
        sleep=sleeps.append,
        log_path=str(tmp_path / "install-log.jsonl"),
        lock=lock if lock is not None else FakeLock(),
        python="/fake/python",
        engines_dir=str(tmp_path / "engines"),
        timeout_s=900,
    )
    kwargs.update(overrides)
    ok = install(engine, confirmed, **kwargs)
    return ok, events, opened, sleeps


def command_plan(root, steps):
    return Plan(
        engine="mlxlm",
        kind="command",
        source_url="https://pypi.org/project/mlx-lm/",
        size_bytes_estimate=None,
        needs_admin=False,
        steps=steps,
    )


def test_install_without_consent_runs_nothing_and_emits_its_refusal_then_done(tmp_path):
    def never(*args, **kwargs):
        raise AssertionError("no side effect may run without consent")

    ok, events, opened, sleeps = do_install(
        tmp_path, confirmed=False, run=never, detect=never, open_url=never,
        hardware=never, lock=never,
    )
    assert ok is False
    assert events == [
        {
            "seq": 1,
            "type": "error",
            "message": events[0]["message"],
            "fraction": None,
            "payload": {"code": "consent_required"},
        },
        {
            "seq": 2,
            "type": "done",
            "message": "install did not start",
            "fraction": None,
            "payload": None,
        },
    ]
    lines = log_lines(tmp_path / "install-log.jsonl")
    assert [line["type"] for line in lines] == ["error", "done"]
    assert lines[0]["code"] == "consent_required"
    assert lines[0]["engine"] == "mlxlm"
    assert lines[0]["confirmed"] is False


def test_install_of_a_name_outside_the_five_refuses_before_anything_runs(tmp_path):
    events = []

    def never(*args, **kwargs):
        raise AssertionError("nothing may run for an unknown engine")

    ok, events, opened, sleeps = do_install(
        tmp_path, engine="mtplx", run=never, detect=never, open_url=never,
        hardware=never, sleep=never, lock=never,
    )
    assert ok is False
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"]["code"] == "unknown_engine"
    assert "mtplx" in events[0]["message"]
    lines = log_lines(tmp_path / "install-log.jsonl")
    assert [line["type"] for line in lines] == ["error", "done"]
    assert lines[0]["engine"] == "mtplx"
    assert lines[0]["code"] == "unknown_engine"
    assert lines[0]["confirmed"] is True


def test_a_pip_engine_with_no_constraints_file_refuses_as_no_constraints(tmp_path, monkeypatch):
    """A known name whose tested build has no committed file is its own code, not internal."""
    def missing(name, major):
        raise ValueError(f"no pip constraints file for {name}: expected /nowhere.txt")

    def never(*args, **kwargs):
        raise AssertionError("nothing may run for a refused plan")

    monkeypatch.setattr(engines, "install_plan", missing)

    ok, events, opened, sleeps = do_install(
        tmp_path, run=never, detect=never, open_url=never, hardware=never,
        sleep=never, lock=never,
    )

    assert ok is False
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"]["code"] == "no_constraints"
    assert "no pip constraints file" in events[0]["message"]
    assert log_lines(tmp_path / "install-log.jsonl")[0]["code"] == "no_constraints"


def test_two_steps_run_in_order_with_progress_after_each_and_done_last(tmp_path):
    venv = f"{tmp_path}/engines/mlxlm-0.31.3"
    run = FakeRun([(0, "venv made"), (0, "installed")])
    ok, events, opened, sleeps = do_install(tmp_path, run=run)
    assert ok is True
    assert [call["argv"] for call in run.calls] == [
        ["/fake/python", "-m", "venv", venv],
        [
            f"{venv}/bin/python",
            "-m",
            "pip",
            "install",
            "--no-input",
            "--disable-pip-version-check",
            "mlx-lm==0.31.3",
            "-c",
            str(CONSTRAINTS / "mlxlm-0.31.3.txt"),
        ],
    ]
    assert [event["type"] for event in events] == ["progress", "progress", "done"]
    assert [event["fraction"] for event in events[:2]] == [0.5, 1.0]
    assert [event["payload"]["step"] for event in events[:2]] == [
        "create-venv",
        "install",
    ]
    assert events[-1]["seq"] == 3


# AC-0 (04-03b): a pip engine the app installed is an engine the harness can start. The venv
# lives under Application Support, where no shell exports it, so the install writes its bin
# directory into the machine-local lab-paths file the start commands' PATH is built from.


def test_a_successful_pip_install_records_its_venv_bin_and_engine_env_prefixes_it(tmp_path):
    """The install of the tested version leaves exactly its own entry, and PATH finds it."""
    from ohyesmlx import runtimes

    def create_venv(argv):
        if argv[1:3] == ["-m", "venv"]:
            (Path(argv[3]) / "bin").mkdir(parents=True, exist_ok=True)

    ok, events, _opened, _sleeps = do_install(
        tmp_path, engine="optiq", run=FakeRun(on_call=create_venv)
    )

    assert ok is True
    lab_paths = tmp_path / "lab-paths.json"
    assert json.loads(lab_paths.read_text()) == {
        "optiq": f"{tmp_path}/engines/optiq-0.5.13/bin"
    }
    assert not (tmp_path / "lab-paths.json.tmp").exists(), "the write is atomic"

    env = runtimes._engine_env(lab_paths_path=str(lab_paths))
    assert env["PATH"].split(os.pathsep)[0] == f"{tmp_path}/engines/optiq-0.5.13/bin"


def test_a_failed_pip_install_records_no_lab_path_and_keeps_the_others(tmp_path):
    """A step that failed installed nothing, so the PATH must not gain a directory."""
    (tmp_path / "lab-paths.json").write_text(
        json.dumps({"mlxlm": "/lab/mlx-lm/bin"}), encoding="utf-8"
    )
    failed, _events, _opened, _sleeps = do_install(
        tmp_path, engine="optiq", run=FakeRun([(0, "venv made"), (1, "boom")])
    )
    assert failed is False
    assert json.loads((tmp_path / "lab-paths.json").read_text()) == {
        "mlxlm": "/lab/mlx-lm/bin"
    }

    ok, _events, _opened, _sleeps = do_install(tmp_path, engine="optiq")
    assert ok is True
    assert json.loads((tmp_path / "lab-paths.json").read_text()) == {
        "mlxlm": "/lab/mlx-lm/bin",
        "optiq": f"{tmp_path}/engines/optiq-0.5.13/bin",
    }


@pytest.mark.parametrize("name", ["osaurus", "omlx", "vmlx"])
def test_record_lab_path_refuses_an_app_engine_and_writes_nothing(tmp_path, name):
    path = tmp_path / "lab-paths.json"

    with pytest.raises(ValueError, match="app engines are archived"):
        engines.record_lab_path(name, "/lab/bin", path=path)

    assert not path.exists()


def test_each_step_is_bounded_by_the_injected_timeout(tmp_path):
    run = FakeRun()
    do_install(tmp_path, run=run)
    assert [call["timeout"] for call in run.calls] == [900, 900]

    run = FakeRun()
    do_install(tmp_path / "second", run=run, timeout_s=12.5)
    assert [call["timeout"] for call in run.calls] == [12.5, 12.5]


def test_steps_run_with_a_hermetic_env_that_drops_pythonpath_and_pip(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/ambient/site-packages")
    monkeypatch.setenv("PIP_INDEX_URL", "https://ambient.example/simple")
    monkeypatch.setenv("PIP_NO_BUILD_ISOLATION", "1")
    monkeypatch.setenv("OHYESMLX_KEPT", "kept")
    run = FakeRun()
    do_install(tmp_path, run=run)
    assert len(run.calls) == 2
    for call in run.calls:
        assert "PYTHONPATH" not in call["env"]
        assert [key for key in call["env"] if key.startswith("PIP_")] == []
        assert call["env"]["OHYESMLX_KEPT"] == "kept"


def test_the_bundled_python_is_the_one_the_plan_creates_the_venv_with(tmp_path):
    run = FakeRun()
    do_install(tmp_path, run=run, python="/bundle/OhYesMLX/bin/python3")
    assert run.calls[0]["argv"] == [
        "/bundle/OhYesMLX/bin/python3",
        "-m",
        "venv",
        f"{tmp_path}/engines/mlxlm-0.31.3",
    ]
    default = inspect.signature(install).parameters["python"].default
    assert default == sys.executable


def test_an_already_installed_engine_is_refused_before_the_lock_or_a_step(tmp_path):
    run = FakeRun()
    lock = FakeLock()
    ok, events, opened, sleeps = do_install(
        tmp_path, detect=FakeDetect("mlxlm", [True]), run=run, lock=lock
    )
    assert ok is False
    assert run.calls == []
    assert lock.acquired == []
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"]["code"] == "already_installed"
    assert log_lines(tmp_path / "install-log.jsonl")[0]["code"] == "already_installed"


def test_a_held_lock_refuses_the_second_install_as_busy(tmp_path):
    run = FakeRun()
    lock = FakeLock(available=False)
    ok, events, opened, sleeps = do_install(tmp_path, run=run, lock=lock)
    assert ok is False
    assert run.calls == []
    assert lock.acquired == ["mlxlm"]
    assert lock.released == []
    assert [
        event["payload"]["code"] for event in events if event["type"] == "error"
    ] == ["busy"]


def test_a_running_install_releases_its_lock_at_the_end(tmp_path):
    lock = FakeLock()
    do_install(tmp_path, lock=lock)
    assert lock.acquired == ["mlxlm"]
    assert lock.released == ["mlxlm"]


def test_engine_locks_are_one_per_engine_and_release_returns_it():
    locks = EngineLocks()
    assert locks.acquire("mlxlm") is True
    assert locks.acquire("mlxlm") is False
    assert locks.acquire("optiq") is True
    locks.release("mlxlm")
    assert locks.acquire("mlxlm") is True


def test_a_known_size_needs_twice_its_estimate_free(tmp_path):
    run = FakeRun()
    ok, events, opened, sleeps = do_install(
        tmp_path, engine="osaurus",
        detect=FakeDetect("osaurus"),
        run=run,
        free_bytes=2 * 85_900_000 - 1,
    )
    assert ok is False
    assert opened == []
    assert [
        event["payload"]["code"] for event in events if event["type"] == "error"
    ] == ["low_disk"]

    ok, events, opened, sleeps = do_install(
        tmp_path / "enough", engine="osaurus",
        detect=FakeDetect("osaurus", [False, True]),
        free_bytes=2 * 85_900_000,
        poll_s=1.0, poll_timeout_s=10.0,
    )
    assert ok is True
    assert opened == ["https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29"]


def test_an_unknown_size_falls_back_to_a_two_gib_floor(tmp_path):
    ok, events, opened, sleeps = do_install(
        tmp_path, free_bytes=2 * 1024**3 - 1
    )
    assert ok is False
    assert [
        event["payload"]["code"] for event in events if event["type"] == "error"
    ] == ["low_disk"]

    run = FakeRun()
    ok, events, opened, sleeps = do_install(tmp_path / "exactly", run=run,
                                            free_bytes=2 * 1024**3)
    assert ok is True
    assert len(run.calls) == 2


def test_a_failing_step_stops_before_the_next_rolls_back_and_reports_the_tail(tmp_path, monkeypatch):
    venv = tmp_path / "engines" / "mlxlm-0.31.3"
    plan = command_plan(
        str(venv),
        [
            Step("create-venv", "make the venv", ["{python}", "-m", "venv", str(venv)]),
            Step("install", "install the wheel",
                 [f"{venv}/bin/python", "-m", "pip", "install", "mlx-lm==0.31.3"]),
            Step("verify", "check the server", [f"{venv}/bin/mlx_lm.server", "--help"]),
        ],
    )
    monkeypatch.setattr(engines, "install_plan", lambda name, major: plan)

    def create_venv(argv):
        if argv[1:3] == ["-m", "venv"]:
            (venv / "bin").mkdir(parents=True)
            (venv / "pyvenv.cfg").write_text("version = 3.12.13\n", encoding="utf-8")

    run = FakeRun([(0, ""), (1, "ERROR: no matching distribution")], on_call=create_venv)
    ok, events, opened, sleeps = do_install(tmp_path, run=run)

    assert ok is False
    assert [call["argv"][0] for call in run.calls] == ["/fake/python", f"{venv}/bin/python"]
    assert not venv.exists()
    assert (tmp_path / "engines").exists()
    assert [event["type"] for event in events] == ["progress", "error", "done"]
    failure = events[1]
    assert failure["payload"]["code"] == "step_failed"
    assert failure["payload"]["step"] == "install"
    assert failure["payload"]["output_tail"] == "ERROR: no matching distribution"
    assert events[-1]["type"] == "done"
    assert log_lines(tmp_path / "install-log.jsonl")[1]["step"] == "install"
    assert log_lines(tmp_path / "install-log.jsonl")[1]["exit_code"] == 1


def test_a_venv_that_existed_before_the_call_is_never_removed(tmp_path, monkeypatch):
    venv = tmp_path / "engines" / "mlxlm-0.31.3"
    venv.mkdir(parents=True)
    (venv / "keep.txt").write_text("pre-existing", encoding="utf-8")
    plan = command_plan(
        str(venv),
        [
            Step("create-venv", "make the venv", ["{python}", "-m", "venv", str(venv)]),
            Step("install", "install the wheel",
                 [f"{venv}/bin/python", "-m", "pip", "install", "mlx-lm==0.31.3"]),
        ],
    )
    monkeypatch.setattr(engines, "install_plan", lambda name, major: plan)
    run = FakeRun([(0, ""), (1, "boom")])
    ok, events, opened, sleeps = do_install(tmp_path, run=run)
    assert ok is False
    assert (venv / "keep.txt").read_text(encoding="utf-8") == "pre-existing"


def test_rollback_refuses_a_path_that_resolves_outside_the_engines_dir(tmp_path, monkeypatch):
    engines_dir = tmp_path / "engines"
    venv = engines_dir / "mlxlm-0.31.3"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("do not delete", encoding="utf-8")
    plan = command_plan(
        str(venv),
        [
            Step("create-venv", "make the venv", ["{python}", "-m", "venv", str(venv)]),
            Step("install", "install the wheel",
                 [f"{venv}/bin/python", "-m", "pip", "install", "mlx-lm==0.31.3"]),
        ],
    )
    monkeypatch.setattr(engines, "install_plan", lambda name, major: plan)

    def link_out(argv):
        if argv[1:3] == ["-m", "venv"]:
            engines_dir.mkdir(parents=True, exist_ok=True)
            os.symlink(outside, venv)

    run = FakeRun([(0, ""), (1, "boom")], on_call=link_out)
    ok, events, opened, sleeps = do_install(tmp_path, run=run)
    assert ok is False
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "do not delete"
    assert venv.is_symlink()
    refusals = [event for event in events if event["type"] == "log"]
    assert len(refusals) == 1
    assert "outside" in refusals[0]["message"]


def test_captured_output_is_capped_to_the_last_four_kilobytes(tmp_path):
    long_output = "x" * 5000 + "TAIL"
    run = FakeRun([(1, long_output)])
    ok, events, opened, sleeps = do_install(tmp_path, run=run)
    assert ok is False
    failure = [event for event in events if event["type"] == "error"][0]
    assert failure["payload"]["output_tail"] == long_output[-4096:]
    assert len(failure["payload"]["output_tail"]) == 4096


def test_every_event_appends_one_json_line_with_the_recorded_fields(tmp_path):
    do_install(tmp_path, run=FakeRun())
    do_install(tmp_path, confirmed=False)

    lines = log_lines(tmp_path / "install-log.jsonl")
    assert [line["type"] for line in lines] == ["progress", "progress", "done", "error", "done"]
    for line in lines:
        assert set(line) >= {"engine", "ts", "confirmed", "step", "exit_code", "type"}
        assert datetime.fromisoformat(line["ts"]).utcoffset().total_seconds() == 0
    assert [line["step"] for line in lines[:2]] == ["create-venv", "install"]
    assert [line["exit_code"] for line in lines[:2]] == [0, 0]
    assert lines[2]["step"] is None
    assert lines[2]["exit_code"] is None
    assert lines[3]["code"] == "consent_required"
    assert [line["confirmed"] for line in lines] == [True, True, True, False, False]


def test_the_install_log_is_created_under_a_new_parent_directory(tmp_path):
    log_path = tmp_path / "nested" / "deeper" / "install-log.jsonl"
    do_install(tmp_path, confirmed=False, log_path=str(log_path))
    assert [line["type"] for line in log_lines(log_path)] == ["error", "done"]


def test_no_plan_step_is_a_shell_string_and_none_uses_sudo():
    for name in ("mlxlm", "osaurus", "omlx", "optiq", "vmlx"):
        for step in install_plan(name, 15).steps:
            if step.command is None:
                continue
            assert isinstance(step.command, list)
            assert all(isinstance(token, str) for token in step.command)
            assert "sudo" not in step.command


def test_a_guided_plan_opens_the_https_page_then_polls_detect_until_installed(tmp_path):
    detect = FakeDetect("osaurus", [False, False, True])
    sleeps = []
    ok, events, opened, _ = do_install(
        tmp_path, engine="osaurus", detect=detect, sleep=sleeps.append,
        poll_s=1.0, poll_timeout_s=10.0,
    )
    assert ok is True
    assert opened == ["https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29"]
    assert detect.calls == 3
    assert sleeps == [1.0]
    assert [event["type"] for event in events] == ["result", "done"]
    assert events[0]["payload"] == {"installed": True}


def test_guided_polling_that_times_out_is_a_result_not_an_error(tmp_path):
    detect = FakeDetect("osaurus", [False], limit=10)
    sleeps = []
    ok, events, opened, _ = do_install(
        tmp_path, engine="osaurus", detect=detect, sleep=sleeps.append,
        poll_s=1.0, poll_timeout_s=3.0,
    )
    assert ok is False
    assert opened == ["https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29"]
    assert detect.calls == 4  # the pre-check plus three one-second polls
    assert sleeps == [1.0, 1.0, 1.0]
    assert [event["type"] for event in events] == ["result", "done"]
    assert events[0]["payload"] == {"installed": False}


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/osaurus.dmg",
        "http://github.com/osaurus-ai/osaurus/releases/latest",
    ],
)
def test_a_url_outside_the_https_allowlist_is_refused_before_the_opener(tmp_path, monkeypatch, url):
    plan = Plan(
        engine="osaurus",
        kind="guided_download",
        source_url=url,
        size_bytes_estimate=1,
        needs_admin=False,
        steps=[Step("open-page", "open", None), Step("verify-install", "verify", None)],
    )
    monkeypatch.setattr(engines, "install_plan", lambda name, major: plan)
    ok, events, opened, sleeps = do_install(
        tmp_path, engine="osaurus", detect=FakeDetect("osaurus")
    )
    assert ok is False
    assert opened == []
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"]["code"] == "url_not_allowed"


def test_the_output_cap_is_four_kilobytes_of_bytes_not_four_thousand_characters(tmp_path):
    run = FakeRun([(1, "\u2713" * 5000)])
    ok, events, opened, sleeps = do_install(tmp_path, run=run)
    failure = [event for event in events if event["type"] == "error"][0]
    tail = failure["payload"]["output_tail"]
    assert len(tail.encode("utf-8")) <= 4096
    assert tail.endswith("\u2713")


def test_a_stray_pyproject_above_a_non_venv_script_does_not_set_optiq_version():
    site = f"{HOME}/.local/lib/python3.12/site-packages"
    env = FakeEnv(
        files={
            f"{HOME}/.local/bin/optiq": "#!/bin/sh\n",
            f"{HOME}/.local/pyvenv.cfg": "version = 3.12.13\n",
            f"{site}/mlx_optiq-0.7.8.dist-info/METADATA": "Name: mlx-optiq\nVersion: 0.7.8\n",
            f"{HOME}/pyproject.toml": '[project]\nversion = "1.2.3"\n',
        },
    )
    optiq = {status.name: status for status in detect_all(env)}["optiq"]
    assert optiq.version == "0.7.8"


# --------------------------------------------------------------------------------------
# The tested-versions manifest (plan 025-01)
# --------------------------------------------------------------------------------------
#
# `ohyesmlx/engines-tested.json` is the one place an engine's tested version is written. The
# loader takes a path, so every shape error is driven here without touching the shipped
# file; every expectation below is a literal, never computed from the code under test.

MANIFEST = {
    "mlxlm": {"version": "0.31.3", "verified": "2026-10-29", "lab_path": None, "canary": None},
    "osaurus": {"version": "0.25.28", "verified": "2026-10-29", "lab_path": None, "canary": None},
    "omlx": {"version": "0.7.2", "verified": "2026-10-29", "lab_path": None, "canary": None},
    "optiq": {"version": "0.5.13", "verified": "2026-10-29", "lab_path": None, "canary": None},
    "vmlx": {"version": "1.6.59", "verified": "2026-10-29", "lab_path": None, "canary": None},
}


def write_manifest(tmp_path, payload):
    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(payload))
    return path


def test_a_manifest_missing_an_engine_is_refused_naming_the_engine_and_the_file(tmp_path):
    payload = {name: dict(entry) for name, entry in MANIFEST.items()}
    del payload["omlx"]
    path = write_manifest(tmp_path, payload)
    with pytest.raises(ValueError) as raised:
        engines.load_manifest(path)
    assert "omlx" in str(raised.value)
    assert str(path) in str(raised.value)


def test_a_manifest_with_an_unknown_engine_is_refused_naming_it(tmp_path):
    payload = {name: dict(entry) for name, entry in MANIFEST.items()}
    payload["mtplx"] = {"version": "3.1.0", "verified": "2026-10-29", "lab_path": None, "canary": None}
    path = write_manifest(tmp_path, payload)
    with pytest.raises(ValueError, match="mtplx"):
        engines.load_manifest(path)


def test_a_non_string_version_is_refused_naming_the_engine_and_the_field(tmp_path):
    payload = {name: dict(entry) for name, entry in MANIFEST.items()}
    payload["optiq"]["version"] = 0.5
    path = write_manifest(tmp_path, payload)
    with pytest.raises(ValueError) as raised:
        engines.load_manifest(path)
    assert "optiq" in str(raised.value)
    assert "version" in str(raised.value)


def test_a_missing_manifest_is_refused_naming_the_file(tmp_path):
    path = tmp_path / "absent.json"
    with pytest.raises(ValueError) as raised:
        engines.load_manifest(path)
    assert str(path) in str(raised.value)


def test_tested_versions_are_the_manifest_literals():
    assert engines.TESTED_VERSIONS == VERSIONS


def test_tested_versions_are_derived_from_the_loaded_manifest():
    assert {
        name: entry["version"] for name, entry in engines.MANIFEST.items()
    } == engines.TESTED_VERSIONS


def test_the_shipped_manifest_carries_the_versions_the_tests_expect():
    payload = json.loads(engines.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert {name: entry["version"] for name, entry in payload.items()} == VERSIONS
    assert {name: entry["verified"] for name, entry in payload.items()} == VERIFIED


def test_no_engine_version_literal_remains_in_the_module():
    source = Path(engines.__file__).read_text(encoding="utf-8")
    for name, version in VERSIONS.items():
        assert version not in source, f"{name}'s {version} is still a literal in engines.py"


# --------------------------------------------------------------------------------------
# The manifest's canary block (plan 025-02)
# --------------------------------------------------------------------------------------
#
# One cell per engine, committed and portable: the format and the HF repo id are pinned, and
# the baseline is null until a `--record` run on a quiet machine writes it.


def shipped_manifest():
    """A deep copy of the shipped manifest, so a test can break one field of one entry."""
    return json.loads(json.dumps(engines.MANIFEST))


def test_the_shipped_manifest_names_one_canary_cell_per_engine():
    payload = json.loads(engines.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert {
        name: (entry["canary"]["format"], entry["canary"]["repo"])
        for name, entry in payload.items()
    } == {
        "mlxlm": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit"),
        # Osaurus has no stock4bit cell in the grid, so its canary is the oq4 one it has.
        "osaurus": ("oq4", "RepublicOfKorokke/Qwen3.5-4B-oQ4"),
        "omlx": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit"),
        "optiq": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit"),
        "vmlx": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit"),
    }
    assert {entry["canary"]["workload"] for entry in payload.values()} == {"decode"}


def test_the_shipped_manifest_pins_each_engines_canary_cell():
    # The cell is the manifest's contract; the baseline numbers beside it change every time
    # `canary --record` runs, so they are deliberately not asserted here.
    payload = json.loads(engines.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert {
        name: (entry["canary"]["format"], entry["canary"]["repo"], entry["canary"]["workload"])
        for name, entry in payload.items()
    } == {
        "mlxlm": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit", "decode"),
        "osaurus": ("oq4", "RepublicOfKorokke/Qwen3.5-4B-oQ4", "decode"),
        "omlx": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit", "decode"),
        "optiq": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit", "decode"),
        "vmlx": ("stock4bit", "mlx-community/Qwen3.5-4B-4bit", "decode"),
    }


def test_a_canary_spec_missing_a_field_is_refused_naming_the_engine_and_the_field(tmp_path):
    payload = shipped_manifest()
    del payload["vmlx"]["canary"]["decode_tok_s"]
    path = write_manifest(tmp_path, payload)

    with pytest.raises(ValueError) as raised:
        engines.load_manifest(path)

    assert "vmlx" in str(raised.value)
    assert "decode_tok_s" in str(raised.value)


def test_a_canary_spec_with_a_non_numeric_baseline_is_refused(tmp_path):
    payload = shipped_manifest()
    payload["optiq"]["canary"]["ttft_s"] = "0.40"
    path = write_manifest(tmp_path, payload)

    with pytest.raises(ValueError) as raised:
        engines.load_manifest(path)

    assert "optiq" in str(raised.value)
    assert "ttft_s" in str(raised.value)


def test_a_canary_spec_with_no_cell_is_refused(tmp_path):
    payload = shipped_manifest()
    payload["omlx"]["canary"]["repo"] = None
    path = write_manifest(tmp_path, payload)

    with pytest.raises(ValueError) as raised:
        engines.load_manifest(path)

    assert "omlx" in str(raised.value)
    assert "repo" in str(raised.value)


def test_a_canary_spec_that_is_not_an_object_is_refused(tmp_path):
    payload = shipped_manifest()
    payload["mlxlm"]["canary"] = "stock4bit"
    path = write_manifest(tmp_path, payload)

    with pytest.raises(ValueError, match="non-object 'canary'"):
        engines.load_manifest(path)


def test_engine_status_exposes_the_manifests_verified_date():
    """The date belongs to the table, not to the install: an engine that is absent, or
    present at another build, is still tested against the manifest's own record."""
    for env in (FakeEnv(), installed_env()):
        assert {status.name: status.verified for status in detect_all(env)} == {
            name: entry["verified"] for name, entry in engines.MANIFEST.items()
        }


def test_a_drifted_version_is_untested_and_still_carries_the_verified_date():
    versions = {**VERSIONS, "vmlx": "1.6.82"}
    statuses = {status.name: status for status in detect_all(installed_env(versions))}
    assert statuses["vmlx"].version == "1.6.82"
    assert statuses["vmlx"].tested is False
    assert statuses["vmlx"].verified == "2026-10-29"


# --------------------------------------------------------------------------------------
# The machine-local lab paths (plan 025-03, Task 2)
# --------------------------------------------------------------------------------------
#
# A lab path is machine-specific, so the committed manifest ships `lab_path: null`
# everywhere and a real one is written to `~/Library/Application Support/OhYesMLX/`
# `lab-paths.json` instead. One loader in `engines.py` reads it; the harness's PATH prefix
# and detection both ask it. Every expectation below is a literal.

LAB_PATHS_FILE = f"{HOME}/Library/Application Support/OhYesMLX/lab-paths.json"


def write_lab_paths(tmp_path, payload):
    path = tmp_path / "lab-paths.json"
    path.write_text(json.dumps(payload))
    return path


def test_no_lab_paths_file_means_no_lab_copies(tmp_path):
    assert engines.lab_paths(tmp_path / "absent.json") == {}


def test_a_lab_paths_file_is_the_engine_to_bin_directory_map_it_holds(tmp_path):
    path = write_lab_paths(
        tmp_path,
        {
            "mlxlm": "/Users/test/lab/mlx-lm-0.31.3/bin",
            "optiq": "/Users/test/lab/optiq-0.5.13/bin",
        },
    )
    assert engines.lab_paths(path) == {
        "mlxlm": "/Users/test/lab/mlx-lm-0.31.3/bin",
        "optiq": "/Users/test/lab/optiq-0.5.13/bin",
    }


def test_a_lab_paths_file_that_is_not_json_is_refused_naming_the_file(tmp_path):
    path = tmp_path / "lab-paths.json"
    path.write_text("{not json")
    with pytest.raises(ValueError) as raised:
        engines.lab_paths(path)
    assert str(path) in str(raised.value)


def test_a_lab_paths_key_outside_the_five_engines_is_refused_naming_the_key(tmp_path):
    path = write_lab_paths(tmp_path, {"mtplx": "/Users/test/lab/mtplx/bin"})
    with pytest.raises(ValueError) as raised:
        engines.lab_paths(path)
    assert "mtplx" in str(raised.value)
    assert str(path) in str(raised.value)


@pytest.mark.parametrize("name", ["osaurus", "omlx", "vmlx"])
def test_a_lab_path_for_an_app_engine_is_refused(tmp_path, name):
    path = write_lab_paths(tmp_path, {name: "/Users/test/lab/bin"})
    with pytest.raises(ValueError, match="app engines are archived, not run from a lab path"):
        engines.lab_paths(path)


def test_a_lab_path_that_is_not_a_string_is_refused_naming_the_key(tmp_path):
    path = write_lab_paths(tmp_path, {"optiq": 5})
    with pytest.raises(ValueError) as raised:
        engines.lab_paths(path)
    assert "optiq" in str(raised.value)


# A canary of a lab copy must record the lab copy's version. Detection reads the global
# install otherwise, so each of these two puts a *different* build at a lab path than the
# one `installed_env` has globally and checks which one is reported.

LAB_OPTIQ_VENV = f"{HOME}/lab/optiq-0.4.2"
LAB_MLXLM_VENV = f"{HOME}/lab/mlx-lm-0.30.0"


def test_a_lab_path_for_optiq_reports_the_lab_copys_version_and_path():
    env = installed_env()
    env.files.update(
        {
            LAB_PATHS_FILE: json.dumps({"optiq": f"{LAB_OPTIQ_VENV}/bin"}),
            f"{LAB_OPTIQ_VENV}/bin/optiq": "#!/bin/sh\n",
            f"{LAB_OPTIQ_VENV}/pyvenv.cfg": "version_info = 3.12.13\n",
            f"{LAB_OPTIQ_VENV}/lib/python3.12/site-packages/"
            "mlx_optiq-0.4.2.dist-info/METADATA": (
                "Metadata-Version: 2.4\nName: mlx-optiq\nVersion: 0.4.2\n"
            ),
        }
    )
    optiq = {status.name: status for status in detect_all(env)}["optiq"]
    assert optiq.installed is True
    assert optiq.path == f"{LAB_OPTIQ_VENV}/bin/optiq"
    assert optiq.version == "0.4.2"
    assert optiq.tested is False


def test_a_lab_path_for_mlxlm_reports_the_lab_copys_version_and_path():
    env = installed_env()
    env.files.update(
        {
            LAB_PATHS_FILE: json.dumps({"mlxlm": f"{LAB_MLXLM_VENV}/bin"}),
            f"{LAB_MLXLM_VENV}/bin/mlx_lm.server": "#!/bin/sh\n",
            f"{LAB_MLXLM_VENV}/pyvenv.cfg": "version = 3.14.7\n",
            f"{LAB_MLXLM_VENV}/lib/python3.14/site-packages/mlx_lm/_version.py": (
                '__version__ = "0.30.0"\n'
            ),
        }
    )
    mlxlm = {status.name: status for status in detect_all(env)}["mlxlm"]
    assert mlxlm.installed is True
    assert mlxlm.path == f"{LAB_MLXLM_VENV}/bin/mlx_lm.server"
    assert mlxlm.version == "0.30.0"
    assert mlxlm.tested is False


def test_with_no_lab_paths_file_detection_still_reads_the_global_installs():
    statuses = {status.name: status for status in detect_all(installed_env())}
    assert statuses["optiq"].path == f"{OPTIQ_VENV}/bin/optiq"
    assert statuses["optiq"].version == "0.5.13"
    assert statuses["mlxlm"].path == f"{MLXLM_VENV}/bin/mlx_lm.server"
    assert statuses["mlxlm"].version == "0.31.3"


def test_a_lab_path_with_nothing_at_it_falls_through_to_the_global_install():
    env = installed_env()
    env.files[LAB_PATHS_FILE] = json.dumps({"optiq": f"{HOME}/lab/gone/bin"})
    optiq = {status.name: status for status in detect_all(env)}["optiq"]
    assert optiq.path == f"{OPTIQ_VENV}/bin/optiq"
    assert optiq.version == "0.5.13"


def test_detection_refuses_a_lab_path_for_an_app_engine():
    env = installed_env()
    env.files[LAB_PATHS_FILE] = json.dumps({"osaurus": f"{HOME}/lab/osaurus.app"})
    with pytest.raises(ValueError, match="app engines are archived"):
        detect_all(env)


def test_detection_refuses_a_lab_paths_file_that_is_not_json():
    env = installed_env()
    env.files[LAB_PATHS_FILE] = "{not json"
    with pytest.raises(ValueError) as raised:
        detect_all(env)
    assert LAB_PATHS_FILE in str(raised.value)


# ---------------------------------------------------------------------------
# engines.install -- cancelling (plan 04-02, AC-5)
#
# A cancel is only ever noticed between steps and between guided polls: a running pip step
# keeps its own timeout, and the rollback removes what this call created before it stops.
# ---------------------------------------------------------------------------


def test_cancel_before_the_second_step_rolls_back_the_first(tmp_path, monkeypatch):
    venv = tmp_path / "engines" / "mlxlm-0.31.3"
    plan = command_plan(
        str(venv),
        [
            Step("create-venv", "make the venv", ["{python}", "-m", "venv", str(venv)]),
            Step("install", "install the wheel",
                 [f"{venv}/bin/python", "-m", "pip", "install", "mlx-lm==0.31.3"]),
        ],
    )
    monkeypatch.setattr(engines, "install_plan", lambda name, major: plan)

    def create_venv(argv):
        if argv[1:3] == ["-m", "venv"]:
            (venv / "bin").mkdir(parents=True)
            (venv / "pyvenv.cfg").write_text("version = 3.12.13\n", encoding="utf-8")

    run = FakeRun(on_call=create_venv)
    ok, events, opened, sleeps = do_install(
        tmp_path, run=run, cancel=lambda: len(run.calls) >= 1
    )

    assert ok is False
    assert len(run.calls) == 1, "the step after the cancel must not run"
    assert not venv.exists(), "the venv step 1 created was not rolled back"
    assert [event["type"] for event in events] == ["progress", "error", "done"]
    assert events[1]["payload"] == {"code": "cancelled"}
    assert events[-1]["type"] == "done"


def test_cancel_during_the_guided_poll_ends_within_one_poll(tmp_path):
    detect = FakeDetect("osaurus", [False], limit=10)
    sleeps = []
    probes = []

    def cancel():
        probes.append(True)
        return len(probes) > 1

    ok, events, opened, _ = do_install(
        tmp_path, engine="osaurus", detect=detect, sleep=sleeps.append,
        poll_s=1.0, poll_timeout_s=10.0, cancel=cancel,
    )

    assert ok is False
    assert sleeps == [1.0], "the cancel was noticed after more than one poll"
    assert detect.calls == 2, "the already-installed check plus one poll"
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"] == {"code": "cancelled"}
    assert opened == ["https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29"]


# --- plan 045-02a AC-5: the guided-download opener names its tool absolutely ------------------


def test_a_guided_download_opens_the_page_with_the_absolute_opener(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((list(argv), kwargs))

    monkeypatch.setattr(engines.subprocess, "run", run)

    engines._real_open("https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29")

    assert engines.OPEN == "/usr/bin/open"
    assert calls == [
        (
            [engines.OPEN, "https://github.com/osaurus-ai/osaurus/releases/tag/0.25.29"],
            {"check": False, "stdin": engines.subprocess.DEVNULL},
        )
    ]


# --- plan 045-02a AC-6: an install step runs in its own, registered process group ------------


class FakeStepProcess:
    """The `Popen` one install step makes: answers output, or one timeout."""

    def __init__(self, *, times_out=False):
        self.pid = 9001
        self.returncode = 0
        self.times_out = times_out
        self.communicates = 0

    def communicate(self, timeout=None):
        self.communicates += 1
        assert self in engines._RUNNING_STEPS, "the step was not registered while it ran"
        if self.times_out and self.communicates == 1:
            raise subprocess.TimeoutExpired(cmd=[], timeout=timeout, output="half ")
        return ("finished", "")


def test_a_step_runs_in_its_own_session_and_leaves_the_registry_empty(monkeypatch):
    proc = FakeStepProcess()
    seen = {}

    def popen(argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return proc

    monkeypatch.setattr(engines.subprocess, "Popen", popen)

    code, output = engines._real_run(["pip", "install", "x"], 5, {"A": "b"})

    assert (code, output) == (0, "finished")
    assert seen["argv"] == ["pip", "install", "x"]
    assert seen["kwargs"]["start_new_session"] is True
    assert seen["kwargs"]["env"] == {"A": "b"}
    assert engines._RUNNING_STEPS == set()


def test_a_step_that_times_out_kills_its_group_and_reports_the_timeout(monkeypatch):
    proc = FakeStepProcess(times_out=True)
    killed = []
    monkeypatch.setattr(engines.subprocess, "Popen", lambda argv, **kwargs: proc)
    monkeypatch.setattr(engines.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    code, output = engines._real_run(["pip", "install", "x"], 1, {})

    assert code == engines.TIMEOUT_EXIT_CODE
    assert killed == [(9001, signal.SIGKILL)]
    assert output == "half "
    assert engines._RUNNING_STEPS == set()


def test_kill_running_steps_kills_every_registered_group(monkeypatch):
    first, second = FakeStepProcess(), FakeStepProcess()
    first.pid, second.pid = 9001, 9002
    monkeypatch.setattr(engines, "_RUNNING_STEPS", {first, second})
    killed = []
    monkeypatch.setattr(engines.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    engines.kill_running_steps()

    assert sorted(killed) == [(9001, signal.SIGKILL), (9002, signal.SIGKILL)]


def test_the_step_lock_is_held_across_popen_and_the_registration(monkeypatch):
    """045-02a AC-6, review 3: `kill_running_steps` must never snapshot the registry in the
    window between a step's spawn and its registration."""
    seen = {}

    class ProbeStep:
        pid = 9100
        returncode = 0

        def __init__(self, *args, **kwargs):
            seen["lock_held"] = engines._RUNNING_STEPS_LOCK.locked()

        def communicate(self, timeout=None):
            return ("", "")

    monkeypatch.setattr(engines.subprocess, "Popen", ProbeStep)

    code, _output = engines._real_run(["pip", "install", "x"], 5, {})

    assert code == 0
    assert seen["lock_held"] is True, "the spawn ran outside the registration lock"


def test_a_kill_started_while_a_step_is_spawning_waits_for_and_kills_it(monkeypatch):
    popen_entered = threading.Event()
    release = threading.Event()
    killed = []

    class SlowStep:
        pid = 9101
        returncode = 0

        def __init__(self, *args, **kwargs):
            popen_entered.set()
            release.wait(5)

        def communicate(self, timeout=None):
            return ("", "")

    monkeypatch.setattr(engines.subprocess, "Popen", SlowStep)
    monkeypatch.setattr(engines, "_RUNNING_STEPS", set())
    monkeypatch.setattr(engines, "_RUNNING_STEPS_LOCK", threading.Lock())
    monkeypatch.setattr(engines.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    runner = threading.Thread(
        target=engines._real_run, args=(["pip", "install", "x"], 5, {})
    )
    runner.start()
    assert popen_entered.wait(5), "the step never started"

    killer = threading.Thread(target=engines.kill_running_steps)
    killer.start()
    deadline = time.monotonic() + 1
    while killer.is_alive() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert killer.is_alive(), "kill_running_steps snapped the registry before registration"

    release.set()
    runner.join(5)
    killer.join(5)

    assert killed == [(9101, signal.SIGKILL)]
