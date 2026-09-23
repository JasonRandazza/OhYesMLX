"""Checks for ohyesmlx.token_counter's accounting rules.

The counter exists to SPLIT a combined stream into reasoning and content. With no
reasoning channel there is no split, so there is nothing for a re-count to validate: the
runtime's own ``completion_tokens`` is the content count, and the counter must not be
asked at all.

Measured on this machine: oMLX 0.6.4 served five coherent requests, every one with an
empty reasoning channel after dedupe, and every one published nothing. The local re-count
of the decoded text was 257 against a ``usage.completion_tokens`` of 256 — the response
was truncated at ``max_tokens``, so it re-tokenized across different boundaries. Exact
equality is unsatisfiable there; it is not a tolerance that was missing.

Where a split IS derived — a genuinely non-empty reasoning channel against one reported
total — reconciliation stays exact and a disagreement still publishes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping

from ohyesmlx.token_counter import resolve_token_accounting


class FixedMapTokenCounter:
    """Test/helper counter: exact string → count; unknown strings → 0."""

    def __init__(self, counts: Mapping[str, int]) -> None:
        self._counts = dict(counts)

    def count(self, text: str) -> int:
        return int(self._counts.get(text, 0))


class ExplodingCounter:
    """Raises if the accounting consults it. A counter with nothing to split must be idle."""

    def count(self, text: str) -> int:
        raise AssertionError(f"token counter was consulted for {text!r}")


def test_empty_reasoning_publishes_the_runtimes_own_completion_count():
    assert resolve_token_accounting(
        reasoning_text="",
        visible_text="The capital of France is Paris.",
        completion_tokens=8,
        token_counter=ExplodingCounter(),
    ) == (0, 8, "EXACT_VISIBLE")


def test_an_empty_reasoning_channel_never_consults_the_counter():
    """The counter has nothing to split, so it is not asked — not even for the content."""
    for reasoning_text in ("", " ", "\n", " \t\n "):
        assert resolve_token_accounting(
            reasoning_text=reasoning_text,
            visible_text="anything at all",
            completion_tokens=42,
            token_counter=ExplodingCounter(),
        ) == (0, 42, "EXACT_VISIBLE")


def test_whitespace_only_reasoning_is_empty_reasoning():
    assert resolve_token_accounting(
        reasoning_text="\n\n\t ",
        visible_text="ok",
        completion_tokens=3,
        token_counter=FixedMapTokenCounter({"ok": 3}),
    ) == (0, 3, "EXACT_VISIBLE")


def test_a_truncated_response_publishes_usage_rather_than_the_local_recount():
    """The measured oMLX case: 257 locally, 256 from usage. 256 is the count."""
    text = "\nThinking Process:\n\n1.  **" * 20
    assert resolve_token_accounting(
        reasoning_text="",
        visible_text=text,
        completion_tokens=256,
        token_counter=FixedMapTokenCounter({text: 257}),
    ) == (0, 256, "EXACT_VISIBLE")


def test_an_empty_reasoning_channel_publishes_without_a_counter_at_all():
    """No split to derive means no counter is needed — a caller that wired none still counts."""
    assert resolve_token_accounting(
        reasoning_text="",
        visible_text="ok",
        completion_tokens=2,
        token_counter=None,
    ) == (0, 2, "EXACT_VISIBLE")


def test_a_non_empty_reasoning_channel_still_reconciles_exactly():
    assert resolve_token_accounting(
        reasoning_text="think hard",
        visible_text="ok",
        completion_tokens=5,
        token_counter=FixedMapTokenCounter({"think hard": 3, "ok": 2}),
    ) == (3, 2, "DERIVED_REASONING_CONTENT")


def test_a_non_empty_reasoning_channel_that_does_not_reconcile_still_refuses():
    assert resolve_token_accounting(
        reasoning_text="think hard",
        visible_text="ok",
        completion_tokens=9,
        token_counter=FixedMapTokenCounter({"think hard": 3, "ok": 2}),
    ) == (None, None, "INCOMPARABLE_TOKEN_ACCOUNTING")


def test_a_derived_split_off_by_one_still_refuses():
    """Removing a check that had nothing to validate is not a tolerance on the ones that do."""
    assert resolve_token_accounting(
        reasoning_text="think hard",
        visible_text="ok",
        completion_tokens=6,
        token_counter=FixedMapTokenCounter({"think hard": 3, "ok": 2}),
    ) == (None, None, "INCOMPARABLE_TOKEN_ACCOUNTING")


def test_completion_tokens_none_with_empty_reasoning_is_unchanged():
    assert resolve_token_accounting(
        reasoning_text="",
        visible_text="ok",
        completion_tokens=None,
        token_counter=FixedMapTokenCounter({"ok": 2}),
    ) == (None, None, "INCOMPARABLE_TOKEN_ACCOUNTING")

    assert resolve_token_accounting(
        reasoning_text="",
        visible_text="ok",
        completion_tokens=None,
        token_counter=None,
    ) == (None, None, "INCOMPARABLE_TOKEN_ACCOUNTING")
