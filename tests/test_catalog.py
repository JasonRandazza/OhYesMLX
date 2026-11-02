"""Checks for ohyesmlx.catalog.

The loader is driven against a temporary file: :func:`entry` is one valid row, and every
refusal below breaks exactly one field of it, so the message that names a field is the
field's own and not a neighbour's.

The shipped-file checks compare against literals from
``docs/research/2026-10-30-phase3-models.md`` -- the approved rows, the research table's
sizes, and the 2 GiB bound -- never against values read back out of the catalog under
test. A row that drifted, or a file that lost a row, fails here rather than in a
downloader.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from ohyesmlx import catalog
from ohyesmlx.catalog import load

SHA256 = "f5a0d9dd" + "0" * 56
GIT_OID = "52373fe24473b1aa44333d318f578ae6bf04b49b"
REVISION = "0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"

# The five engines of Decision D2, spelled out rather than read from engines.py: a sixth
# name there is a deliberate catalog decision and not something a row inherits silently.
ENGINES = ("mlxlm", "osaurus", "omlx", "optiq", "vmlx")

GIB = 1024**3


def entry(**overrides):
    """One valid catalog row; a check breaks exactly one field of it."""
    row = {
        "repo": "mlx-community/Qwen3.5-4B-4bit",
        "title": "Qwen3.5 4B 4-bit",
        "params": 4_659_865_088,
        "format": "mlx affine 4-bit gs64",
        "modality": "vision-language",
        "license": "apache-2.0",
        "tier": "standard",
        "revision": REVISION,
        "size_bytes": 401,
        "files": [
            {"path": "config.json", "size": 1, "sha256": None, "git_oid": GIT_OID},
            {"path": "model.safetensors", "size": 400, "sha256": SHA256, "git_oid": None},
        ],
        "engines": ["mlxlm", "omlx"],
        "measured_here": True,
        "notes": "one row, for the loader",
    }
    row.update(overrides)
    return row


def write(tmp_path, models, **header):
    """A catalog file of *models* at *tmp_path*; the header is the shipped one by default."""
    payload = {"built": "2026-11-01", "models": models}
    payload.update(header)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def refusal(path, row):
    with pytest.raises(ValueError) as raised:
        load(write(Path(path), [row]))
    return str(raised.value)


# --------------------------------------------------------------------------------------
# AC-1: the loader validates, and a refusal names the file, the repo and the field
# --------------------------------------------------------------------------------------


def test_a_valid_entry_loads_as_the_recorded_values(tmp_path):
    (model,) = load(write(tmp_path, [entry()]))
    assert model.repo == "mlx-community/Qwen3.5-4B-4bit"
    assert model.params == 4_659_865_088
    assert model.modality == "vision-language"
    assert model.tier == "standard"
    assert model.revision == REVISION
    assert model.size_bytes == 401
    assert model.engines == ["mlxlm", "omlx"]
    assert model.measured_here is True
    assert [(f.path, f.size, f.sha256, f.git_oid) for f in model.files] == [
        ("config.json", 1, None, GIT_OID),
        ("model.safetensors", 400, SHA256, None),
    ]


def test_a_model_and_its_files_are_frozen(tmp_path):
    (model,) = load(write(tmp_path, [entry()]))
    with pytest.raises(FrozenInstanceError):
        model.tier = "starter"
    with pytest.raises(FrozenInstanceError):
        model.files[0].size = 2


def test_a_missing_catalog_is_refused_naming_the_file(tmp_path):
    path = tmp_path / "absent.json"
    with pytest.raises(ValueError) as raised:
        load(path)
    assert str(path) in str(raised.value)


def test_a_catalog_that_is_not_json_is_refused_naming_the_file(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as raised:
        load(path)
    assert str(path) in str(raised.value)


def test_a_catalog_without_a_build_date_is_refused_naming_the_file(tmp_path):
    path = write(tmp_path, [entry()])
    path.write_text(json.dumps({"models": [entry()]}), encoding="utf-8")
    with pytest.raises(ValueError) as raised:
        load(path)
    assert str(path) in str(raised.value)
    assert "built" in str(raised.value)


def test_a_catalog_without_a_models_list_is_refused_naming_the_file(tmp_path):
    path = write(tmp_path, "not a list")
    with pytest.raises(ValueError) as raised:
        load(path)
    assert str(path) in str(raised.value)
    assert "models" in str(raised.value)


def test_an_entry_that_is_not_an_object_is_refused_naming_the_file(tmp_path):
    path = write(tmp_path, ["mlx-community/Qwen3.5-4B-4bit"])
    with pytest.raises(ValueError) as raised:
        load(path)
    assert str(path) in str(raised.value)
    assert "0" in str(raised.value)


def test_a_repo_that_is_not_org_slash_name_is_refused_naming_the_file(tmp_path):
    path = tmp_path / "catalog.json"
    for repo in ("Qwen3.5-4B-4bit", "mlx-community/Qwen3.5-4B-4bit/extra", "org /name"):
        message = refusal(tmp_path, entry(repo=repo))
        assert str(path) in message
        assert "repo" in message


def test_every_required_field_is_named_when_it_is_missing(tmp_path):
    path = tmp_path / "catalog.json"
    for field in (
        "title",
        "params",
        "format",
        "modality",
        "license",
        "tier",
        "revision",
        "size_bytes",
        "files",
        "engines",
        "measured_here",
        "notes",
    ):
        row = entry()
        del row[field]
        message = refusal(tmp_path, row)
        assert str(path) in message, f"a missing {field} named no file"
        assert row["repo"] in message, f"a missing {field} named no repo"
        assert field in message, f"a missing {field} was not named"


def test_a_params_that_is_not_an_integer_is_refused(tmp_path):
    path = tmp_path / "catalog.json"
    for params in (751_632_384.0, "751632384", True):
        message = refusal(tmp_path, entry(params=params))
        assert str(path) in message
        assert entry()["repo"] in message
        assert "params" in message


def test_a_modality_outside_the_two_is_refused(tmp_path):
    message = refusal(tmp_path, entry(modality="image"))
    assert "modality" in message
    assert entry()["repo"] in message


def test_a_tier_outside_the_two_is_refused(tmp_path):
    message = refusal(tmp_path, entry(tier="large"))
    assert "tier" in message
    assert entry()["repo"] in message


def test_a_revision_that_is_not_a_commit_is_refused(tmp_path):
    for revision in ("main", REVISION[:12], REVISION.upper()):
        message = refusal(tmp_path, entry(revision=revision))
        assert "revision" in message, revision
        assert entry()["repo"] in message


def test_size_bytes_that_is_not_the_sum_of_the_files_is_refused(tmp_path):
    message = refusal(tmp_path, entry(size_bytes=402))
    assert "size_bytes" in message
    assert "401" in message and "402" in message
    assert entry()["repo"] in message


def test_an_entry_with_no_files_is_refused(tmp_path):
    message = refusal(tmp_path, entry(files=[], size_bytes=0))
    assert "files" in message
    assert entry()["repo"] in message


def test_a_file_path_that_is_absolute_is_refused(tmp_path):
    message = refusal(
        tmp_path,
        entry(
            size_bytes=401,
            files=[
                {"path": "/etc/passwd", "size": 401, "sha256": SHA256, "git_oid": None}
            ],
        ),
    )
    assert "files" in message
    assert "/etc/passwd" in message


def test_a_file_size_that_is_not_an_integer_is_refused(tmp_path):
    message = refusal(
        tmp_path,
        entry(
            files=[{"path": "config.json", "size": "401", "sha256": None, "git_oid": GIT_OID}]
        ),
    )
    assert "size" in message
    assert "config.json" in message


def test_a_sha256_that_is_not_64_hex_is_refused(tmp_path):
    for sha in (SHA256[:63], "z" * 64, ""):
        message = refusal(
            tmp_path,
            entry(
                files=[
                    {"path": "model.safetensors", "size": 401, "sha256": sha, "git_oid": None}
                ]
            ),
        )
        assert "sha256" in message, sha
        assert "model.safetensors" in message


def test_a_file_with_neither_a_sha256_nor_a_git_oid_is_refused(tmp_path):
    message = refusal(
        tmp_path,
        entry(files=[{"path": "config.json", "size": 401, "sha256": None, "git_oid": None}]),
    )
    assert "config.json" in message
    assert "sha256" in message and "git_oid" in message


def test_a_file_with_both_a_sha256_and_a_git_oid_is_refused(tmp_path):
    """One file has one verifiable identity; two would leave the downloader choosing which
    of them the catalog means."""
    message = refusal(
        tmp_path,
        entry(
            files=[
                {"path": "config.json", "size": 401, "sha256": SHA256, "git_oid": GIT_OID}
            ]
        ),
    )
    assert "config.json" in message
    assert "sha256" in message and "git_oid" in message
    assert entry()["repo"] in message


@pytest.mark.parametrize("path", ["a\\b", "a\x00b", "a//b", ""])
def test_the_shared_path_guard_refuses_at_load(tmp_path, path):
    """`catalog.check_path` is the one guard; the loader applies it to every file, so a
    hostile literal is refused when the catalog is read rather than when a download starts."""
    message = refusal(
        tmp_path,
        entry(files=[{"path": path, "size": 401, "sha256": None, "git_oid": GIT_OID}]),
    )
    assert "files" in message
    assert entry()["repo"] in message


def test_a_git_oid_that_is_not_40_hex_is_refused(tmp_path):
    message = refusal(
        tmp_path,
        entry(
            files=[
                {"path": "config.json", "size": 401, "sha256": None, "git_oid": GIT_OID[:12]}
            ]
        ),
    )
    assert "git_oid" in message
    assert "config.json" in message


def test_an_unknown_engine_is_refused(tmp_path):
    message = refusal(tmp_path, entry(engines=["mlxlm", "mtplx"]))
    assert "engines" in message
    assert "mtplx" in message
    assert entry()["repo"] in message


def test_measured_here_that_is_not_a_boolean_is_refused(tmp_path):
    message = refusal(tmp_path, entry(measured_here="yes"))
    assert "measured_here" in message
    assert entry()["repo"] in message


def test_notes_that_are_not_a_string_is_refused(tmp_path):
    message = refusal(tmp_path, entry(notes=None))
    assert "notes" in message
    assert entry()["repo"] in message


# --------------------------------------------------------------------------------------
# AC-2 and AC-3: the shipped seed is exactly the approved set, and nothing beyond it
# --------------------------------------------------------------------------------------

# Research table rows 1-8 and 10-11 (rows 9 and 12 are over the disk cap; row 9 is
# gemma-4-e2b, which the plan keeps out of the seed).
STARTER = [
    "mlx-community/Qwen3-0.6B-4bit",
    "mlx-community/Qwen3.5-0.8B-4bit",
    "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
    "mlx-community/LFM2.5-1.2B-Instruct-4bit",
    "mlx-community/granite-4.0-h-1b-4bit",
    "mlx-community/Qwen3.5-2B-4bit",
    "RepublicOfKorokke/Qwen3.5-2B-oQ4",
    "mlx-community/LFM2.5-2.6B-4bit",
    "mlx-community/SmolLM3-3B-4bit",
    "mlx-community/Llama-3.2-3B-Instruct-4bit",
]

# The tier above the cap: the two artifacts this Mac has really measured.
STANDARD = [
    "mlx-community/Qwen3.5-4B-4bit",
    "mlx-community/LFM2.5-8B-A1B-MLX-4bit",
]

# The research's own size_bytes, row by row (section 5, and section 4.1 for the 4B stock
# artifact, which section 5 does not list). The 4B figure is the Hub listing's sum: the
# 3,061,131,520 in section 4.1 is the harness's walk of the local snapshot, whose
# model.safetensors is 873 B longer than the file the Hub lists.
RESEARCH_SIZE_BYTES = {
    "mlx-community/Qwen3-0.6B-4bit": 351_386_061,
    "mlx-community/Qwen3.5-0.8B-4bit": 652_029_391,
    "mlx-community/Qwen3.5-0.8B-OptiQ-4bit": 886_129_146,
    "mlx-community/LFM2.5-1.2B-Instruct-4bit": 663_395_788,
    "mlx-community/granite-4.0-h-1b-4bit": 833_197_077,
    "mlx-community/Qwen3.5-2B-4bit": 1_749_081_927,
    "RepublicOfKorokke/Qwen3.5-2B-oQ4": 1_794_528_789,
    "mlx-community/LFM2.5-2.6B-4bit": 1_535_593_294,
    "mlx-community/SmolLM3-3B-4bit": 1_747_380_812,
    "mlx-community/Llama-3.2-3B-Instruct-4bit": 1_824_825_759,
    "mlx-community/Qwen3.5-4B-4bit": 3_061_130_647,
    "mlx-community/LFM2.5-8B-A1B-MLX-4bit": 4_782_228_614,
}


def shipped():
    return load()


def test_the_starter_tier_is_the_approved_set():
    assert sorted(m.repo for m in shipped() if m.tier == "starter") == sorted(STARTER)


def test_the_standard_tier_is_the_approved_set():
    assert sorted(m.repo for m in shipped() if m.tier == "standard") == sorted(STANDARD)


def test_the_seed_holds_exactly_the_twelve_approved_rows():
    assert len(shipped()) == len(STARTER) + len(STANDARD)


def test_every_starter_row_fits_the_2_gib_cap():
    for model in shipped():
        if model.tier == "starter":
            assert model.size_bytes <= 2 * GIB, model.repo


def test_gemma_4_e2b_is_not_in_the_seed():
    assert not [m for m in shipped() if "gemma" in m.repo.lower()]
    assert not [m for m in shipped() if m.size_bytes == 3_583_088_661]


def test_measured_here_is_true_only_for_the_two_standard_rows():
    assert sorted(m.repo for m in shipped() if m.measured_here) == sorted(STANDARD)


def test_size_bytes_matches_the_research_table():
    assert {m.repo: m.size_bytes for m in shipped()} == RESEARCH_SIZE_BYTES


def test_every_entry_sizes_sum_to_its_files():
    for model in shipped():
        assert model.size_bytes == sum(f.size for f in model.files), model.repo


def test_every_entry_lists_exactly_the_five_engines_the_table_marks():
    # "all 5" is the research table's own column for all twelve rows. A sixth engine name
    # is a catalog decision: it has to be checked against this table before it is offered.
    for model in shipped():
        assert set(model.engines) <= set(ENGINES), model.repo
        assert sorted(model.engines) == sorted(ENGINES), model.repo


def test_every_entry_pins_a_commit_and_a_hash_for_its_weights():
    for model in shipped():
        assert len(model.revision) == 40, model.repo
        int(model.revision, 16)
        assert [f for f in model.files if f.sha256], model.repo


def test_the_catalog_records_one_build_date():
    payload = json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8"))
    assert date.fromisoformat(payload["built"])


def test_the_catalog_ships_beside_the_module_like_the_engines_manifest():
    assert catalog.CATALOG_PATH == Path(catalog.__file__).resolve().with_name("catalog.json")
    pyproject = Path(catalog.__file__).resolve().parent.parent / "pyproject.toml"
    assert "force-include" not in pyproject.read_text(encoding="utf-8")


def test_the_download_disk_margin_is_defined_once_here_and_is_one_point_two():
    # Both the recommender (can this fit?) and the downloader (may it start?) ask this
    # constant; the extra 20% covers a largest-shard `.incomplete` beside the finished files
    # (docs/research/2026-10-30-phase3-models.md section 4.3).
    assert catalog.DISK_MARGIN == 1.2


def test_disk_needed_is_the_one_disk_rule_rounded_up():
    # 10 bytes x 1.2 is exactly 12; 11 x 1.2 is 13.2 and must round up rather than to 13.
    assert catalog.disk_needed(0) == 0
    assert catalog.disk_needed(10) == 12
    assert catalog.disk_needed(11) == 14
