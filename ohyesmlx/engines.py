"""Which serving engines this Mac has, and at what version, without starting one.

The Engines screen's first question is answered here and nowhere else: is Osaurus,
oMLX, OptiQ, mlx-lm or vMLX installed, at what version, and where does it really live?
``detect_all(env)`` takes every side effect as a parameter, the way ``hardware.scan``
takes its commands -- *env* offers ``exists(path)``, ``read_text(path)``,
``listdir(path)``, ``realpath(path)`` and ``home`` -- so the detection is checked against a fixture
filesystem and this machine is one default away.

Two rules shape every probe below, both paid for in
``docs/research/2026-10-29-engine-install-paths.md``:

- **A version is a file the install wrote, never a process.** ``vmlx --version`` exits 2
  (§5.4) and Osaurus's flags can start or stop a server (§1.4), so the version comes
  from ``CFBundleShortVersionString`` or from ``__version__`` in a Python file.
- **Presence is a file test over known locations, never PATH alone.** Four of the five
  names sit in directories a fresh Mac does not export (§6.2), and
  ``/opt/homebrew/bin/osaurus`` outlives the app it pointed at, so a ``which`` hit is
  not an install.

``install_plan(name, macos_major)`` answers the screen's second question -- what installing
an engine would do -- as data, so the user can see the source, the size and every step
before anything runs. Detection leaves ``EngineStatus.install`` ``None``; the server
composes the two in Phase 4.
"""

from __future__ import annotations

import os
import pathlib
import plistlib
import re
from dataclasses import dataclass
from xml.parsers.expat import ExpatError

from ohyesmlx.runtimes import RUNTIMES, VMLX_ENGINE_INIT

# The five engines of Decision D2, in the registry's own order. MTPLX joins when its
# branch lands; until then its registry entry is filtered out rather than probed.
ONBOARDING_ENGINES = ("mlxlm", "osaurus", "omlx", "optiq", "vmlx")

# What this harness has measured against, and the one place those literals live
# (research §6.3): a different installed version is reported untested, never assumed
# equivalent, because every start command and refusal is written against these builds.
TESTED_VERSIONS = {
    "mlxlm": "0.31.3",
    "osaurus": "0.25.28",
    "omlx": "0.7.2",
    "optiq": "0.5.13",
    "vmlx": "1.6.59",
}

_TITLES = {
    "mlxlm": "mlx-lm",
    "osaurus": "Osaurus",
    "omlx": "oMLX",
    "optiq": "OptiQ",
    "vmlx": "vMLX",
}

_BLURBS = {
    "mlxlm": "Apple's reference MLX server, and this harness's control.",
    "osaurus": "Native menubar app with its own MLX engine.",
    "omlx": "Menubar app that bundles its own Python and MLX.",
    "optiq": "Python package that serves quantized models through the optiq CLI.",
    "vmlx": "Desktop app with a bundled Python engine and an OpenAI-compatible server.",
}


@dataclass(frozen=True)
class Step:
    """One thing an install plan asks for; a human performs the ones with no command."""

    id: str
    label: str
    command: list[str] | None  # argv to run, or None for a step the user takes


@dataclass(frozen=True)
class Plan:
    """What installing one engine would do, as data the consent screen renders."""

    engine: str
    kind: str  # "guided_download" | "command"
    source_url: str
    size_bytes_estimate: int | None  # the DOWNLOAD, and None where the research says UNKNOWN
    needs_admin: bool
    steps: list[Step]


@dataclass(frozen=True)
class EngineStatus:
    name: str
    title: str
    blurb: str
    installed: bool
    version: str | None
    path: str | None
    tested: bool
    install: Plan | None  # install_plan's answer; the server composes them in Phase 4


class _Filesystem:
    """The real filesystem, read-only: the default for every side effect above."""

    home = os.path.expanduser("~")

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_text(self, path: str) -> str:
        return pathlib.Path(path).read_text(encoding="utf-8")

    def listdir(self, path: str) -> list[str]:
        return os.listdir(path)

    def realpath(self, path: str) -> str:
        return os.path.realpath(path)


DEFAULT_ENV = _Filesystem()

