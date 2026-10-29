"""Checks for ohyesmlx.engines.

Every check drives ``detect_all`` through a fake filesystem: ``files`` maps a path to
the literal text at it (or to the exception reading it raises), ``links`` maps a path
to the target ``realpath`` follows, and ``dirs`` are empty directories. Nothing is
launched, no real file is read, and no expected value is computed from the code under
test.
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError, fields

import pytest

from ohyesmlx.engines import Plan, Step, detect_all, install_plan
from ohyesmlx.runtimes import RUNTIMES

HOME = "/Users/test"

# install_plan takes no env: the venv it names is under the real user's home.
ENGINES_DIR = os.path.expanduser("~/Library/Application Support/OhYesMLX/engines")

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
    "osaurus": "0.25.28",
    "omlx": "0.7.2",
    "optiq": "0.5.13",
    "mlxlm": "0.31.3",
    "vmlx": "1.6.59",
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
    versions = {**VERSIONS, "omlx": "0.7.3", "mlxlm": "0.32.2"}
    statuses = {status.name: status for status in detect_all(installed_env(versions))}
    assert statuses["omlx"].version == "0.7.3"
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
        "osaurus": "https://github.com/osaurus-ai/osaurus/releases/latest",
        "omlx": "https://github.com/jundot/omlx/releases",
        "vmlx": "https://github.com/jjang-ai/vmlx/releases/latest",
    }
    for name, source_url in sources.items():
        plan = install_plan(name, 15)
        assert plan.engine == name
        assert plan.kind == "guided_download"
        assert plan.source_url == source_url
        assert [step.id for step in plan.steps] == ["open-page", "verify-install"]
        assert [step.command for step in plan.steps] == [None, None]
        assert "detected" in plan.steps[1].label


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
        ],
    ]


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
        ],
    ]


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
