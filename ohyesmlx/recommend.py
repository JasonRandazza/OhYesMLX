"""Which catalog models fit this Mac, ranked, with plain-language reasons.

Seam S4, the third onboarding question after "what Mac is this" (`hardware`) and "which
engines do I have" (`engines`): of the models the catalog offers, which can this machine
hold resident and download today, and which of those should be offered first?

Two separate budgets, each defined once where it is decided and never restated here:

- **Memory.** ``_fit`` compares ``size_bytes`` against ``Hardware.model_budget_bytes``
  through ``COMFORTABLE_FACTOR`` and ``TIGHT_FACTOR``; the constants carry the measured
  rationale.
- **Disk.** ``catalog.disk_needed`` is the one definition of the margin; this module asks
  it rather than computing a second copy.

Both are estimates from RAM and disk, never measurements -- `Pick.fit_basis` says so, and
`Pick.measured_here` stays ``None`` here: D5 fills it from the user's own runs in Phase 4
and never from our M2 Max rows. Nothing in this module reads a file, runs a command or
measures anything; the caller passes `Hardware`, the catalog rows and `EngineStatus` in.
"""

from __future__ import annotations

from dataclasses import dataclass

from ohyesmlx.catalog import Model, disk_needed
from ohyesmlx.engines import EngineStatus
from ohyesmlx.hardware import Hardware

# Research 2026-10-30 section 4.3: the comfortable line. Twice the artifact's bytes is the
# measured worst-case peak (1.94x at a 1,309-token prompt, plus ~0.1x for a 3B artifact's
# 4k KV), and `Hardware.model_budget_bytes` has already subtracted 2 GiB for KV and runtime
# overhead, so the two guards overlap rather than leaving a gap.
COMFORTABLE_FACTOR = 2.0

# The tight line: 1 / 1.25 = 0.8, i.e. weights at most 80% of the budget. Above the
# comfortable line but below this one, the row still loads under the lightest measured
# residency (0.96x) while the budget's reserved KV headroom is no longer implied -- so it
# is offered, ranked after every comfortable row, and labelled tight. Past 1.25 the
# weights alone are more than 80% of the budget and the row is left out.
TIGHT_FACTOR = 1.25

# AC-4's "little disk" line: under 20 GiB free, the disk is the scarce resource, so a
# starter-tier row is offered ahead of a larger standard one even when both are
# comfortable. At or above it, parameters order the two as usual.
STARTER_DISK_PRESSURE_BYTES = 20 * 1024**3

# The number the screen shows before "more models": the first three after ranking.
START_HERE_COUNT = 3

# Bytes are reported in decimal GB, because the label says GB: every byte count above is
# compared in bytes and GiB, and only the sentence the user reads divides by 1e9.
_BYTES_PER_GB = 1_000_000_000


@dataclass(frozen=True)
class Pick:
    """One catalog model this Mac can hold and download, as the recommendations screen shows it.

    ``fit`` is D5's honesty label on an estimate: ``"comfortable"`` or ``"tight"``, with
    ``fit_basis`` always ``"estimated"``. ``engines`` names the installed engines that can
    serve the row, or -- when none is installed -- every engine the catalog says can, so
    the screen can say "install X first" under ``install_needed``. ``measured_here`` is
    this user's own run on this Mac, which Phase 4 fills; it is null here and never filled
    from our M2 Max rows.
    """

    model_id: str  # the catalog row's repo id
    title: str
    params_b: float  # the BASE model's count in billions, one decimal
    format: str
    size_bytes: int
    fit: str  # "comfortable" | "tight"
    fit_basis: str  # "estimated"
    engines: list[str]  # installed engines, else the catalog's list to install
    install_needed: bool
    start_here: bool
    reason: str
    measured_here: dict | None = None


def _fit(size_bytes: int, budget_bytes: int) -> str | None:
    """``"comfortable"``, ``"tight"``, or None when the weights exceed the budget's lines."""
    if size_bytes * COMFORTABLE_FACTOR <= budget_bytes:
        return "comfortable"
    if size_bytes * TIGHT_FACTOR <= budget_bytes:
        return "tight"
    return None


def _gb(byte_count: float) -> str:
    """*byte_count* as decimal GB with one decimal: the only place bytes become text."""
    return f"{byte_count / _BYTES_PER_GB:.1f}"


def _reason(model: Model, fit: str, budget_bytes: int) -> str:
    """The fixed template for an offerable row: what is left over memory, and the download."""
    spare = _gb(budget_bytes - model.size_bytes)
    download = _gb(model.size_bytes)
    if fit == "comfortable":
        return f"Fits with about {spare} GB of memory to spare; {download} GB download"
    return f"Tight fit, about {spare} GB of memory to spare; {download} GB download"


def exclusion_reason(model: Model, hw: Hardware, free_disk: int) -> str | None:
    """Why :func:`pick` leaves *model* out, or None when the row clears both budgets.

    Memory is checked first, because it is the budget a download cannot fix. The two
    templates carry numbers and nothing else -- no speed claim, and no restatement of
    `Hardware.unsupported_reason`: an unsupported Mac is :func:`pick`'s refusal alone, so
    the sentence is never copied into a per-model reason.
    """
    fit = _fit(model.size_bytes, hw.model_budget_bytes)
    if fit is None:
        return (
            f"Needs about {_gb(model.size_bytes * COMFORTABLE_FACTOR)} GB of memory at peak; "
            f"this Mac's budget is {_gb(hw.model_budget_bytes)} GB"
        )
    needed = disk_needed(model.size_bytes)
    if free_disk < needed:
        return (
            f"Needs about {_gb(needed)} GB of free disk to download; "
            f"this Mac has {_gb(free_disk)} GB free"
        )
    return None


def _rank(model: Model, fit: str, free_disk: int) -> tuple[int, int, int, str]:
    """AC-4's order: fit, then tier under disk pressure, then more parameters, then repo id."""
    starter_first = fit == "comfortable" and free_disk < STARTER_DISK_PRESSURE_BYTES
    tier_rank = 0 if (not starter_first or model.tier == "starter") else 1
    return (0 if fit == "comfortable" else 1, tier_rank, -model.params, model.repo)


def pick(
    hw: Hardware,
    models: list[Model],
    engines: list[EngineStatus],
    free_disk: int,
) -> list[Pick]:
    """The catalog rows this Mac can hold and download, ranked; pure, and no I/O.

    An unsupported Mac is an empty list: `Hardware.unsupported_reason` already carries the
    one sentence the screen shows, so this function neither duplicates it nor builds a
    pick-shaped stand-in for it. Every other row is offered or left out by
    `exclusion_reason` alone, so neither budget is decided a second time here.
    """
    if not hw.supported:
        return []
    installed = {status.name for status in engines if status.installed}
    offerable = []
    for model in models:
        if exclusion_reason(model, hw, free_disk) is not None:
            continue
        offerable.append((model, _fit(model.size_bytes, hw.model_budget_bytes)))
    offerable.sort(key=lambda pair: _rank(pair[0], pair[1], free_disk))
    picks = []
    for position, (model, fit) in enumerate(offerable):
        installed_here = [name for name in model.engines if name in installed]
        picks.append(
            Pick(
                model_id=model.repo,
                title=model.title,
                params_b=round(model.params / _BYTES_PER_GB, 1),
                format=model.format,
                size_bytes=model.size_bytes,
                fit=fit,
                fit_basis="estimated",
                engines=installed_here or list(model.engines),
                install_needed=not installed_here,
                start_here=position < START_HERE_COUNT,
                reason=_reason(model, fit, hw.model_budget_bytes),
            )
        )
    return picks