_APPLICATIONS = "/Applications"

# The two ways a Python package assigns its version: mlx-lm writes
# `mlx_lm/_version.py`, vMLX's engine writes `vmlx_engine/__init__.py`.
_ASSIGNED_VERSION = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

# A venv records the interpreter it was made with here -- `version` from the stdlib's
# venv, `version_info` from uv -- which is how site-packages is found under `lib/`
# without listing a directory.
_VENV_PYTHON = re.compile(r"^\s*version(?:_info)?\s*=\s*(\d+\.\d+)", re.MULTILINE)


def _read_or_none(env, path: str) -> str | None:
    try:
        return env.read_text(path)
    except (OSError, ValueError):
        return None


def _plist_version(env, bundle: str) -> str | None:
    """``CFBundleShortVersionString``, or None when the plist is absent or unreadable."""
    text = _read_or_none(env, f"{bundle}/Contents/Info.plist")
    if text is None:
        return None
    try:
        plist = plistlib.loads(text.encode())
    except (ValueError, ExpatError):
        return None
    version = plist.get("CFBundleShortVersionString")
    return str(version) if version else None


def _module_version(env, path: str) -> str | None:
    """The literal assigned to ``__version__`` in *path*, or None."""
    text = _read_or_none(env, path)
    if text is None:
        return None
    match = _ASSIGNED_VERSION.search(text)
    return match.group(1) if match else None


def _venv_package_version(env, script: str, package: str, filename: str) -> str | None:
    """The version file under the venv *script* lives in, or None."""
    root = os.path.dirname(os.path.dirname(env.realpath(script)))
    config = _read_or_none(env, os.path.join(root, "pyvenv.cfg"))
    if config is None:
        return None
    python = _VENV_PYTHON.search(config)
    if python is None:
        return None
    return _module_version(
        env,
        os.path.join(
            root, "lib", f"python{python.group(1)}", "site-packages", package, filename
        ),
    )


_PYPROJECT_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_METADATA_VERSION = re.compile(r"^Version:\s*(\S+)", re.MULTILINE)


def _optiq_version(env, script: str) -> str | None:
    """OptiQ computes its version at import, so no file carries a literal.

    An editable checkout keeps the truth in the pyproject beside ``.venv`` (its installed
    metadata goes stale, per OptiQ's own ``_resolve_version``); a wheel install keeps it in
    ``mlx_optiq-<version>.dist-info/METADATA``.
    """
    root = os.path.dirname(os.path.dirname(env.realpath(script)))
    pyproject = _read_or_none(env, os.path.join(os.path.dirname(root), "pyproject.toml"))
    if pyproject is not None:
        match = _PYPROJECT_VERSION.search(pyproject)
        if match:
            return match.group(1)
    config = _read_or_none(env, os.path.join(root, "pyvenv.cfg"))
    python = _VENV_PYTHON.search(config) if config else None
    if python is None:
        return None
    site = os.path.join(root, "lib", f"python{python.group(1)}", "site-packages")
    try:
        names = env.listdir(site)
    except OSError:
        return None
    for name in names:
        if name.startswith("mlx_optiq-") and name.endswith(".dist-info"):
            metadata = _read_or_none(env, os.path.join(site, name, "METADATA"))
            match = _METADATA_VERSION.search(metadata) if metadata else None
            return match.group(1) if match else None
    return None


def _first_existing(env, paths: tuple[str, ...]) -> str | None:
    for path in paths:
        if env.exists(path):
            return path
    return None


def _app_engine_venvs(env, name: str) -> tuple[str, ...]:
    """The venv roots plan 02-02 creates under the app's engines dir, pin first.

    The pinned root is version-suffixed the way the harness's own mlx-lm venv is
    (``mlx-lm-0.31.3``), so a second version never lands on top of a measured one.
    """
    base = os.path.join(env.home, "Library", "Application Support", "OhYesMLX", "engines")
    return (os.path.join(base, f"{name}-{TESTED_VERSIONS[name]}"), os.path.join(base, name))


def _app_engine_scripts(env, name: str, script: str) -> tuple[str, ...]:
    return tuple(os.path.join(root, "bin", script) for root in _app_engine_venvs(env, name))


