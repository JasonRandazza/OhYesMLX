"""Checks for the CLI's prompt-length pin.

No tokenizer is built and no model is loaded. ``sized_prompt`` is handed ``len(text.split())``
-- the counter the order names as simple enough for a test to drive it with -- and the run-level
tests drive ``cli.main`` against a stand-in for ``measure`` that records the one call it was
handed: what the CLI passes to ``run_cells`` is the question here, and what a run renders from
results is ``tests/test_report.py``'.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from ohyesmlx import cli

# Two formats, one runtime: a legal format-axis selection, and both cells share an artifact
# directory so the default fixture builds one counter for the pair.
CELLS = "oq4__mlxlm=/models/oq4,jang4__mlxlm=/models/oq4"
# The same selection with a second artifact, which is a second tokenizer.
TWO_ARTIFACTS = "oq4__mlxlm=/models/oq4,jang4__mlxlm=/models/other"

TARGETS = (200, 500, 1000, 4000)


class WordCounter:
    """A counter as simple as the contract allows: one word is one token."""

    def __init__(self, model_dir=None):
        self.model_dir = model_dir

    def count(self, text):
        return len(text.split())


class ThriceCounter(WordCounter):
    """A second artifact's tokenizer, disagreeing with the first about the same bytes: three
    tokens a word against the other's one, so the length it can achieve at a target is a
    different number rather than the same one reached by cutting half as much text."""

    def count(self, text):
        return 3 * len(text.split())


def word_counter(model_dir=None):
    return WordCounter(model_dir)


def cut_of(text: str) -> str:
    """The cut out of a sized prompt: what sits between the head and the tail."""
    assert text.startswith(cli.SIZED_HEAD), "the head asks the model to read the document"
    assert text.endswith(cli.SIZED_TAIL), "the tail asks what the document is about"
    return text[len(cli.SIZED_HEAD) : -len(cli.SIZED_TAIL)]


# --- the prompt the pin builds ---------------------------------------------------------------


def test_the_prompt_lands_at_or_under_the_target_and_counts_what_it_returns():
    """Both halves of the contract, on a counter that can land on the target exactly and one
    that cannot: one word is one token and reaches 500 of them, and three tokens a word stops
    under it. An ``achieved`` taken from the target instead of from the text passes the first
    counter and fails the second."""
    for counter_type in (WordCounter, ThriceCounter):
        for target in TARGETS:
            counter = counter_type()
            text, achieved = cli.sized_prompt(counter, target)

            assert achieved <= target, f"{target}: the pin promised a length it did not hold to"
            assert achieved == counter.count(text), (
                f"{target}: achieved is not what the counter says of the text returned"
            )

    assert cli.sized_prompt(ThriceCounter(), 500)[1] < 500, (
        "the fixture has a counter that cannot land on the target"
    )


def test_the_cut_ends_at_a_whitespace_boundary():
    """The cut is a prefix of the source, and it stops where whitespace begins rather than
    inside a word -- the whole point of a boundary being that no word is cut in half."""
    source = cli.sized_source()

    for target in TARGETS:
        cut = cut_of(cli.sized_prompt(WordCounter(), target)[0])

        assert cut, "the prompt holds some of the document"
        assert source.startswith(cut), "the prompt is cut from the source, not assembled"
        assert cut == source or source[len(cut)].isspace()


def test_a_larger_target_extends_the_prompt_a_smaller_one_made():
    """A sweep's lengths are the same prompt made longer: at a larger target the smaller one's
    cut is still there, at the front, with more document after it."""
    for small, large in ((200, 500), (500, 4000)):
        short = cut_of(cli.sized_prompt(WordCounter(), small)[0])
        long = cut_of(cli.sized_prompt(WordCounter(), large)[0])

        assert len(short) < len(long)
        assert long.startswith(short)


def test_a_target_that_needs_more_text_than_the_source_holds_is_refused():
    counter = WordCounter()
    whole = counter.count(cli.SIZED_HEAD + cli.sized_source() + cli.SIZED_TAIL)

    with pytest.raises(ValueError, match="more text than the source holds"):
        cli.sized_prompt(counter, whole + 1)


def test_a_target_too_small_for_the_head_and_the_tail_is_refused():
    counter = WordCounter()
    head_and_tail = counter.count(cli.SIZED_HEAD + cli.SIZED_TAIL)

    # Below the head and the tail there is no prompt to build at all.
    for target in (1, head_and_tail - 1):
        with pytest.raises(ValueError, match="cannot fit the head and the tail"):
            cli.sized_prompt(counter, target)

    # Exactly the head and the tail fits them and leaves nothing for the document, so the
    # prompt would ask what the document is about with no document in it. A different refusal,
    # and it says so: the two are one size apart and a reader has to be able to tell which one
    # their target hit.
    with pytest.raises(ValueError, match="fits only the head and the tail"):
        cli.sized_prompt(counter, head_and_tail)


def test_no_paragraph_of_the_source_appears_twice_in_a_prompt():
    """Padding with a repeated section would reach any target, and the prompt would then be a
    different prompt from the one its pin names.

    The source carries two identical code blocks of its own, so the property checked is the one
    the construction can break: the prompt holds **no more** copies of any paragraph than the
    prefix it was cut from does, and the head and the tail each appear exactly once.
    """
    source = cli.sized_source()
    paragraphs = [paragraph for paragraph in source.split("\n\n") if len(paragraph) >= 40]

    assert paragraphs, "the fixture has prose to check"
    for target in TARGETS:
        text, _achieved = cli.sized_prompt(WordCounter(), target)
        cut = cut_of(text)

        assert text.count(cli.SIZED_HEAD) == 1
        assert text.count(cli.SIZED_TAIL) == 1
        for paragraph in paragraphs:
            assert text.count(paragraph) == cut.count(paragraph), (
                f"{target}: the prompt holds a copy of a paragraph the cut does not"
            )


# --- the run the pin drives ------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FakeCell:
    id: str
    runtime: str
    artifact_dir: str
    label: str


@dataclasses.dataclass(frozen=True)
class FakeWorkload:
    """``measure.Workload``'s shape: the CLI constructs these and forwards them."""

    id: str
    messages: list
    max_tokens: int


