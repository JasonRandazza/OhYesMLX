"""Local token counting for a pinned model directory.

The runtime's ``usage`` block is the preferred source for token counts, but only when it
separates reasoning tokens from content tokens. When it does not, :class:`TokenCounter`
supplies the content count — and :func:`resolve_token_accounting` refuses to report a
count unless it reconciles with the runtime's own completion total. Two sources are never
mixed inside one comparison.

The counter exists to *split* one combined stream into reasoning and content. With no
reasoning channel there is no split to derive and nothing to validate: the runtime's
``completion_tokens`` is the content count by definition, exactly as it is when the
runtime reports the split itself. Re-tokenizing the decoded text is not the inverse of
generation, so demanding that a re-count reproduce ``completion_tokens`` exactly is
unsatisfiable for any response truncated at ``max_tokens`` — it re-tokenizes across
different boundaries and lands a token or two away, which is how five coherent oMLX 0.6.4
responses published no tok/s at all.
"""

from __future__ import annotations

from pathlib import Path


class TokenCounter:
    """Best-effort tokenizer counter for a pinned model directory.

    Prefers HuggingFace ``tokenizers`` reading ``tokenizer.json``, then
    ``transformers.AutoTokenizer``.
    """

    def __init__(self, model_dir: str | Path) -> None:
        self._model_dir = str(model_dir)
        self._backend: str | None = None
        self._tokenizer: object | None = None

    def _load(self) -> tuple[str, object]:
        if self._tokenizer is not None and self._backend is not None:
            return self._backend, self._tokenizer

        tokenizer_json = Path(self._model_dir) / "tokenizer.json"
        if tokenizer_json.is_file():
            try:
                from tokenizers import (
                    Tokenizer,  # type: ignore[import-not-found]
                )
            except ImportError:
                Tokenizer = None  # type: ignore[assignment,misc]
            if Tokenizer is not None:
                self._backend = "tokenizers"
                self._tokenizer = Tokenizer.from_file(str(tokenizer_json))
                return self._backend, self._tokenizer

        try:
            from transformers import (
                AutoTokenizer,  # type: ignore[import-not-found]
            )
        except ImportError as error:
            raise RuntimeError(
                "neither tokenizers nor transformers is available"
            ) from error
        self._backend = "transformers"
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_dir,
            trust_remote_code=True,
        )
        return self._backend, self._tokenizer

    def count(self, text: str) -> int:
        if not text:
            return 0
        backend, tokenizer = self._load()
        if backend == "tokenizers":
            encoded = tokenizer.encode(text)  # type: ignore[attr-defined]
            return len(encoded.ids)
        encoded = tokenizer.encode(text, add_special_tokens=False)  # type: ignore[attr-defined]
        return len(encoded)


def resolve_token_accounting(
    *,
    reasoning_text: str,
    visible_text: str,
    completion_tokens: int | None,
    token_counter: TokenCounter | None,
) -> tuple[int | None, int | None, str]:
    """Return (reasoning_tokens, visible_output_tokens,
    token_accounting_status).

    One way to be exact, and one way to derive a split:

    * The runtime reports no reasoning channel at all, so there is no split to derive and
      its ``completion_tokens`` is the content count — the counter is not consulted.
    * The stream mixes both and the runtime reports one total, so the counter splits it
      and the two parts must sum to that total exactly.
    """
    if not reasoning_text.strip() and completion_tokens is not None:
        return 0, completion_tokens, "EXACT_VISIBLE"

    if token_counter is None:
        return None, None, "INCOMPARABLE_TOKEN_ACCOUNTING"

    reasoning = token_counter.count(reasoning_text)
    visible = token_counter.count(visible_text)
    if reasoning < 0 or visible < 0:
        return None, None, "INCOMPARABLE_TOKEN_ACCOUNTING"

    if completion_tokens is not None:
        if reasoning + visible != completion_tokens:
            return None, None, "INCOMPARABLE_TOKEN_ACCOUNTING"
        if visible <= 0:
            return None, None, "INCOMPARABLE_TOKEN_ACCOUNTING"
        return reasoning, visible, "DERIVED_REASONING_CONTENT"

    if reasoning > 0 and visible > 0:
        return reasoning, visible, "DERIVED_REASONING_CONTENT"
    return None, None, "INCOMPARABLE_TOKEN_ACCOUNTING"
