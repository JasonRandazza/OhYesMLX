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

import json
import math
import os
import pathlib
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.parsers.expat import ExpatError

from ohyesmlx import app_support_dir, atomic_write_text
from ohyesmlx.hardware import scan as _scan_hardware
from ohyesmlx.runtimes import OSAURUS_APP_BUNDLES, RUNTIMES, VMLX_ENGINE_INIT

# The five engines of Decision D2, in the registry's own order. MTPLX joins when its
# branch lands; until then its registry entry is filtered out rather than probed.
ONBOARDING_ENGINES = ("mlxlm", "osaurus", "omlx", "optiq", "vmlx")

# The manifest, and the one place an engine's tested version is written (Decision 135):
# a different installed version is reported untested, never assumed equivalent, because
# every start command and refusal is written against the builds it names. It lives beside
# the package rather than inside it so a checkout and an installed wheel read the same
# file; pyproject ships `ohyesmlx/engines-tested.json` in both builds.
MANIFEST_PATH = pathlib.Path(__file__).resolve().parent / "engines-tested.json"


def load_manifest(path=MANIFEST_PATH) -> dict[str, dict]:
    """Read and validate the tested-versions manifest at *path*.

    One entry per engine in :data:`ONBOARDING_ENGINES`, and nothing besides: ``version``
    is the build the harness is written against, ``verified`` the ISO date it was
    confirmed, ``lab_path`` an optional bin directory a pinned copy lives in, and
    ``canary`` the canary routine's record (plan 025-02). A missing, unreadable or
    ill-shaped file raises ``ValueError`` naming the file and the entry at fault: a table
    half-read would report an installed build as tested against a version nobody checked.
    """
    path = pathlib.Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read the engines manifest {path}: {error}") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError(f"the engines manifest {path} is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"the engines manifest {path} must be a JSON object keyed by engine")
    missing = [name for name in ONBOARDING_ENGINES if name not in payload]
    if missing:
        raise ValueError(
            f"the engines manifest {path} is missing engine(s): {', '.join(missing)}"
        )
    unknown = [name for name in payload if name not in ONBOARDING_ENGINES]
    if unknown:
        raise ValueError(
            f"the engines manifest {path} names unknown engine(s) "
            f"{', '.join(sorted(unknown))}; expected one of {', '.join(ONBOARDING_ENGINES)}"
        )
    for name in ONBOARDING_ENGINES:
        entry = payload[name]
        if not isinstance(entry, dict):
            raise ValueError(f"the engines manifest {path} entry {name} must be an object")
        if not isinstance(entry.get("version"), str):
            raise ValueError(
                f"the engines manifest {path} entry {name} has no string 'version'"
            )
        if entry.get("verified") is not None and not isinstance(entry["verified"], str):
            raise ValueError(
                f"the engines manifest {path} entry {name} has a non-string 'verified'"
            )
        if entry.get("lab_path") is not None and not isinstance(entry["lab_path"], str):
            raise ValueError(
                f"the engines manifest {path} entry {name} has a non-string 'lab_path'"
            )
        canary = entry.get("canary")
        if canary is not None:
            if not isinstance(canary, dict):
                raise ValueError(
                    f"the engines manifest {path} entry {name} has a non-object 'canary'"
                )
            for field in ("format", "repo", "workload"):
                if not isinstance(canary.get(field), str) or not canary[field]:
                    raise ValueError(
                        f"the engines manifest {path} entry {name} canary has no string "
                        f"'{field}'"
                    )
            for field in ("decode_tok_s", "ttft_s", "measured", "version_measured"):
                if field not in canary:
                    raise ValueError(
                        f"the engines manifest {path} entry {name} canary has no '{field}' "
                        "key; a baseline that has not been recorded yet is null, not absent"
                    )
            for field in ("decode_tok_s", "ttft_s"):
                value = canary[field]
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                ):
                    raise ValueError(
                        f"the engines manifest {path} entry {name} canary has a non-numeric "
                        f"'{field}'"
                    )
            for field in ("measured", "version_measured"):
                if canary[field] is not None and not isinstance(canary[field], str):
                    raise ValueError(
                        f"the engines manifest {path} entry {name} canary has a non-string "
                        f"'{field}'"
                    )
    return payload


# Loaded once, at import: a manifest that is absent or ill-shaped stops this module with
# the file's name, because every answer below -- tested, install pin, detections -- would
# otherwise be a comparison against nothing.
MANIFEST = load_manifest()
TESTED_VERSIONS = {name: MANIFEST[name]["version"] for name in ONBOARDING_ENGINES}

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
    verified: str | None  # the manifest's ISO date for the build `tested` is against
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
    # ponytail: a checkout is recognised by the venv being named `.venv`; a differently
    # named editable venv falls through to dist-info metadata. Add a pyproject-name check if one appears.
    pyproject = None
    if os.path.basename(root) == ".venv":
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


