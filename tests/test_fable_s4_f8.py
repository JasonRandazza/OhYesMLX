"""Fable 5.2 S4-F8: stage B runs the winner engine on a sibling that does not list it.

The finding: stage A filters its engines on the chosen row's ``engines``
(``quickbench.py:292``), but stage B's plan is every catalog sibling regardless of that
sibling's own ``engines`` (``quickbench.py:294-302``), and the run hands the winner to each
of them with no ``top["engine"] in sibling.engines`` test (``quickbench.py:895``). With a
real catalog whose sibling rows carry different engine lists, the run would download a
model the engine cannot serve and measure it anyway.

No shipped base has such rows (all twelve catalog rows list all five engines, and
``test_catalog.py:428-433`` pins that), so this drives the module's own injected ``models``
argument with a two-row base: the chosen row lists ``mlxlm`` only, its sibling ``optiq``
only, and ``mlxlm`` wins stage A. Every side effect is the fake from ``test_quickbench``;
nothing is downloaded, started or written outside ``tmp_path``.
"""

from __future__ import annotations

from test_quickbench import a_model, a_run, an_engine

CHOSEN = a_model("org/two-b-stock", "stock4bit", "TwoB", engine_names=("mlxlm",))
SIBLING = a_model(
    "org/two-b-oq4", "oq4", "TwoB", size_bytes=3_000_000_000, engine_names=("optiq",)
)
MODELS = [CHOSEN, SIBLING]
ENGINES = [an_engine("mlxlm"), an_engine("optiq")]


def test_stage_b_skips_a_sibling_that_does_not_list_the_winner_engine(tmp_path):
    ok, fakes, summary = a_run(
        tmp_path,
        models=MODELS,
        engines_list=ENGINES,
        downloaded=(CHOSEN.repo,),
    )

    assert ok is True
    assert summary["stage_a"]["winner"] == "mlxlm"

    # The sibling's row lists optiq only, so the winner cannot serve it: it is neither
    # downloaded nor measured, and the summary says why instead of calling it a failure.
    assert fakes.cache.downloads == []
    assert [call["cells"][0].id for call in fakes.run_cells.calls] == ["stock4bit__mlxlm"]
    stage_b = summary["stage_b"]["cells"]
    assert stage_b[0]["reused"] is True
    assert len(stage_b) == 2
    assert stage_b[1]["format"] == SIBLING.format
    assert stage_b[1]["status"] == "SKIPPED"
    assert "not listed" in stage_b[1]["reason"]
    assert "mlxlm" in stage_b[1]["reason"]


def test_plan_output_is_unchanged_for_a_mixed_engine_base(tmp_path):
    from types import SimpleNamespace

    from ohyesmlx import quickbench
    from test_quickbench import FakeCache

    cache = FakeCache(downloaded=(CHOSEN.repo,))
    shown = quickbench.plan(
        CHOSEN.repo,
        SimpleNamespace(),
        ENGINES,
        MODELS,
        cache_dir=str(tmp_path / "cache"),
        downloaded=cache.downloaded,
    )
    # The unlisted sibling is still planned and still counted: the skip is a run-time one.
    assert [p.repo for p in shown.stage_b] == [SIBLING.repo]
    assert shown.download_bytes == SIBLING.size_bytes