class FakeMeasure:
    """The one ``run_cells`` call the CLI makes, recorded. No runtime, no results, no file."""

    Cell = FakeCell
    Workload = FakeWorkload

    def __init__(self):
        self.calls = []

    def run_cells(self, cells, workloads, **kwargs):
        self.calls.append({"cells": cells, "workloads": workloads, **kwargs})
        return []


@pytest.fixture
def measure(monkeypatch):
    fake = FakeMeasure()
    monkeypatch.setattr(cli, "_load_measure", lambda: fake)
    monkeypatch.setattr(cli, "token_counter", SimpleNamespace(TokenCounter=word_counter))
    return fake


def run(tmp_path, *flags):
    return cli.main(
        [
            "run",
            "--study",
            "format",
            "--cells",
            CELLS,
            "--results-dir",
            str(tmp_path / "results"),
            *flags,
        ]
    )


def test_a_run_pinning_the_cache_state_passes_it_to_the_loop_and_defaults_to_nothing(
    measure, tmp_path
):
    """The pin is the CLI's to parse and the loop's to record: `off`/`on` reach `run_cells`,
    an absent flag reaches it as `None` -- which is the pin not taken, not `off` -- and a third
    value is refused by the parser before a run directory exists."""
    assert run(tmp_path, "--cache-state", "off") == 0
    assert measure.calls[0]["cache_state"] == "off"

    assert run(tmp_path, "--cache-state", "on") == 0
    assert measure.calls[1]["cache_state"] == "on"

    assert run(tmp_path) == 0
    assert measure.calls[2]["cache_state"] is None

    with pytest.raises(SystemExit):
        run(tmp_path, "--cache-state", "lukewarm")
    assert len(measure.calls) == 3


def test_a_run_pinning_the_kv_quant_passes_it_to_the_loop_and_defaults_to_nothing(
    measure, tmp_path
):
    """The codec pin is the CLI's to parse and the loop's to record: the three values reach
    `run_cells`, an absent flag reaches it as `None` -- the pin not taken, not `off` -- and a
    value that is not one of the three is refused by the parser before a run directory exists.
    `fp8` is the one that matters: it reads as a float8 codec and there is none in this set."""
    assert run(tmp_path, "--kv-quant", "off") == 0
    assert measure.calls[0]["kv_quant"] == "off"

    assert run(tmp_path, "--kv-quant", "affine8") == 0
    assert measure.calls[1]["kv_quant"] == "affine8"

    assert run(tmp_path, "--kv-quant", "affine4") == 0
    assert measure.calls[2]["kv_quant"] == "affine4"

    assert run(tmp_path) == 0
    assert measure.calls[3]["kv_quant"] is None

    for value in ("fp8", "int4", "affine16"):
        with pytest.raises(SystemExit):
            run(tmp_path, "--kv-quant", value)

    assert len(measure.calls) == 4
    # The two cache pins are separate fields and neither implies the other.
    assert all(call["cache_state"] is None for call in measure.calls)


