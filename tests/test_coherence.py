"""Checks for ohyesmlx.coherence.

The failing fixture is the real captured completion, byte for byte, from
``docs/research/2026-09-14-oq-portability-spike.md`` Round 2: ``Jundot/Qwen3.6-35B-A3B-oQ4-mtp``
under stock ``mlx_lm.server``, returned in ``choices[0].message.reasoning`` with
``finish_reason: "length"`` and 64/64 completion tokens. It loaded in 4 s, answered HTTP 200
and decoded at full speed. This module exists because nothing about it raised.

The passing fixture is a completion of the shape a healthy cell returns to the pinned prompt.
No healthy-runtime completion has been captured on disk in this repo yet, so this one is
written English rather than quoted English — the check it locks in is the same either way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ohyesmlx import coherence

SPIKE = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "research"
    / "2026-09-14-oq-portability-spike.md"
)
SPIKE_SALAD_LINE = 288  # 1-indexed, the captured completion in "Round 2"

# Verbatim, replacement character included. The doc's own copy of this line is the source.
CAPTURED_SALAD = (
    "，,跟ashaa.atore quell\ufffd不会ulatSR2ancel Hard1* \"uhl an:...,1. 40面-VP : tep  "
    "1etasconfIAS11. ass question questionys- 0 memory 1 exleCT us  以能 ze"
)


def test_the_fixture_is_the_captured_string_and_not_a_paraphrase():
    """A salad fixture that drifted from the capture would pass for the wrong reasons."""
    captured = SPIKE.read_text(encoding="utf-8").splitlines()[SPIKE_SALAD_LINE - 1]

    assert CAPTURED_SALAD == captured
    assert coherence.REPLACEMENT_CHARACTER in CAPTURED_SALAD


HEALTHY_COMPLETION = (
    "A benchmark that changes two things at once cannot say which one caused the difference, "
    "because the faster row is the only row you have. Suppose you swap the quantization "
    "format and the serving runtime in the same step, and the new cell reports 41.2 tokens "
    "per second against 28.7 before. The format may be better, the runtime may be better, and "
    "the result cannot distinguish them. Change one, hold the other constant, and the number "
    "means something."
)


def test_the_captured_salad_fails():
    passed, reason = coherence.is_coherent(CAPTURED_SALAD)

    assert passed is False
    assert reason == "replacement characters"


def test_the_salad_fails_on_its_mixed_scripts_when_nothing_was_replaced():
    """The same failure with the replacement character removed still has to fail."""
    salad = (
        "the of 中文对拉丁文字混排 и немного кириллицы 也混杂其中 слов и знаков ещё"
    )

    passed, reason = coherence.is_coherent(salad)

    assert passed is False
    assert reason.startswith("no majority script")


def test_a_response_of_pure_debris_fails_the_word_check():
    passed, reason = coherence.is_coherent("1. - / ,,, 22 3.4 ??? ### ... ;;;")

    assert passed is False
    assert reason == "implausible words"


def test_a_real_coherent_completion_passes():
    assert coherence.is_coherent(HEALTHY_COMPLETION) == (True, "ok")


def test_the_checkable_answer_has_to_appear():
    assert coherence.is_coherent("The answer is 4.", expect="4") == (True, "ok")
    assert coherence.is_coherent("Two plus two is four.", expect="4") == (
        False,
        "expected '4' is absent",
    )


def test_the_answer_is_matched_case_insensitively():
    assert coherence.is_coherent("The capital is Paris.", expect="paris") == (True, "ok")


def test_the_first_failing_check_is_the_one_reported():
    """One reason, not a list: the caller reports the first thing that went wrong."""
    passed, reason = coherence.is_coherent(CAPTURED_SALAD, expect="4")

    assert passed is False
    assert reason == "replacement characters"


def test_still_thinking_is_not_reported_as_incoherent():
    """A thinking model that spent the whole budget has produced no output, not bad output.

    The captured failure arrived with ``message.content`` absent; the caller reads that as
    NO_CONTENT and gives the cell its own status. Nothing here may say the output was
    incoherent, because there is no output to judge.
    """
    passed, reason = coherence.is_coherent("")
    assert (passed, reason) == (False, coherence.NO_CONTENT)

    for ordinary_incoherence in ("replacement characters", "implausible words"):
        assert coherence.NO_CONTENT != ordinary_incoherence
    assert coherence.is_coherent("   \n\t ")[1] == coherence.NO_CONTENT


@pytest.mark.parametrize(
    "text",
    [
        "Это связный русский текст, который проверяет, что смешивание скриптов не путается с бессмыслицей.",
        "这是一段连贯的中文文本，用于验证脚本检查不会误报。",
        "これは一貫した日本語の文章で、誤って不整合とは判定されません。",
        "이것은 일관된 한국어 문장이며, 스크립트 검사에서 잘못 판정되지 않아야 합니다.",
        "هذا نص عربي متماسك، ويجب ألا يعتبر غير مفهوم.",
        "答案是 Apple。",
    ],
)
def test_legitimate_non_english_output_passes(text):
    assert coherence.is_coherent(text) == (True, "ok")


def test_a_numbered_list_is_not_a_word_salad():
    assert coherence.is_coherent("1. first\n2. second") == (True, "ok")