# The app's own Application Support directory: plan 02-02's venvs live in `engines/`
# under it, and plan 02-03's install log sits beside that. Its one definition is
# `ohyesmlx.app_support_dir`, so `fetch` and `quickbench` ask the same helper.
def _app_support(home: str) -> str:
    """The app's Application Support directory for *home*, as the string callers join."""
    return str(app_support_dir(home))


def _engines_dir(home: str) -> str:
    """The one place the app-managed engines directory is derived (detect and install share it)."""
    return os.path.join(_app_support(home), "engines")


def _app_engine_venvs(env, name: str) -> tuple[str, ...]:
    """The venv roots plan 02-02 creates under the app's engines dir, pin first.

    The pinned root is version-suffixed the way the harness's own mlx-lm venv is
    (``mlx-lm-<version>``), so a second version never lands on top of a measured one.
    """
    base = _engines_dir(env.home)
    return (os.path.join(base, f"{name}-{TESTED_VERSIONS[name]}"), os.path.join(base, name))


def _app_engine_scripts(env, name: str, script: str) -> tuple[str, ...]:
    return tuple(os.path.join(root, "bin", script) for root in _app_engine_venvs(env, name))


# The machine-local lab copies, and the only place a real lab path is written. A lab path
# is machine-specific -- a directory that is right on one Mac is a refusal to start on
# every other one -- so the committed manifest ships ``lab_path: null`` everywhere and the
# local file beside the app's engines dir carries what this Mac actually has. Plan 025-03's
# wizard writes it; the harness's PATH prefix and detection below both read it through
# :func:`lab_paths` and nothing restates the list.
LAB_PATHS_NAME = "lab-paths.json"


def _lab_paths_file(home: str) -> str:
    """The one place the machine-local lab-paths file is derived (detection and start share it)."""
    return os.path.join(_app_support(home), LAB_PATHS_NAME)


def _lab_paths_beside(engines_dir: str) -> str:
    """The lab-paths file of the app-support directory *engines_dir* is a child of.

    ``_engines_dir`` and ``_lab_paths_file`` are two children of one directory; ``install`` is
    handed the first and writes the second beside it, so a scratch engines directory an
    injected or test run uses keeps its own lab-paths file rather than this Mac's real one.
    """
    return os.path.join(os.path.dirname(os.path.abspath(engines_dir)), LAB_PATHS_NAME)


LAB_PATHS_FILE = _lab_paths_file(DEFAULT_ENV.home)

# The engines a lab path may name, and the whole of them: the two pip packages install
# into a venv this harness can point a start command at. The three app engines are .app
# bundles and their tested build is archived rather than installed into a bin directory,
# so a lab path for one names no directory a script could be found in.
LAB_ENGINES = ("mlxlm", "optiq")


def check_lab_dir(path: str) -> None:
    """Refuse *path* unless it is an absolute directory this user owns and others cannot write.

    A lab path becomes the front of PATH for every engine start (``runtimes._engine_env``)
    and is written into the machine-local file by :func:`record_lab_path`, so a directory
    another account or group can write is a directory that picks which ``mlx_lm.server``
    the harness runs. ``os.stat`` follows symlinks on purpose: the directory the process
    will actually read is the one that must be private, not the link that names it.
    """
    if not os.path.isabs(path):
        raise ValueError(f"{path}: a lab path must be absolute")
    try:
        info = os.stat(path)
    except OSError as error:
        raise ValueError(f"{path}: a lab path must be a directory: {error}") from error
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"{path}: a lab path must be a directory")
    if info.st_uid != os.geteuid():
        raise ValueError(
            f"{path}: a lab path must be owned by this user (uid {os.geteuid()}), "
            f"not uid {info.st_uid}"
        )
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"{path}: a lab path must not be group- or other-writable")