def test_a_run_pinning_the_mtp_depth_passes_it_to_the_loop_and_defaults_to_nothing(
    measure, tmp_path
):
    """The depth pin is the CLI's to parse and the loop's to record: the four values reach
    `run_cells` as strings, an absent flag reaches it as `None` -- the pin not taken, not `off`
    -- and anything else is refused by the parser before a run directory exists. `4` is above
    the ceiling vMLX's own flag accepts, and `auto` is the adaptive policy this pin exists to
    take away from the runtime."""
    assert run(tmp_path, "--mtp-depth", "off") == 0
    assert measure.calls[0]["mtp_depth"] == "off"

    for index, depth in enumerate(("1", "2", "3"), start=1):
        assert run(tmp_path, "--mtp-depth", depth) == 0
        assert measure.calls[index]["mtp_depth"] == depth

    assert run(tmp_path) == 0
    assert measure.calls[4]["mtp_depth"] is None

    for value in ("0", "4", "auto", "adaptive"):
        with pytest.raises(SystemExit):
            run(tmp_path, "--mtp-depth", value)

    assert len(measure.calls) == 5
    # Four pins, four independent fields: taking one leaves the other three absent.
    assert all(call["stream_experts"] is None for call in measure.calls)
    assert all(call["cache_state"] is None for call in measure.calls)
    assert all(call["kv_quant"] is None for call in measure.calls)


def test_a_run_pinning_the_streaming_state_passes_it_to_the_loop_and_defaults_to_nothing(
    measure, tmp_path
):
    """`off`/`on` reach `run_cells`, an absent flag reaches it as `None` -- which is not `off`,
    because OptiQ's own default is `auto` -- and `auto` itself is refused by the parser: it is
    the decision this pin exists to take away from the runtime."""
    assert run(tmp_path, "--stream-experts", "off") == 0
    assert measure.calls[0]["stream_experts"] == "off"

    assert run(tmp_path, "--stream-experts", "on") == 0
    assert measure.calls[1]["stream_experts"] == "on"

    assert run(tmp_path) == 0
    assert measure.calls[2]["stream_experts"] is None

    for value in ("auto", "true", "disabled"):
        with pytest.raises(SystemExit):
            run(tmp_path, "--stream-experts", value)

    assert len(measure.calls) == 3
    assert all(call["mtp_depth"] is None for call in measure.calls)


def test_a_run_pinning_a_prompt_length_measures_one_prefill_workload_at_64_tokens(
    measure, tmp_path, capsys
):
    code = run(tmp_path, "--prompt-tokens", "500")

    assert code == 0
    assert len(measure.calls) == 1
    call = measure.calls[0]
    assert [workload.id for workload in call["workloads"]] == ["prefill"]
    assert [workload.max_tokens for workload in call["workloads"]] == [64]

    text, achieved = cli.sized_prompt(WordCounter(), 500)
    assert [message["content"] for message in call["workloads"][0].messages] == [text]
    assert call["prompt_tokens"] == {"target": 500, "achieved": achieved}
    assert call["prompt_tokens"]["achieved"] <= 500
    assert "leaderboard.md" in capsys.readouterr().out


def test_a_run_without_the_flag_measures_the_three_pinned_workloads_unchanged(
    measure, tmp_path, capsys
):
    code = run(tmp_path)

    assert code == 0
    call = measure.calls[0]

    assert [(w.id, w.max_tokens) for w in call["workloads"]] == [
        ("chat", 128),
        ("prefill", 64),
        ("decode", 512),
    ]
    assert [w.messages[0]["content"] for w in call["workloads"]] == [
        cli.PROMPT,
        cli.PREFILL_PROMPT,
        cli.PROMPT,
    ]
    assert call["prompt_tokens"] is None


# --- the workload set -------------------------------------------------------------------------


