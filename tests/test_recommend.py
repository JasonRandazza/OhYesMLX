"""Checks for ohyesmlx.recommend.

Every expected value here is a literal. The byte counts are the research table's
(``docs/research/2026-10-30-phase3-models.md`` section 5), the three budgets are
``hardware.model_budget``'s own for an 8 GiB, a 16 GiB and a 64 GiB Mac, and every reason
string is written out in full -- so a constant that moved fails here rather than on a
screen. Fixtures are tiny hand-built rows: no catalog file, no Mac, no server.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from ohyesmlx.catalog import Model, ModelFile
from ohyesmlx.engines import EngineStatus
from ohyesmlx.hardware import Hardware
from ohyesmlx.recommend import Pick, exclusion_reason, pick

# hardware.model_budget's own answers: two thirds of unified memory less 2 GiB under 36 GiB.
BUDGET_8_GIB = 3_579_139_413
BUDGET_16_GIB = 9_305_762_474
BUDGET_64_GIB = 49_392_123_904

# Free disk: enough for every row unless a check is about disk, and AC-4's 20 GiB line.
PLENTY_OF_DISK = 500 * 1024**3
UNDER_20_GIB = 19 * 1024**3

# Three rows from the research table, at the table's own base-parameter and size bytes.
QWEN_06B = dict(
    repo="mlx-community/Qwen3-0.6B-4bit",
    params=751_632_384,
    size=351_386_061,
    tier="starter",
)
QWEN_2B_OQ4 = dict(
    repo="RepublicOfKorokke/Qwen3.5-2B-oQ4",
    params=2_274_069_824,
    size=1_794_528_789,
    tier="starter",
)
LFM_8B = dict(
    repo="mlx-community/LFM2.5-8B-A1B-MLX-4bit",
    params=8_467_856_832,
    size=4_782_228_614,
    tier="standard",
)


def hardware(budget, *, ram=8 * 1024**3, supported=True, unsupported_reason=None):
    """A Hardware as ``scan`` would report it, with *budget* handed in as a literal."""
    return Hardware(
        supported=supported,
        unsupported_reason=unsupported_reason,
        chip="Apple M2",
        family="M2",
        tier="base",
        cpu_cores=8,
        gpu_cores=None,
        ram_bytes=ram,
        macos="15.4",
        disk_free_bytes=0,
        volumes=[],
        model_budget_bytes=budget,
    )


def model(
    *,
    repo="mlx-community/fixture-1b",
    params=1_000_000_000,
    size=1_000_000_000,
    tier="starter",
    engines=("mlxlm",),
    measured_here=False,
):
    """One catalog row; the file list is cosmetic, because recommend never reads it."""
    return Model(
        repo=repo,
        title=repo,
        params=params,
        format="mlx affine 4-bit gs64",
        modality="text",
        license="apache-2.0",
        tier=tier,
        revision="0" * 40,
        size_bytes=size,
        files=[ModelFile(path="model.safetensors", size=size, sha256="0" * 64, git_oid=None)],
        engines=list(engines),
        measured_here=measured_here,
        notes="fixture",
    )


def status(name, *, installed):
    """One EngineStatus as ``detect_all`` reports it, with nothing installed but the name."""
    return EngineStatus(
        name=name,
        title=name,
        blurb="",
        installed=installed,
        version=None,
        path=None,
        tested=False,
        verified=None,
        install=None,
    )


# --------------------------------------------------------------------------------------
# AC-1: the fit rule, one definition
# --------------------------------------------------------------------------------------


def test_comfortable_when_twice_the_weights_fits_the_budget():
    [only] = pick(hardware(2_000_000_000), [model(size=1_000_000_000)], [], PLENTY_OF_DISK)
    assert only.fit == "comfortable"


def test_tight_at_exactly_1_25_times_the_budget():
    [only] = pick(hardware(1_250_000_000), [model(size=1_000_000_000)], [], PLENTY_OF_DISK)
    assert only.fit == "tight"


def test_excluded_past_1_25_times_the_budget():
    size = 1_000_000_000
    assert pick(hardware(1_000_000_000), [model(size=size)], [], PLENTY_OF_DISK) == []
    assert exclusion_reason(model(size=size), hardware(1_000_000_000), PLENTY_OF_DISK) == (
        "Needs about 2.0 GB of memory at peak; this Mac's budget is 1.0 GB"
    )


def test_16_gib_mac_holds_the_8b_moe_as_tight():
    [only] = pick(hardware(BUDGET_16_GIB), [model(**LFM_8B)], [], PLENTY_OF_DISK)
    assert only.fit == "tight"


def test_8_gib_mac_holds_the_2b_oq4_as_tight_only():
    [only] = pick(hardware(BUDGET_8_GIB), [model(**QWEN_2B_OQ4)], [], PLENTY_OF_DISK)
    assert only.fit == "tight"


def test_8_gib_mac_excludes_the_8b_moe():
    assert pick(hardware(BUDGET_8_GIB), [model(**LFM_8B)], [], PLENTY_OF_DISK) == []
    assert exclusion_reason(model(**LFM_8B), hardware(BUDGET_8_GIB), PLENTY_OF_DISK) == (
        "Needs about 9.6 GB of memory at peak; this Mac's budget is 3.6 GB"
    )


# --------------------------------------------------------------------------------------
# AC-2: disk fit, and a Mac the catalog refuses to advise
# --------------------------------------------------------------------------------------


def test_disk_needs_the_catalog_margin_over_the_download():
    hw = hardware(BUDGET_64_GIB)
    fits = model(repo="mlx-community/fits", size=1_000_000_000)
    # 1.2 GB free is exactly the 1.2x the download needs; 1.1 GB is above the bare
    # download and still short of it; 0.9 GB is not.
    assert [p.model_id for p in pick(hw, [fits], [], 1_200_000_000)] == ["mlx-community/fits"]
    assert pick(hw, [fits], [], 1_100_000_000) == []
    assert pick(hw, [fits], [], 900_000_000) == []
    assert exclusion_reason(fits, hw, 900_000_000) == (
        "Needs about 1.2 GB of free disk to download; this Mac has 0.9 GB free"
    )


def test_exclusion_reason_is_none_for_a_model_that_fits():
    assert exclusion_reason(model(**QWEN_06B), hardware(BUDGET_64_GIB), PLENTY_OF_DISK) is None


def test_an_unsupported_mac_gets_no_pick():
    hw = hardware(
        BUDGET_64_GIB,
        ram=64 * 1024**3,
        supported=False,
        unsupported_reason="this Mac is not Apple silicon",
    )
    # The row clears both budgets; only the supported flag removes it.
    assert pick(hw, [model(**QWEN_06B)], [], PLENTY_OF_DISK) == []


def test_the_unsupported_sentence_is_never_copied_into_a_reason():
    hw = hardware(
        0,
        ram=4 * 1024**3,
        supported=False,
        unsupported_reason="this Mac has less than 8 GiB of unified memory",
    )
    reason = exclusion_reason(model(size=1_000_000_000), hw, PLENTY_OF_DISK)
    assert reason == "Needs about 2.0 GB of memory at peak; this Mac's budget is 0.0 GB"
    assert "unified memory" not in reason


# --------------------------------------------------------------------------------------
# AC-3: engines
# --------------------------------------------------------------------------------------


def test_a_pick_lists_the_installed_engines_for_that_row():
    engines = [
        status("mlxlm", installed=True),
        status("osaurus", installed=False),
        status("omlx", installed=True),
    ]
    [only] = pick(
        hardware(BUDGET_64_GIB),
        [model(engines=("mlxlm", "osaurus"))],
        engines,
        PLENTY_OF_DISK,
    )
    assert only.engines == ["mlxlm"]
    assert only.install_needed is False


def test_install_needed_lists_every_catalog_engine_when_none_is_installed():
    # OptiQ is installed, but this row cannot be served by it.
    [only] = pick(
        hardware(BUDGET_64_GIB),
        [model(engines=("mlxlm", "omlx"))],
        [status("optiq", installed=True)],
        PLENTY_OF_DISK,
    )
    assert only.engines == ["mlxlm", "omlx"]
    assert only.install_needed is True


def test_install_needed_when_no_engine_is_detected_at_all():
    [only] = pick(
        hardware(BUDGET_64_GIB),
        [model(engines=("optiq", "vmlx"))],
        [],
        PLENTY_OF_DISK,
    )
    assert only.engines == ["optiq", "vmlx"]
    assert only.install_needed is True


# --------------------------------------------------------------------------------------
# AC-4: ranking
# --------------------------------------------------------------------------------------


def test_comfortable_outranks_tight_whatever_the_parameter_count():
    small = model(repo="mlx-community/small", params=1_000_000_000, size=1_000_000_000)
    picks = pick(
        hardware(BUDGET_16_GIB),
        [model(**LFM_8B), small],
        [status("mlxlm", installed=True)],
        PLENTY_OF_DISK,
    )
    assert [p.model_id for p in picks] == [
        "mlx-community/small",
        "mlx-community/LFM2.5-8B-A1B-MLX-4bit",
    ]
    assert [p.fit for p in picks] == ["comfortable", "tight"]


def test_more_parameters_come_first_within_a_fit():
    picks = pick(
        hardware(BUDGET_64_GIB),
        [
            model(repo="mlx-community/one-b", params=1_000_000_000),
            model(repo="mlx-community/three-b", params=3_000_000_000),
        ],
        [status("mlxlm", installed=True)],
        PLENTY_OF_DISK,
    )
    assert [p.model_id for p in picks] == ["mlx-community/three-b", "mlx-community/one-b"]


def test_starter_tier_comes_first_when_free_disk_is_under_20_gib():
    rows = [
        model(
            repo="mlx-community/standard-4b",
            params=4_000_000_000,
            size=1_000_000_000,
            tier="standard",
        ),
        model(
            repo="mlx-community/starter-1b",
            params=1_000_000_000,
            size=1_000_000_000,
            tier="starter",
        ),
    ]
    engines = [status("mlxlm", installed=True)]
    assert [p.model_id for p in pick(hardware(BUDGET_64_GIB), rows, engines, UNDER_20_GIB)] == [
        "mlx-community/starter-1b",
        "mlx-community/standard-4b",
    ]
    # At exactly 20 GiB the disk stops being scarce, so larger parameters win again.
    assert [
        p.model_id for p in pick(hardware(BUDGET_64_GIB), rows, engines, 20 * 1024**3)
    ] == ["mlx-community/standard-4b", "mlx-community/starter-1b"]


def test_ties_break_by_repo_id():
    picks = pick(
        hardware(BUDGET_64_GIB),
        [
            model(repo="mlx-community/zeta", params=2_000_000_000),
            model(repo="mlx-community/alpha", params=2_000_000_000),
        ],
        [status("mlxlm", installed=True)],
        PLENTY_OF_DISK,
    )
    assert [p.model_id for p in picks] == ["mlx-community/alpha", "mlx-community/zeta"]


def test_the_first_three_are_start_here():
    rows = [
        model(repo=f"mlx-community/row-{index}", params=1_000_000_000 + index)
        for index in range(5)
    ]
    picks = pick(
        hardware(BUDGET_64_GIB), rows, [status("mlxlm", installed=True)], PLENTY_OF_DISK
    )
    assert [p.model_id for p in picks] == [
        "mlx-community/row-4",
        "mlx-community/row-3",
        "mlx-community/row-2",
        "mlx-community/row-1",
        "mlx-community/row-0",
    ]
    assert [p.start_here for p in picks] == [True, True, True, False, False]


def test_fewer_than_three_picks_are_all_start_here():
    picks = pick(
        hardware(BUDGET_64_GIB), [model(repo="mlx-community/only")], [], PLENTY_OF_DISK
    )
    assert [p.start_here for p in picks] == [True]


# --------------------------------------------------------------------------------------
# AC-5: reasons are fixed templates with numbers, and no speed claim
# --------------------------------------------------------------------------------------


def test_comfortable_reason_is_the_fixed_template():
    [only] = pick(hardware(BUDGET_16_GIB), [model(**QWEN_2B_OQ4)], [], PLENTY_OF_DISK)
    assert only.reason == "Fits with about 7.5 GB of memory to spare; 1.8 GB download"
    assert "tok/s" not in only.reason
    assert "M2" not in only.reason


def test_tight_reason_is_the_fixed_template():
    [only] = pick(hardware(BUDGET_8_GIB), [model(**QWEN_2B_OQ4)], [], PLENTY_OF_DISK)
    assert only.reason == "Tight fit, about 1.8 GB of memory to spare; 1.8 GB download"
    assert "tok/s" not in only.reason
    assert "M2" not in only.reason


# --------------------------------------------------------------------------------------
# AC-6: the pinned Pick shape
# --------------------------------------------------------------------------------------


def test_pick_has_exactly_the_pinned_fields():
    assert [field.name for field in fields(Pick)] == [
        "model_id",
        "title",
        "params_b",
        "format",
        "size_bytes",
        "fit",
        "fit_basis",
        "engines",
        "install_needed",
        "start_here",
        "reason",
        "measured_here",
    ]


def test_params_b_is_the_base_count_in_billions_to_one_decimal():
    [only] = pick(hardware(BUDGET_64_GIB), [model(**QWEN_06B)], [], PLENTY_OF_DISK)
    assert only.params_b == 0.8


def test_pick_is_frozen_and_carries_no_measurement_here():
    [only] = pick(
        hardware(BUDGET_64_GIB),
        [model(**LFM_8B, measured_here=True)],
        [],
        PLENTY_OF_DISK,
    )
    assert only.model_id == "mlx-community/LFM2.5-8B-A1B-MLX-4bit"
    assert only.title == "mlx-community/LFM2.5-8B-A1B-MLX-4bit"
    assert only.params_b == 8.5
    assert only.format == "mlx affine 4-bit gs64"
    assert only.size_bytes == 4_782_228_614
    assert only.fit_basis == "estimated"
    assert only.measured_here is None
    with pytest.raises(FrozenInstanceError):
        only.fit = "tight"