def lab_paths(path=LAB_PATHS_FILE, *, read=None) -> dict[str, str]:
    """The machine-local lab paths at *path*, keyed by engine; ``{}`` when there is no file.

    One reader for one file, because two callers need the same answer and a second copy of
    the validation would be a second place for the two to disagree: ``runtimes._engine_env``
    prefixes these directories to PATH, and :func:`detect_all` looks in them first -- so a
    canary of a lab copy reports that copy's version rather than the global install's.

    A missing file is ``{}``: no lab copies is the ordinary state of a machine that has not
    frozen anything. Everything else is refused by ``ValueError`` naming the file and the
    entry at fault, because the alternatives are both worse than stopping -- an unknown key
    is a path nobody would read, and a file half-understood would measure a global install
    under a pinned version's label. The three app engines are refused with their own
    message (:data:`LAB_ENGINES`).

    *read* is how the caller supplies text -- ``pathlib`` by default, and the detection below
    hands in its ``env`` so the same file is checked against a fixture filesystem.
    """
    if read is None:
        def read(path):
            return pathlib.Path(path).read_text(encoding="utf-8")

    try:
        text = read(path)
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ValueError(f"cannot read the lab paths file {path}: {error}") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError(f"the lab paths file {path} is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"the lab paths file {path} must be a JSON object keyed by engine")
    for name, value in payload.items():
        if name not in ONBOARDING_ENGINES:
            raise ValueError(
                f"the lab paths file {path} names unknown engine {name!r}; expected one of "
                f"{', '.join(ONBOARDING_ENGINES)}"
            )
        if name not in LAB_ENGINES:
            raise ValueError(
                f"the lab paths file {path} names {name!r}, and app engines are archived, "
                f"not run from a lab path: only {', '.join(LAB_ENGINES)} can name one"
            )
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"the lab paths file {path} entry {name} is not a non-empty string path"
            )
    return dict(payload)


def record_lab_path(engine: str, bin_dir: str, *, path=LAB_PATHS_FILE) -> None:
    """Record *engine*'s bin directory in the machine-local lab-paths file, atomically.

    The one writer for one file, and :func:`lab_paths` its one reader. ``install`` calls this
    after a pip engine's install succeeds, because the venv it created lives under Application
    Support where no shell exports it: the start commands use bare names, so without this
    entry every mlx-lm and OptiQ cell on a Mac that installed through the app fails to start.

    Read, replace, write: every other engine's entry is kept, and *engine*'s is replaced only
    by an install of the version the manifest pins (:func:`install_plan` pins
    ``TESTED_VERSIONS``). The write is :func:`ohyesmlx.atomic_write_text`.

    *bin_dir* is refused by :func:`check_lab_dir` before the file is even read.

    A file this function cannot read is refused by :func:`lab_paths` rather than overwritten,
    and an engine outside :data:`LAB_ENGINES` is refused here for the same reason that reader
    refuses one.
    """
    if engine not in LAB_ENGINES:
        raise ValueError(
            f"refusing to record a lab path for {engine!r}: only {', '.join(LAB_ENGINES)} "
            "install into a bin directory"
        )
    if not isinstance(bin_dir, str) or not bin_dir:
        raise ValueError(
            f"refusing to record a lab path for {engine}: {bin_dir!r} is not a non-empty "
            "directory"
        )
    check_lab_dir(bin_dir)
    entries = lab_paths(path)
    entries[engine] = bin_dir
    atomic_write_text(path, json.dumps(entries, indent=2, sort_keys=True) + "\n")


def _detect_osaurus(env) -> tuple[str | None, str | None]:
    # Both spellings are `runtimes`' one definition of the app's paths.
    found = _first_existing(env, OSAURUS_APP_BUNDLES)
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


def _lab_script(lab_path: str | None, script: str) -> tuple[str, ...]:
    """The script a machine-local lab path would hold, or nothing when no lab path is set."""
    if not lab_path:
        return ()
    return (os.path.join(os.path.expanduser(lab_path), script),)


def _detect_optiq(env, lab_path=None) -> tuple[str | None, str | None]:
    found = _first_existing(
        env,
        _lab_script(lab_path, "optiq")
        + _app_engine_scripts(env, "optiq", "optiq")
        + (
            os.path.join(env.home, ".local", "bin", "optiq"),
            os.path.join(env.home, "Dev", "tools", "mlx-optiq", ".venv", "bin", "optiq"),
        ),
    )
    if found is None:
        return None, None
    return env.realpath(found), _optiq_version(env, found)


def _detect_mlxlm(env, lab_path=None) -> tuple[str | None, str | None]:
    # A console script is the only durable evidence: mlx-lm has no app bundle and no
    # global location (`runtimes.py` carries none either), so the harness venv and the
    # app's own venvs are the two known homes.
    found = _first_existing(
        env,
        _lab_script(lab_path, "mlx_lm.server")
        + _app_engine_scripts(env, "mlxlm", "mlx_lm.server")
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
    """One status per onboarding engine, in registry order.

    An engine this machine has frozen a lab copy of is detected *there* first: the lab
    directory comes ahead of the app's own venvs and of the global installs, and the
    version is read from the venv the script found in it lives in. That ordering is the
    point of the lab copy rather than a convenience -- ``canary`` records the version
    ``detect_all`` reports, so a canary of a pinned build that answered with the global
    install's version would write the wrong number against the wrong build. The three app
    engines cannot have a lab path at all (:func:`lab_paths` refuses one), so they are
    asked without it.

    A lab path with nothing at it is not an error *here*: detection reports what it finds,
    and the refusal belongs to starting an engine (``runtimes._engine_env``), which is
    where falling back to the global install would corrupt a measurement.
    """
    labs = lab_paths(_lab_paths_file(env.home), read=env.read_text)
    statuses = []
    for name in RUNTIMES:
        if name not in ONBOARDING_ENGINES:
            continue
        if name in LAB_ENGINES:
            path, version = _DETECTORS[name](env, labs.get(name))
        else:
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
                verified=MANIFEST[name]["verified"],
                install=None,  # the server composes install_plan(name, macos) in Phase 4
            )
        )
    return statuses