def test_turn_n_is_the_first_n_questions_and_the_replies_between_them(measure):
    """The conversation is the pinned one, turn by turn: turn N's messages are the first N
    questions of the dialogue and the N-1 fixed replies between them, ending on question N.

    The replies are literals on purpose. The probe this replaces fed each runtime's own reply
    back into the next turn, so every runtime saw a different history and a difference between
    two turns could belong to the history rather than to the runtime; a literal reply is what
    makes turn N the same prompt everywhere, and the word budget keeps them short enough to sit
    between two questions without dwarfing them.
    """
    users = [content for role, content in cli.DIALOGUE if role == "user"]
    replies = [content for role, content in cli.DIALOGUE if role == "assistant"]

    assert len(users) == 10 and len(replies) == 9
    assert all(60 <= len(reply.split()) <= 120 for reply in replies)

    shapes = cli.multiturn_workloads(measure)
    assert len(shapes) == 10

    for turn, workload in enumerate(shapes, start=1):
        expected = []
        for index in range(turn - 1):
            expected += [
                {"role": "user", "content": users[index]},
                {"role": "assistant", "content": replies[index]},
            ]
        expected.append({"role": "user", "content": users[turn - 1]})

        assert workload.messages == expected
        assert workload.messages[-1]["role"] == "user", "a turn ends on the question it asks"


def test_the_multiturn_set_is_ten_growing_turns_under_one_cap(measure, tmp_path):
    code = run(tmp_path, "--workloads", "multiturn")

    assert code == 0
    assert len(measure.calls) == 1
    shapes = measure.calls[0]["workloads"]

    assert [workload.id for workload in shapes] == [
        f"turn-{turn:02d}" for turn in range(1, 11)
    ]
    assert {workload.max_tokens for workload in shapes} == {128}
    assert all(workload.messages[-1]["role"] == "user" for workload in shapes)

    for previous, workload in zip(shapes, shapes[1:]):
        assert len(workload.messages) == len(previous.messages) + 2
        assert workload.messages[: len(previous.messages)] == previous.messages


def test_the_multiturn_set_is_a_selector_and_not_a_header_pin(measure, tmp_path):
    """The header already lists every workload a run measured with its messages and its cap, so
    the set needs no field of its own: the flag changes the workload list handed to the loop and
    nothing else, and `prompt_tokens` stays `None` -- the prompt-length pin not taken."""
    assert run(tmp_path) == 0
    assert run(tmp_path, "--workloads", "multiturn") == 0

    default, multiturn = measure.calls
    assert multiturn["prompt_tokens"] is None
    assert {key: value for key, value in multiturn.items() if key != "workloads"} == {
        key: value for key, value in default.items() if key != "workloads"
    }


def test_naming_the_default_set_changes_nothing(measure, tmp_path):
    assert run(tmp_path) == 0
    assert run(tmp_path, "--workloads", "pinned") == 0

    default, named = (call["workloads"] for call in measure.calls)

    assert [workload.id for workload in named] == ["chat", "prefill", "decode"]
    assert [(w.id, w.messages, w.max_tokens) for w in named] == [
        (w.id, w.messages, w.max_tokens) for w in default
    ]