def _detect_osaurus(env) -> tuple[str | None, str | None]:
    # Both spellings: the DMG installs `osaurus.app`, the cask artifact is
    # `Osaurus.app`, and on a case-sensitive volume they are two different files.
    found = _first_existing(
        env, (f"{_APPLICATIONS}/osaurus.app", f"{_APPLICATIONS}/Osaurus.app")
    )
    if found is None:
        return None, None
    path = env.realpath(found)
    return path, _plist_version(env, path)


def _detect_omlx(env) -> tuple[str | None, str | None]:
    # The shim is the file the harness starts and the one `realpath` resolves; the
    # bundle is the fallback evidence and always where the version is written.
    found = _first_existing(
        env, (os.path.join(env.home, ".omlx", "bin", "omlx"), f"{_APPLICATIONS}/oMLX.app")
    )
    if found is None:
        return None, None
    return env.realpath(found), _plist_version(env, f"{_APPLICATIONS}/oMLX.app")


def _detect_optiq(env) -> tuple[str | None, str | None]:
    found = _first_existing(
        env,
        _app_engine_scripts(env, "optiq", "optiq")
        + (
            os.path.join(env.home, ".local", "bin", "optiq"),
            os.path.join(env.home, "Dev", "tools", "mlx-optiq", ".venv", "bin", "optiq"),
        ),
    )
    if found is None:
        return None, None
    return env.realpath(found), _optiq_version(env, found)


def _detect_mlxlm(env) -> tuple[str | None, str | None]:
    # A console script is the only durable evidence: mlx-lm has no app bundle and no
    # global location (`runtimes.py` carries none either), so the harness venv and the
    # app's own venvs are the two known homes.
    found = _first_existing(
        env,
        _app_engine_scripts(env, "mlxlm", "mlx_lm.server")
        + (
            os.path.join(
                env.home,
                ".local",
                "share",
                "ohyesmlx",
                f"mlx-lm-{TESTED_VERSIONS['mlxlm']}",
                "bin",
                "mlx_lm.server",
            ),
        ),
    )
    if found is None:
        return None, None
    return env.realpath(found), _venv_package_version(env, found, "mlx_lm", "_version.py")


def _detect_vmlx(env) -> tuple[str | None, str | None]:
    found = _first_existing(
        env, (f"{_APPLICATIONS}/vMLX.app", os.path.join(env.home, ".local", "bin", "vmlx"))
    )
    if found is None:
        return None, None
    return env.realpath(found), _module_version(env, VMLX_ENGINE_INIT)


_DETECTORS = {
    "mlxlm": _detect_mlxlm,
    "osaurus": _detect_osaurus,
    "omlx": _detect_omlx,
    "optiq": _detect_optiq,
    "vmlx": _detect_vmlx,
}


def detect_all(env=DEFAULT_ENV) -> list[EngineStatus]:
    """One status per onboarding engine, in registry order."""
    statuses = []
    for name in RUNTIMES:
        if name not in ONBOARDING_ENGINES:
            continue
        path, version = _DETECTORS[name](env)
        statuses.append(
            EngineStatus(
                name=name,
                title=_TITLES[name],
                blurb=_BLURBS[name],
                installed=path is not None,
                version=version,
                path=path,
                tested=version == TESTED_VERSIONS[name],
                install=None,  # the server composes install_plan(name, macos) in Phase 4
            )
        )
    return statuses


# The guided routes open the release page: neither oMLX nor vMLX has a fixed asset URL,
# so the plan names the asset and never resolves "latest" over the wire (research §2.1,
# §5.1). Osaurus's README points at `Osaurus.dmg` on the same page (§1.1).
_GUIDED_SOURCES = {
    "osaurus": "https://github.com/osaurus-ai/osaurus/releases/latest",
    "omlx": "https://github.com/jundot/omlx/releases",
    "vmlx": "https://github.com/jjang-ai/vmlx/releases/latest",
}

_OSAURUS_ASSET = "Osaurus.dmg (the standard build, not the ~3.6 GB -full one)"
_OSAURUS_SIZE = 85_900_000

