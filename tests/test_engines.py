"""Checks for ohyesmlx.engines.

Every check drives ``detect_all`` through a fake filesystem: ``files`` maps a path to
the literal text at it (or to the exception reading it raises), ``links`` maps a path
to the target ``realpath`` follows, and ``dirs`` are empty directories. Nothing is
launched, no real file is read, and no expected value is computed from the code under
test.
"""

from __future__ import annotations

from ohyesmlx.engines import detect_all
from ohyesmlx.runtimes import RUNTIMES

HOME = "/Users/test"

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
