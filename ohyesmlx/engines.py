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

``install`` is filled by plan 02-02 (``install_plan``); detection leaves it ``None``.
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
class EngineStatus:
    name: str
    title: str
    blurb: str
    installed: bool
    version: str | None
    path: str | None
    tested: bool
    install: object | None  # the Plan from plan 02-02; None until it exists


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
                install=None,  # plan 02-02 fills this with install_plan(name)
            )
        )
    return statuses