# (macOS < 26, macOS >= 26). "<ver>" stays a pattern rather than a guessed release:
# the plan is data, and the release page is where the current version is read.
_GUIDED_ASSETS = {
    "osaurus": (_OSAURUS_ASSET, _OSAURUS_ASSET),
    "omlx": ("oMLX-<ver>-macos15-sequoia.dmg", "oMLX-<ver>-macos26-27.dmg"),
    "vmlx": ("vMLX-<ver>-sequoia-arm64.dmg", "vMLX-<ver>-tahoe-arm64.dmg"),
}

# Download sizes in bytes (MB = 1_000_000), from the research table. The installed and
# after-use figures are not estimates of this, so they are not folded in (§6.5).
_GUIDED_SIZES = {
    "osaurus": (_OSAURUS_SIZE, _OSAURUS_SIZE),
    "omlx": (837_800_000, 875_200_000),
    "vmlx": (579_000_000, 604_500_000),
}

_PIP_SOURCES = {
    "mlxlm": "https://pypi.org/project/mlx-lm/",
    "optiq": "https://pypi.org/project/mlx-optiq/",
}

# The distribution name each engine installs, pinned to TESTED_VERSIONS rather than to
# PyPI's latest: every start command and refusal is written against that build (§6.3).
_PIP_PACKAGES = {"mlxlm": "mlx-lm", "optiq": "mlx-optiq"}


def _guided_plan(name: str, macos_major: int) -> Plan:
    generation = 0 if macos_major < 26 else 1
    return Plan(
        engine=name,
        kind="guided_download",
        source_url=_GUIDED_SOURCES[name],
        size_bytes_estimate=_GUIDED_SIZES[name][generation],
        needs_admin=False,
        steps=[
            Step(
                id="open-page",
                label=(
                    f"Download {_GUIDED_ASSETS[name][generation]} from the release page "
                    f"and drag {_TITLES[name]} to Applications."
                    + (" Pick the latest stable release, not a release candidate." if name == "omlx" else "")
                ),
                command=None,
            ),
            Step(
                id="verify-install",
                label=(
                    f"Reopen this screen: {_TITLES[name]} is detected once its app bundle "
                    f"is in {_APPLICATIONS}."
                ),
                command=None,
            ),
        ],
    )


def _command_plan(name: str) -> Plan:
    version = TESTED_VERSIONS[name]
    package = _PIP_PACKAGES[name]
    root = _app_engine_venvs(DEFAULT_ENV, name)[0]
    return Plan(
        engine=name,
        kind="command",
        source_url=_PIP_SOURCES[name],
        # The research knows the wheel size but not a clean install's footprint, and a
        # wheel is not what this step leaves on disk (§3.2, §5.2).
        size_bytes_estimate=None,
        needs_admin=False,
        steps=[
            Step(
                id="create-venv",
                label=f"Create a Python 3.11+ virtual environment at {root}.",
                command=["{python}", "-m", "venv", root],
            ),
            Step(
                id="install",
                label=f"Install {package} {version}, the version this harness measured.",
                command=[
                    os.path.join(root, "bin", "python"),
                    "-m",
                    "pip",
                    "install",
                    "--no-input",
                    "--disable-pip-version-check",
                    f"{package}=={version}",
                ],
            ),
        ],
    )


def install_plan(name: str, macos_major: int) -> Plan:
    """What installing *name* on macOS *macos_major* would do, and nothing else.

    Pure data: no network, no subprocess, no filesystem write. The two kinds are the
    research's own split -- the three app engines are guided downloads that open the
    release page, and the two Python packages are commands that create the venv under
    the app's engines dir and install into it (Decision D2).

    ``{python}`` in the first command is a placeholder: 02-03 substitutes the
    interpreter it picked, so the plan does not choose one here.
    """
    if name not in ONBOARDING_ENGINES:
        raise ValueError(
            f"unknown engine {name!r}; expected one of {', '.join(ONBOARDING_ENGINES)}"
        )
    if name in _PIP_PACKAGES:
        return _command_plan(name)
    return _guided_plan(name, macos_major)
