"""S4-F6: the memory sentences state numbers the fit rule does not use.

``_fit`` decides a row with one of two multiples of ``size_bytes`` against
``Hardware.model_budget_bytes``: comfortable at ``COMFORTABLE_FACTOR`` (2.0), tight at
``TIGHT_FACTOR`` (1.25), otherwise the row is left out (``recommend.py:87-93``). Two
user-facing sentences then quote two other multiples of the same size:

- ``exclusion_reason`` says the row "Needs about {size * COMFORTABLE_FACTOR} GB of memory at
  peak" (``recommend.py:135-137``) -- the 2x line, not the 1.25x line that actually left the
  row out;
- ``_reason`` says "about {budget - size} GB of memory to spare" (``recommend.py:108-112``)
  -- the 1x weights, not the 2x/1.25x line that decided the fit.

So a row can be offered with "memory to spare" while the module's own peak sentence puts it
above the budget. The tests below pin the two contradictions the finding names; the failing
cases fail on the shipped code by design. They are the finding's evidence, not a proposed
copy fix: the sentence text that replaces them is a wording decision, so the assertions are
written against the fit rule's factors, which any coherent sentence must use.
"""

from __future__ import annotations

import re

import pytest

from ohyesmlx.catalog import Model, ModelFile
from ohyesmlx.hardware import Hardware
from ohyesmlx.recommend import (
    COMFORTABLE_FACTOR,
    TIGHT_FACTOR,
    exclusion_reason,
    pick,
)

# hardware.model_budget's own answers for the two Macs in the finding.
BUDGET_8_GIB = 3_579_139_413  # shown as 3.6 GB
BUDGET_16_GIB = 9_305_762_474  # shown as 9.3 GB

PLENTY_OF_DISK = 500 * 1024**3
GB = 1_000_000_000

# The catalog's own sizes, the finding's rows: the 2B oQ4 it names at 1.82 GB, the 8B MoE at
# 4.78 GB, and a 3.06 GB row for the exclusion half of its 8 GiB scenario.
QWEN_2B_OQ4_BYTES = 1_794_528_789
LFM_8B_BYTES = 4_782_228_614
ROW_3_06_BYTES = 3_060_000_000


def hardware(budget):
    """A Hardware as ``scan`` would report it, with *budget* handed in as a literal."""
    return Hardware(
        supported=True,
        unsupported_reason=None,
        chip="Apple M2",
        family="M2",
        tier="base",
        cpu_cores=8,
        gpu_cores=None,
        ram_bytes=8 * 1024**3,
        macos="15.4",
        disk_free_bytes=0,
        volumes=[],
        model_budget_bytes=budget,
    )


def model(size, repo="mlx-community/fixture"):
    """One catalog row; the file list is cosmetic, because recommend never reads it."""
    return Model(
        repo=repo,
        title=repo,
        params=1_000_000_000,
        format="mlx affine 4-bit gs64",
        modality="text",
        license="apache-2.0",
        tier="starter",
        revision="0" * 40,
        size_bytes=size,
        files=[ModelFile(path="model.safetensors", size=size, sha256="0" * 64, git_oid=None)],
        engines=["mlxlm"],
        measured_here=False,
        notes="fixture",
    )


def _memory_peak_gb(row):
    """The "memory at peak" figure the exclusion sentence states for *row*.

    The memory branch is reached by handing in a zero budget, and its need figure is a
    function of the row alone (the budget is quoted separately in the same sentence), so
    this is the number the module would print about the row on any Mac.
    """
    sentence = exclusion_reason(row, hardware(0), PLENTY_OF_DISK)
    assert sentence is not None, "a zero budget must take the memory branch"
    match = re.fullmatch(
        r"Needs about ([0-9]+\.[0-9]) GB of memory; "
        r"this Mac's budget is [0-9]+\.[0-9] GB",
        sentence,
    )
    assert match is not None, sentence
    return float(match.group(1))