# The guided routes open the release page of the version this harness is written against,
# never `releases/latest`: a new Osaurus build was out within hours of the one this harness
# adopted (Decision 139), so "latest" installs whatever shipped last. Neither oMLX nor vMLX
# has a fixed asset URL, so the plan names the asset and the page it lives on (research §2.1,
# §5.1; Osaurus's README points at `Osaurus.dmg` on the same page, §1.1). Each entry is
# (release base, tag prefix) and the URL is built from TESTED_VERSIONS, so a version bump
# moves the page with no other edit. Osaurus tags bare versions; oMLX and vMLX prefix "v"
# (tag pages checked 2026-11-02 with `gh api`).
_GUIDED_TRACKS = {
    "osaurus": ("https://github.com/osaurus-ai/osaurus/releases/tag/", ""),
    "omlx": ("https://github.com/jundot/omlx/releases/tag/", "v"),
    "vmlx": ("https://github.com/jjang-ai/vmlx/releases/tag/", "v"),
}


def _release_url(name: str) -> str:
    """The tested build's GitHub release page: one base and tag prefix per engine (AC-3)."""
    base, prefix = _GUIDED_TRACKS[name]
    return f"{base}{prefix}{TESTED_VERSIONS[name]}"


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

# A pip engine's pin is only half a pin: pinning the distribution leaves its dependency
# set to float, and the two lab venvs had already drifted apart at the same versions (mlx
# 0.32.4 vs 0.32.2, transformers 5.12.1 vs 5.17.0). The committed constraints file pins
# the whole set, one per pip engine per tested version, beside the package the way the
# manifest is. It also records the finding that made this necessary: OptiQ serves through
# `mlx_lm.server` and does not pin mlx-lm, so unpinned pip took the newest and every chat
# request answered HTTP 404 (found 2026-10-30 building the OptiQ lab copy); its freeze
# names mlx-lm at the tested mlx-lm version.
CONSTRAINTS_DIR = pathlib.Path(__file__).resolve().parent / "constraints"


def constraints_path(engine: str) -> pathlib.Path:
    """The constraints file for *engine*'s tested version: the one definition of its name."""
    return CONSTRAINTS_DIR / f"{engine}-{TESTED_VERSIONS[engine]}.txt"


# A requirements line the installer may hand pip: a pin and nothing else, followed by one or
# more sha256 hashes. Everything else -- `--index-url`, `--extra-index-url`, `--trusted-host`,
# `-f`, `-r`, `-c`, `-e` -- is refused below, because a requirements file can carry all of
# them and the installer's file is one it wrote rather than one it reads from the user. The
# pin grammar is written once; the two patterns below and `scripts/hash_freeze.py` ask it.
_PIN = r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*)"
_PIN_ONLY = re.compile(rf"^{_PIN}$")
_HASHED_PIN = re.compile(rf"^{_PIN}(?:\s+--hash=sha256:[0-9a-f]{{64}})+$")


def _requirement_lines(text: str):
    """The file's requirement lines, with ``\\`` continuations joined and comments dropped.

    A continuation that runs to EOF is flushed as its own line: a file whose last line is
    ``pkg==1.0 \\`` is a pin with no hashes, and dropping the pending line would read it as
    a file with nothing to check. ``scripts/hash_freeze.py`` joins with this same function,
    so the validator and the regenerator cannot disagree about what the file says.
    """
    pending = ""
    for line in text.splitlines():
        line = (pending + " " + line.strip() if pending else line).strip()
        pending = ""
        if line.endswith("\\"):
            pending = line[:-1].rstrip()
            continue
        if not line or line.startswith("#"):
            continue
        yield line
    if pending and not pending.startswith("#"):
        yield pending


