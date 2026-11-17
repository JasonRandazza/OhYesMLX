"""What Mac this is.

Onboarding's first question is answered here and nowhere else: the chip, its family and
tier, the core count, unified memory, free disk, and the macOS version. ``scan`` takes its
side effects as parameters -- commands go through ``run(argv)``, volumes come from
``volume_paths()``, and each volume's space from ``disk_usage(path)`` -- so the parsing is
checked against captured text and the real machine is one default away. ``gpu_cores`` is
the ``gpu-core-count`` that ``ioreg -rc AGXAccelerator -d1`` reports for this Mac's GPU,
and ``None`` when macOS does not report it -- an absent line, empty output, or a command
that fails.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from ohyesmlx.sample import SYSCTL

# Every tool this module runs, by absolute path, so a PATH carrying a lab directory or a
# user's own binary cannot decide what "this Mac" is. `SYSCTL` is `sample`'s definition --
# the module that used it first -- and the other two are used only here.
SW_VERS = "/usr/bin/sw_vers"
IOREG = "/usr/sbin/ioreg"

# A tool that has not answered in this long is hung, not slow: the scan is four short
# commands, and `/hardware` must answer rather than hold a handler thread forever (T-09).
TOOL_TIMEOUT_S = 10

# Below 8 GiB there is not enough unified memory for the smallest model in the catalog,
# so the machine is reported unsupported rather than recommended to (Decision D1).
MIN_RAM_BYTES = 8 * 1024**3

# The chip's trailing word, when it has one, is its tier. Anything else is a base chip.
_SUFFIX_TIERS = {"pro": "pro", "max": "max", "ultra": "ultra"}


@dataclass(frozen=True)
class Hardware:
    supported: bool
    unsupported_reason: str | None
    chip: str
    family: str
    tier: str
    cpu_cores: int
    gpu_cores: int | None
    ram_bytes: int
    macos: str
    disk_free_bytes: int
    volumes: list[dict]
    model_budget_bytes: int


def _run(argv: list[str]) -> str:
    """Run *argv* and return its stdout with surrounding whitespace removed.

    *argv* names its tool by absolute path, and the call is bounded by ``TOOL_TIMEOUT_S``:
    a hung tool raises ``subprocess.TimeoutExpired`` rather than hanging the caller.
    """
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=TOOL_TIMEOUT_S,
        check=True,
    )
    return proc.stdout.strip()


def _chip_identity(chip: str) -> tuple[str, str]:
    """``("Apple M2 Max")`` -> ``("M2", "max")``; an unknown trailing word is base."""
    tokens = chip.split()
    if len(tokens) < 2 or tokens[0] != "Apple":
        return "", "base"
    suffix = tokens[2].lower() if len(tokens) > 2 else ""
    return tokens[1], _SUFFIX_TIERS.get(suffix, "base")


_GPU_CORE_COUNT = re.compile(r'"gpu-core-count" = (\d+)')


def _gpu_cores(ioreg: str) -> int | None:
    """The AGX accelerator's core count from ``ioreg`` text; first match, or ``None``."""
    match = _GPU_CORE_COUNT.search(ioreg)
    return int(match.group(1)) if match else None


def _support(chip: str, ram_bytes: int) -> tuple[bool, str | None]:
    if not chip.startswith("Apple"):
        return False, "this Mac is not Apple silicon"
    if ram_bytes < MIN_RAM_BYTES:
        return False, "this Mac has less than 8 GiB of unified memory"
    return True, None


def model_budget(ram_bytes: int) -> int:
    """Bytes of model weights this Mac may hold resident, integer arithmetic only.

    Apple's default GPU wired-memory ceiling is three quarters of unified memory on a
    36 GiB machine and above, two thirds below it; 2 GiB is then reserved for the KV cache
    and runtime overhead.
    """
    ceiling = ram_bytes * 3 // 4 if ram_bytes >= 36 * 1024**3 else ram_bytes * 2 // 3
    return max(0, ceiling - 2 * 1024**3)


def _volume_paths(root: str = "/Volumes") -> list[str]:
    """``"/"`` then each directory directly under *root*.

    The startup disk appears under ``/Volumes`` as a symlink to ``/``, so only entries that
    are directories in their own right are volumes; a missing *root* is one disk.
    """
    paths = ["/"]
    try:
        with os.scandir(root) as entries:
            found = sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return paths
    for entry in found:
        # ponytail: name list, not an APFS role query; `diskutil` role lookup if system volumes multiply
        if entry.name.startswith(".") or entry.name == "Recovery":
            continue
        if entry.is_dir(follow_symlinks=False):
            paths.append(entry.path)
    return paths


def free_bytes_at(path: str, disk_usage=None) -> int:
    """Free bytes on the volume that holds *path*, which need not exist yet.

    The one disk-free definition (S4-F3): the nearest existing ancestor of *path*, resolved
    through symlinks, asked of ``shutil.disk_usage`` -- looked up at call time, so a test
    that replaces the module attribute is honoured (*disk_usage* is only for ``scan``'s own injection). ``scan``'s ``disk_free_bytes`` and both
    download guards ask this, so the number the screens show is the number the guards use.
    """
    probe = os.path.realpath(path)
    while not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    return (disk_usage or shutil.disk_usage)(probe).free


def scan(
    run=_run,
    disk_usage=None,
    volume_paths=_volume_paths,
    cache_dir: str | None = None,
) -> Hardware:
    """Describe this Mac through *run* and its volumes through *disk_usage*.

    ``disk_free_bytes`` is the free space of the volume the Hugging Face cache lives on
    (*cache_dir*, else ``fetch.default_cache_dir()``), not of ``/``.
    """
    from ohyesmlx import fetch  # fetch imports this module; the cycle is broken here

    disk_usage = disk_usage or shutil.disk_usage

    chip = run([SYSCTL, "-n", "machdep.cpu.brand_string"])
    ram_bytes = int(run([SYSCTL, "-n", "hw.memsize"]))
    cpu_cores = int(run([SYSCTL, "-n", "hw.ncpu"]))
    macos = run([SW_VERS, "-productVersion"])
    try:
        ioreg = run([IOREG, "-rc", "AGXAccelerator", "-d1"])
    except (OSError, subprocess.CalledProcessError):
        ioreg = ""
    family, tier = _chip_identity(chip)
    supported, reason = _support(chip, ram_bytes)
    try:
        disk_free_bytes = free_bytes_at(cache_dir or fetch.default_cache_dir(), disk_usage)
    except OSError:
        disk_free_bytes = 0
    volumes: list[dict] = []
    for path in volume_paths():
        try:
            free_bytes = disk_usage(path).free
        except OSError:
            continue
        volumes.append({"path": path, "free_bytes": free_bytes})
    return Hardware(
        supported=supported,
        unsupported_reason=reason,
        chip=chip,
        family=family,
        tier=tier,
        cpu_cores=cpu_cores,
        gpu_cores=_gpu_cores(ioreg),
        ram_bytes=ram_bytes,
        macos=macos,
        disk_free_bytes=disk_free_bytes,
        volumes=volumes,
        model_budget_bytes=model_budget(ram_bytes),
    )