def test_the_two_workload_selectors_cannot_both_choose_the_set(measure, tmp_path, capsys):
    """A run measures one set: argparse refuses the pair whichever order it is given, before a
    run directory exists and before any runtime is started."""
    for flags in (
        ("--workloads", "multiturn", "--prompt-tokens", "500"),
        ("--prompt-tokens", "500", "--workloads", "multiturn"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            run(tmp_path, *flags)
        assert exc_info.value.code == 2

        err = capsys.readouterr().err
        assert "not allowed with" in err
        assert "--workloads" in err and "--prompt-tokens" in err

    assert measure.calls == [], "the refused selection started a run"
    assert not (tmp_path / "results").exists()


def test_a_workload_set_that_is_not_one_of_the_two_is_refused(measure, tmp_path, capsys):
    """`pinned` and `multiturn` are the whole set: a third is refused as an invalid choice
    rather than taken as a name for shapes nobody pinned."""
    with pytest.raises(SystemExit) as exc_info:
        run(tmp_path, "--workloads", "turn-10")

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err and "turn-10" in err
    assert measure.calls == []


def test_the_run_help_lists_the_workload_selector(capsys, monkeypatch):
    # Python 3.14 argparse colours help when FORCE_COLOR is set; the assertion is on the text.
    monkeypatch.setenv("NO_COLOR", "1")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["run", "--help"])

    assert exc_info.value.code == 0
    assert "--workloads {pinned,multiturn}" in capsys.readouterr().out


def test_the_prompt_is_sized_once_per_distinct_artifact(monkeypatch, tmp_path):
    """Two cells over one artifact is one tokenizer and one prompt: the counter is the
    tokenizer that will serve the prompt, and there is one of those to build."""
    built = []

    def factory(model_dir):
        built.append(model_dir)
        return WordCounter(model_dir)

    monkeypatch.setattr(cli, "_load_measure", lambda: FakeMeasure())
    monkeypatch.setattr(cli, "token_counter", SimpleNamespace(TokenCounter=factory))

    code = run(tmp_path, "--prompt-tokens", "300")

    assert code == 0
    assert built == ["/models/oq4"]


def test_tokenizers_that_disagree_refuse_the_run_before_it_measures_anything(
    monkeypatch, tmp_path, capsys
):
    """One run pins one prompt length, so two artifacts whose tokenizers count the same bytes
    differently are a refused run rather than a sweep whose columns sent different prompts."""
    fake = FakeMeasure()
    monkeypatch.setattr(cli, "_load_measure", lambda: fake)
    monkeypatch.setattr(
        cli,
        "token_counter",
        SimpleNamespace(
            TokenCounter=lambda model_dir: (
                ThriceCounter(model_dir) if model_dir.endswith("other") else WordCounter(model_dir)
            )
        ),
    )

    code = cli.main(
        [
            "run",
            "--study",
            "format",
            "--cells",
            TWO_ARTIFACTS,
            "--prompt-tokens",
            "500",
            "--results-dir",
            str(tmp_path / "results"),
        ]
    )
    err = capsys.readouterr().err

    first, second = (
        cli.sized_prompt(counter(), 500)[1] for counter in (WordCounter, ThriceCounter)
    )
    assert first != second, "the fixture has to disagree about the same bytes"

    assert code == 2
    assert fake.calls == [], "the run started without one prompt length"
    assert not (tmp_path / "results").exists(), "the refused run left a run directory behind"
    assert "/models/oq4" in err and "/models/other" in err
    assert f"counts {first}" in err and f"counts {second}" in err


def test_a_target_the_pin_refuses_exits_two_without_starting_a_run(measure, tmp_path, capsys):
    code = run(tmp_path, "--prompt-tokens", "1")

    assert code == 2
    assert measure.calls == []
    assert not (tmp_path / "results").exists()
    assert "head and the tail" in capsys.readouterr().err


def test_cli_version_flag_prints_version_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0
    assert "ohyesmlx 0.3.0" in capsys.readouterr().out


def test_cli_short_version_flag_prints_version_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["-V"])
    assert exc_info.value.code == 0
    assert "ohyesmlx 0.3.0" in capsys.readouterr().out


def test_cli_help_flag_prints_usage_and_exits_zero(capsys, monkeypatch):
    # Python 3.14 argparse colours help when FORCE_COLOR is set; the assertion is on the text.
    monkeypatch.setenv("NO_COLOR", "1")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage: ohyesmlx" in out
    assert "run" in out
    assert "grid" in out
    assert "sweep" in out


def test_cli_subcommand_help_exits_zero(capsys, monkeypatch):
    # Python 3.14 argparse colours help when FORCE_COLOR is set; the assertion is on the text.
    monkeypatch.setenv("NO_COLOR", "1")
    for subcmd in ("run", "grid", "sweep"):
        with pytest.raises(SystemExit) as exc_info:
            cli.main([subcmd, "--help"])
        assert exc_info.value.code == 0
        assert f"usage: ohyesmlx {subcmd}" in capsys.readouterr().out



def test_cli_no_args_exits_two(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])
    assert exc_info.value.code == 2
    assert "error" in capsys.readouterr().err


def test_cli_unknown_subcommand_exits_two(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["unknown_command"])
    assert exc_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_package_version_matches():
    import ohyesmlx

    assert ohyesmlx.__version__ == "0.3.0"


def test_package_longtext_resource_exists_and_loads():
    assert cli.LONGTEXT.exists()
    assert cli.LONGTEXT.is_file()
    source = cli.sized_source()
    assert len(source) > 10000
    assert "1. Scope. This standard governs" in source
    assert len(cli.LONGTEXT.read_text(encoding="utf-8")) > 100000


