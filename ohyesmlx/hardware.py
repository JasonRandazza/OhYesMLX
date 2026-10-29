"""What Mac this is.

Onboarding's first question is answered here and nowhere else: the chip, its family and
tier, the core count, unified memory, and the macOS version. ``scan`` takes its only side
effect as a parameter -- every command it runs goes through ``run(argv)`` -- so the parsing
is checked against captured text and the real machine is one default away.

Disk fields (``disk_free_bytes``, ``volumes``) and ``model_budget_bytes`` belong to T1.2
and T1.3; they are reported as ``0`` / ``[]`` / ``0`` here so the pinned ``Hardware`` shape
is complete and a caller never has to invent them. ``gpu_cores`` is ``None``: no command
this slice runs reports it, and a guessed number would be worse than an honest absence.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

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
    """Run *argv* and return its stdout with surrounding whitespace removed."""
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
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


def _support(chip: str, ram_bytes: int) -> tuple[bool, str | None]:
    if not chip.startswith("Apple"):
        return False, "this Mac is not Apple silicon"
    if ram_bytes < MIN_RAM_BYTES:
        return False, "this Mac has less than 8 GiB of unified memory"
    return True, None


def scan(run=_run) -> Hardware:
    """Describe this Mac through *run*, the one command seam."""
    chip = run(["sysctl", "-n", "machdep.cpu.brand_string"])
    ram_bytes = int(run(["sysctl", "-n", "hw.memsize"]))
    cpu_cores = int(run(["sysctl", "-n", "hw.ncpu"]))
    macos = run(["sw_vers", "-productVersion"])
    family, tier = _chip_identity(chip)
    supported, reason = _support(chip, ram_bytes)
    return Hardware(
        supported=supported,
        unsupported_reason=reason,
        chip=chip,
        family=family,
        tier=tier,
        cpu_cores=cpu_cores,
        gpu_cores=None,
        ram_bytes=ram_bytes,
        macos=macos,
        disk_free_bytes=0,
        volumes=[],
        model_budget_bytes=0,
    )