def _check_hashed_requirements(path) -> None:
    """Refuse *path* unless every requirement is a ``name==version`` pin with its hashes.

    One validator for the one thing that makes the install's ``--require-hashes`` mean
    something: every line is a pin, every pin carries a hash for every file it may install,
    and no line is a pip option. A pin without a hash is named as such; anything else is
    named as the line it is. Both messages name the file, because the caller's next step is
    to regenerate it (``scripts/hash_freeze.py``), not to guess which of two files it read.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    for line in _requirement_lines(text):
        if _HASHED_PIN.match(line):
            continue
        token = line.split()[0]
        if _PIN_ONLY.match(token) and "--hash=" not in line:
            raise ValueError(
                f"{path}: the requirement {token!r} carries no hashes; the installer runs "
                "pip with --require-hashes, so the pin must be followed by a "
                "--hash=sha256:<hex> line for every file (scripts/hash_freeze.py writes them)"
            )
        raise ValueError(
            f"{path}: {line!r} is not a name==version pin followed by "
            "--hash=sha256:<64 hex> lines; option lines (--index-url, -r, -e, ...) are "
            "refused"
        )


def _guided_plan(name: str, macos_major: int) -> Plan:
    generation = 0 if macos_major < 26 else 1
    return Plan(
        engine=name,
        kind="guided_download",
        source_url=_release_url(name),
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
                # -I: the user's site-packages and PYTHON* variables must not shape the
                # interpreter that builds every later start command (T-07).
                command=["{python}", "-I", "-m", "venv", root],
            ),
            Step(
                id="install",
                label=f"Install {package} {version}, the version this harness measured.",
                # --isolated: no user pip config or PIP_* variable chooses the index (T-07).
                # --require-hashes/--only-binary: the file names the package and every
                # dependency, and pip may take only files whose hash it lists. Building an
                # sdist is not covered by hash-checking and runs its code, so sdists are out.
                # --no-deps: the constraints file is the whole closure (scripts/hash_freeze.py
                # froze the venv's full set), so the resolver has nothing to add and no
                # declaration it can act on -- which is what lets a requirement be omitted
                # deliberately. optiq omits pygame: mlx-optiq declares it only for
                # `optiq game`, which this harness never starts, and pygame 2.6.1 has no
                # CPython 3.14 wheel, so pip could only build it from source, needing SDL
                # headers a Mac without Homebrew lacks (045-03).
                command=[
                    os.path.join(root, "bin", "python"),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--isolated",
                    "--no-input",
                    "--disable-pip-version-check",
                    "--require-hashes",
                    "--only-binary",
                    ":all:",
                    "--no-deps",
                    "-r",
                    str(constraints_path(name)),
                ],
            ),
        ],
    )


def install_plan(name: str, macos_major: int) -> Plan:
    """What installing *name* on macOS *macos_major* would do, and nothing else.

    Pure data: no network, no subprocess, no filesystem write. The two kinds are the
    research's own split -- the three app engines are guided downloads that open the
    release page, and the two Python packages are commands that create the venv under
    the app's engines dir and install into it (Decision D2). A pip engine's plan is
    refused with ``ValueError`` naming the expected file when the tested version has no
    committed constraints file, because a package pin without its freeze installs a
    build nobody measured, and with ``ValueError`` naming the file and the line when any
    requirement in it carries no hashes (:func:`_check_hashed_requirements`), because
    ``--require-hashes`` would refuse that line only after the venv was created.

    ``{python}`` in the first command is a placeholder: 02-03 substitutes the
    interpreter it picked, so the plan does not choose one here.
    """
    if name not in ONBOARDING_ENGINES:
        raise ValueError(
            f"unknown engine {name!r}; expected one of {', '.join(ONBOARDING_ENGINES)}"
        )
    if name in _PIP_PACKAGES:
        constraints = constraints_path(name)
        if not constraints.is_file():
            raise ValueError(
                f"no pip constraints file for {name} {TESTED_VERSIONS[name]}: "
                f"expected {constraints}"
            )
        _check_hashed_requirements(constraints)
        return _command_plan(name)
    return _guided_plan(name, macos_major)


# ---------------------------------------------------------------------------
# Installing an engine -- plan 02-03
#
# ``install`` executes a Plan it derives itself (AC-6), and every side effect it has
# is a parameter: the runner, the opener, the emitter, detection, the hardware scan,
# sleep, the lock and the install log. The defaults wrap the real thing; every test
# injects a fake, so no test starts a process, opens a page or touches the real
# installs.
# ---------------------------------------------------------------------------

# Where plan 02-02's venvs live and where every attempt leaves its local record
# (AC-10). The log is plain append-only JSONL under the app's own Application Support
# directory and is never uploaded (Decision D8); it is not a governance layer.
DEFAULT_ENGINES_DIR = _engines_dir(DEFAULT_ENV.home)
DEFAULT_INSTALL_LOG = os.path.join(_app_support(DEFAULT_ENV.home), "install-log.jsonl")

# AC-8 bounds: a step that runs longer than this is killed, and the output an event
# carries is its last four kilobytes so a chatty pip cannot grow the job stream.
STEP_TIMEOUT_S = 900
OUTPUT_TAIL_BYTES = 4096

# AC-11: free disk must cover the download twice -- the download plus what the
# install unpacks -- and an unknown estimate falls back to this floor.
LOW_DISK_FLOOR_BYTES = 2 * 1024**3

# AC-9: the only hosts a guided plan may open. The plans name GitHub release pages
# and PyPI project pages; nothing else has any business being opened by this app.
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "pypi.org")

# AC-8: guided downloads poll detection until the user has installed the app or this
# much wall clock has passed. A timeout is a result, never an error.
POLL_S = 2.0
POLL_TIMEOUT_S = 600.0

# The status a killed step reports, by coreutils' convention for a timeout.
TIMEOUT_EXIT_CODE = 124


class EngineLocks:
    """One non-blocking, in-process lock per engine.

    ``install`` asks before it touches disk and releases in a ``finally``, so a
    second install of the same engine reports ``busy`` instead of running a second
    venv creation into one directory (AC-11).
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def acquire(self, engine: str) -> bool:
        with self._guard:
            lock = self._locks.setdefault(engine, threading.Lock())
        return lock.acquire(blocking=False)

    def release(self, engine: str) -> None:
        with self._guard:
            lock = self._locks.get(engine)
        if lock is not None:
            lock.release()


