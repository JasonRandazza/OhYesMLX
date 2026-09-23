"""Tests for ohyesmlx.pareto visualization module."""

from __future__ import annotations

import pytest

from ohyesmlx import cli, pareto


def test_build_pareto_dataset_contains_expected_models_and_keys():
    dataset = pareto.build_pareto_dataset()
    assert len(dataset) >= 15

    required_keys = {
        "id",
        "model",
        "model_type",
        "format",
        "runtime",
        "decode_tps",
        "peak_mb",
        "disk_gb",
        "frontier",
        "role",
        "verdict",
    }
    models = set()
    runtimes = set()

    for entry in dataset:
        assert required_keys.issubset(entry.keys()), f"entry {entry.get('id')} missing keys"
        assert entry["decode_tps"] > 0
        assert entry["peak_mb"] > 0
        assert entry["disk_gb"] > 0
        assert entry["frontier"] in {"on", "off", "undetermined"}
        models.add(entry["model"])
        runtimes.add(entry["runtime"])

    assert "Qwen3.5-4B" in models
    assert "LFM2.5-8B-A1B" in models
    assert "Qwen3.6-35B-A3B" in models
    assert {"vMLX", "Osaurus"}.issubset(runtimes)


def test_generate_pareto_html_creates_valid_standalone_document():
    html = pareto.generate_pareto_html()
    assert html.startswith("<!DOCTYPE html>")
    assert "<svg" in html
    assert "Pareto" in html
    assert "RAW_DATA" in html
    assert "JANG_4S" in html
    assert "stock4bit" in html
    assert "Qwen3.5-4B" in html
    assert "LFM2.5-8B-A1B" in html
    assert "Qwen3.6-35B-A3B" in html


def test_save_pareto_html_writes_file(tmp_path):
    target = tmp_path / "sub" / "pareto_report.html"
    result = pareto.save_pareto_html(target)
    assert result == target
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert len(content) > 5000
    assert "<!DOCTYPE html>" in content


def test_cli_pareto_command_generates_file_and_exits_zero(tmp_path, capsys):
    target = tmp_path / "custom_pareto.html"
    code = cli.main(["pareto", "--out", str(target)])
    assert code == 0
    assert target.exists()
    assert target.stat().st_size > 5000

    out = capsys.readouterr().out
    assert "wrote interactive visualization to" in out
    assert str(target) in out


def test_cli_pareto_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["pareto", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage: ohyesmlx pareto" in out
    assert "--out" in out