def _spare_gb(reason):
    """The "memory to spare" figure in *reason*, or None when the sentence has none."""
    match = re.search(r"about ([0-9]+\.[0-9]) GB of memory to spare", reason)
    return None if match is None else float(match.group(1))


# --------------------------------------------------------------------------------------
# Contradiction 1: the number in the exclusion sentence is not the line the row missed.
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("budget", "size", "offered"),
    [
        pytest.param(BUDGET_16_GIB, QWEN_2B_OQ4_BYTES, True, id="16-gib-2b-comfortable"),
        pytest.param(BUDGET_8_GIB, QWEN_2B_OQ4_BYTES, True, id="8-gib-1.82-gb-tight"),
        pytest.param(BUDGET_16_GIB, LFM_8B_BYTES, True, id="16-gib-4.78-gb-tight"),
        pytest.param(BUDGET_8_GIB, ROW_3_06_BYTES, False, id="8-gib-3.06-gb-excluded"),
        pytest.param(BUDGET_8_GIB, LFM_8B_BYTES, False, id="8-gib-4.78-gb-excluded"),
    ],
)
def test_the_peak_the_memory_sentence_states_is_above_budget_only_for_a_left_out_row(
    budget, size, offered
):
    """The finding's test idea: parsed-back need <= budget exactly when ``pick`` offers it.

    The stated figure is read from the module's own memory sentence, not recomputed here.
    The excluded cases are the controls: their stated peak is genuinely above the budget, so
    the helper is not what fails. The two tight cases are the contradiction -- the sentence's
    own number is above the budget while ``pick`` offers the row.
    """
    hw = hardware(budget)
    row = model(size, "org/row")
    stated_peak = _memory_peak_gb(row) * GB
    assert (pick(hw, [row], [], PLENTY_OF_DISK) != []) is offered
    assert (stated_peak <= hw.model_budget_bytes) is offered, (
        f"the memory sentence states a peak of {stated_peak / GB:.1f} GB, the budget is "
        f"{hw.model_budget_bytes / GB:.2f} GB, and pick() "
        f"{'offers' if offered else 'leaves out'} the row"
    )


# --------------------------------------------------------------------------------------
# Contradiction 2: "to spare" subtracts one size, not the factor that decided the fit.
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("budget", "size", "fit", "factor"),
    [
        pytest.param(BUDGET_16_GIB, QWEN_2B_OQ4_BYTES, "comfortable", COMFORTABLE_FACTOR,
                     id="16-gib-2b-comfortable"),
        pytest.param(BUDGET_16_GIB, LFM_8B_BYTES, "tight", TIGHT_FACTOR,
                     id="16-gib-4.78-gb-tight"),
        pytest.param(BUDGET_8_GIB, QWEN_2B_OQ4_BYTES, "tight", TIGHT_FACTOR,
                     id="8-gib-1.82-gb-tight"),
    ],
)
def test_the_spare_figure_is_the_headroom_over_the_line_that_decided_the_fit(
    budget, size, fit, factor
):
    """A row's printed spare must be budget minus the factor the fit rule used for it.

    Comfortable rows are decided at 2x, tight rows at 1.25x. Today every printed spare is
    ``budget - size`` (1x). A tight row that drops the spare figure is allowed -- the
    finding's own fix direction offers that -- but a figure that is stated must match the
    line that decided the row.
    """
    hw = hardware(budget)
    [only] = pick(hw, [model(size, "org/row")], [], PLENTY_OF_DISK)
    assert only.fit == fit
    spare = _spare_gb(only.reason)
    if spare is None:
        assert fit == "tight", only.reason
        return
    headroom = (hw.model_budget_bytes - size * factor) / GB
    assert spare == round(headroom, 1), (
        f"{fit} row of {size / GB:.2f} GB: reason claims {spare} GB to spare; the "
        f"{factor}x line that decided the fit leaves {headroom:.1f} GB. Reason: "
        f"{only.reason!r}"
    )