DEFAULT_LOCKS = EngineLocks()


def _cap(text: str) -> str:
    """The last ``OUTPUT_TAIL_BYTES`` bytes of *text*: the one definition of the output cap."""
    return text.encode("utf-8")[-OUTPUT_TAIL_BYTES:].decode("utf-8", "ignore")


def _tail(*streams) -> str:
    """The last ``OUTPUT_TAIL_BYTES`` of every stream joined, bytes decoded leniently."""
    parts = []
    for stream in streams:
        if stream is None:
            continue
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8", "replace")
        parts.append(stream)
    return _cap("".join(parts))


# The pip steps running right now, and the lock that guards the set. A step is added before
# its output is read and removed however it ends, so the server's kill list never holds a
# finished process.
_RUNNING_STEPS: set[subprocess.Popen] = set()
_RUNNING_STEPS_LOCK = threading.Lock()


def _kill_step_group(proc: subprocess.Popen) -> None:
    """SIGKILL a step's process group; a group already gone is not an error."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def kill_running_steps() -> None:
    """Kill every install step still running, by its process group.

    The one caller is the server's shutdown wait: its bound has expired with a job still
    running, so the installer's own 900 s timeout is the only thing left to stop the step,
    and the job's rollback runs in its thread once the step returns. Only steps this process
    started are in the registry, so nothing else is signalled.
    """
    with _RUNNING_STEPS_LOCK:
        steps = list(_RUNNING_STEPS)
    for proc in steps:
        _kill_step_group(proc)


def _real_run(argv: list[str], timeout_s: float, env: dict[str, str]) -> tuple[int, str]:
    """Run *argv* -- a list, never a shell string -- and return (code, output tail).

    The step runs in its own session and is registered while it runs, so a server shutting
    down can end the whole tree a pip step started rather than the one process
    (:func:`kill_running_steps`). The lock spans the spawn and the registration, so a kill
    that runs while a step is starting either sees it or waits for it and never misses it. A
    timeout kills the group, not just the parent, and reports ``TIMEOUT_EXIT_CODE`` with the
    output the step had produced.
    """
    with _RUNNING_STEPS_LOCK:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            env=env,
            start_new_session=True,
        )
        _RUNNING_STEPS.add(proc)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired as expired:
            _kill_step_group(proc)
            proc.communicate()
            return TIMEOUT_EXIT_CODE, _tail(expired.stdout, expired.stderr)
        return proc.returncode, _tail(stdout, stderr)
    finally:
        with _RUNNING_STEPS_LOCK:
            _RUNNING_STEPS.discard(proc)


# `open` is the one system tool this module runs by bare name today; an absolute path keeps
# a PATH entry from choosing which opener a guided install uses.
OPEN = "/usr/bin/open"


def _real_open(url: str) -> None:
    subprocess.run([OPEN, url], check=False, stdin=subprocess.DEVNULL)


def _print_event(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _hermetic_env() -> dict[str, str]:
    """The ambient environment minus the two families that change what pip installs.

    ``PYTHONPATH`` can shadow the venv's own packages, and any ``PIP_*`` key (index
    URL, cache directory, build isolation) makes the same command behave differently
    per machine, so both are dropped and everything else -- HOME, PATH, TMPDIR --
    passes through (AC-12).
    """
    return {
        key: value
        for key, value in os.environ.items()
        if key != "PYTHONPATH" and not key.startswith("PIP_")
    }


def _installed(statuses, engine: str) -> bool:
    return any(status.name == engine and status.installed for status in statuses)


def _disk_required(size_bytes_estimate: int | None) -> int:
    if size_bytes_estimate is None:
        return LOW_DISK_FLOOR_BYTES
    return 2 * size_bytes_estimate


def _never_cancelled() -> bool:
    """The default cancel probe: a CLI install is never cancelled from elsewhere."""
    return False


def _url_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and parts.hostname in ALLOWED_DOWNLOAD_HOSTS


def _venv_root(argv: list[str]) -> str | None:
    """The directory a ``-m venv`` command creates, or None for any other command.

    Found by searching the argv for ``-m venv``, not read at fixed indices: the venv step
    runs its interpreter with ``-I``, and both the rollback of a failed install and the
    lab-path record of a successful one follow this answer.
    """
    for index, token in enumerate(argv):
        if token == "-m" and argv[index + 1 : index + 2] == ["venv"]:
            return argv[index + 2] if index + 2 < len(argv) else None
    return None


def _plan_engines_dir(plan: Plan) -> str | None:
    for step in plan.steps:
        root = _venv_root(step.command or [])
        if root is not None:
            return os.path.dirname(root)
    return None


def _relocate(argv: list[str], source_dir: str | None, engines_dir: str) -> list[str]:
    """Point the plan's paths at the engines dir this call was handed.

    ``install_plan`` names the production directory; ``install`` executes it against
    the injected one so a scratch-dir smoke -- and every test -- never touches the
    real installs. With the production directory injected this is the identity.
    """
    if source_dir is None:
        return list(argv)
    prefix = source_dir.rstrip(os.sep) + os.sep
    return [
        os.path.join(engines_dir, token[len(prefix):])
        if token == source_dir or token.startswith(prefix)
        else token
        for token in argv
    ]


def _rollback(created: list[str], engines_dir: str, send) -> None:
    """Remove the paths this call created, and nothing else.

    A path is removed only when it resolves inside *engines_dir*: a symlink that
    points out, or a parent directory that does, is refused and reported rather than
    followed (AC-7).
    """
    inside = os.path.realpath(engines_dir)
    for path in reversed(created):
        real = os.path.realpath(path)
        if real == inside or os.path.commonpath([inside, real]) != inside:
            send(
                "log",
                f"rollback refused {path}: it resolves outside {engines_dir}",
                payload={"path": path},
            )
            continue
        try:
            if os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.lexists(path):
                os.remove(path)
        except OSError as error:
            send("log", f"rollback could not remove {path}: {error}", payload={"path": path})


def _job_event(seq: int, kind: str, message: str, fraction=None, payload=None) -> dict:
    """The pinned job-event shape (``docs/interfaces.md`` **Job**), built in one place.

    Every module that emits on a job's stream -- ``install``, ``fetch``, ``quickbench`` --
    and the server's own guard events ask this, so the five keys cannot drift apart.
    """
    return {
        "seq": seq,
        "type": kind,
        "message": message,
        "fraction": fraction,
        "payload": payload,
    }


def _append_install_log(log_path, *, engine, confirmed, kind, step, exit_code, code) -> None:
    """Append one JSON line for one event; the file is local and append-only (AC-10)."""
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "confirmed": confirmed,
        "step": step,
        "exit_code": exit_code,
        "type": kind,
        "code": code,
    }
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


def install(
    engine: str,
    confirmed: bool,
    *,
    macos_major: int,
    run=_real_run,
    open_url=_real_open,
    emit=_print_event,
    cancel=_never_cancelled,
    detect=detect_all,
    hardware=_scan_hardware,
    sleep=time.sleep,
    log_path=DEFAULT_INSTALL_LOG,
    lock=DEFAULT_LOCKS,
    python=sys.executable,
    engines_dir=DEFAULT_ENGINES_DIR,
    timeout_s: float = STEP_TIMEOUT_S,
    poll_s: float = POLL_S,
    poll_timeout_s: float = POLL_TIMEOUT_S,
) -> bool:
    """Install *engine*, but only with consent and never over an existing install.

    Deriving the Plan is the name check: an unknown engine, and a pip engine whose tested
    version has no committed constraints file, are refused before anything else runs
    (``unknown_engine`` and ``no_constraints``), and no caller-supplied command, argv or URL
    is ever executed (AC-6), so the Phase 4 localhost API cannot become an arbitrary-command
    endpoint. Every refusal emits one ``error`` event with a code, appends it to the local
    install log, and ends with ``done``, in the order consent -> already installed -> busy ->
    low disk. Steps then run with the injected interpreter and a hermetic environment,
    progress follows each one, and ``done`` is last. A failed step removes only what this
    call created (AC-7).

    *cancel* is probed before each step and before each guided-download poll, never
    while a step runs: a cancelled install takes the same rollback path a failed step
    does and ends with ``error`` code ``cancelled`` and ``done``. A pip step in
    progress therefore keeps its own timeout and the installer's rollback still
    applies, which is what lets an abandoned guided wait release the job slot.
    """
    seq = 0

    def send(kind, message, *, fraction=None, payload=None, step=None, exit_code=None):
        nonlocal seq
        seq += 1
        event = _job_event(seq, kind, message, fraction, payload)
        _append_install_log(
            log_path,
            engine=engine,
            confirmed=confirmed,
            kind=kind,
            step=step,
            exit_code=exit_code,
            code=(payload or {}).get("code"),
        )
        emit(event)
        return event

    def refuse(code, message):
        send("error", message, payload={"code": code})
        send("done", "install did not start")
        return False

    try:
        plan = install_plan(engine, macos_major)  # AC-6: an unknown name refuses here, first
    except ValueError as error:
        # AC-10: a refused attempt is still an attempt. A known pip engine reports
        # `no_constraints` whichever check refused it: the constraints file is missing, or it
        # is there and a requirement in it carries no hashes (AC-1). Either way there is no
        # constraints file this installer may use. A name outside the five is unknown.
        return refuse(
            "no_constraints" if engine in ONBOARDING_ENGINES else "unknown_engine",
            str(error),
        )

    def cancelled(created: list[str]) -> bool:
        """The failure path a cancel takes: error, the same rollback, then done."""
        send("error", f"the install of {engine} was cancelled", payload={"code": "cancelled"})
        _rollback(created, engines_dir, send)
        send("done", "install cancelled; nothing else was run")
        return False

    if not confirmed:
        return refuse("consent_required", "consent was not given; nothing was installed")

    if _installed(detect(), engine):
        return refuse(
            "already_installed", f"{engine} is already installed; nothing was overwritten"
        )

    if not lock.acquire(engine):
        return refuse("busy", f"another install of {engine} is already running")

    def run_steps() -> bool:
        created: list[str] = []
        source_dir = _plan_engines_dir(plan)
        installed_bin: str | None = None
        for position, step in enumerate(plan.steps):
            if cancel():
                return cancelled(created)
            if step.command is None:
                continue
            argv = _relocate(
                [python if token == "{python}" else token for token in step.command],
                source_dir,
                engines_dir,
            )
            root = _venv_root(argv)
            existed = root is not None and os.path.lexists(root)
            exit_code, output = run(argv, timeout_s, _hermetic_env())
            tail = _cap(output or "")
            if root is not None and not existed and os.path.lexists(root):
                created.append(root)
            if exit_code != 0:
                send(
                    "error",
                    f"step {step.id} failed with exit code {exit_code}",
                    payload={"code": "step_failed", "step": step.id, "output_tail": tail},
                    step=step.id,
                    exit_code=exit_code,
                )
                _rollback(created, engines_dir, send)
                send("done", "install failed; nothing else was run")
                return False
            if root is not None:
                # The venv this install created is the one a later start must find on PATH
                # (AC-0); it is recorded only after the step succeeded, and beside the engines
                # directory this call was handed rather than this Mac's real one.
                installed_bin = os.path.join(root, "bin")
            send(
                "progress",
                step.label,
                fraction=(position + 1) / len(plan.steps),
                payload={"step": step.id},
                step=step.id,
                exit_code=exit_code,
            )
        if installed_bin is not None:
            record_lab_path(engine, installed_bin, path=_lab_paths_beside(engines_dir))
        send("done", "install finished")
        return True

    def run_guided() -> bool:
        if not _url_allowed(plan.source_url):
            return refuse(
                "url_not_allowed",
                f"refusing to open {plan.source_url}: only https URLs on "
                f"{', '.join(ALLOWED_DOWNLOAD_HOSTS)} are allowed",
            )
        open_url(plan.source_url)
        attempts = max(1, math.ceil(poll_timeout_s / poll_s))
        installed = False
        for _ in range(attempts):
            if cancel():
                return cancelled([])
            installed = _installed(detect(), engine)
            if installed:
                break
            sleep(poll_s)
        send(
            "result",
            "installation complete" if installed else "not detected before the timeout",
            payload={"installed": installed},
        )
        send("done", "install finished" if installed else "install gave up waiting")
        return installed

    try:
        needed = _disk_required(plan.size_bytes_estimate)
        free = hardware().disk_free_bytes
        if free < needed:
            return refuse(
                "low_disk",
                f"{free} bytes free is less than the {needed} bytes this install needs",
            )

        if plan.kind == "guided_download":
            return run_guided()

        return run_steps()
    finally:
        lock.release(engine)
