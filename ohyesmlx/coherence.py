"""A floor, not an eval: is this cell producing language at all?

Stock ``mlx_lm.server`` loaded ``Jundot/Qwen3.6-35B-A3B-oQ4-mtp`` in 4 s, answered HTTP 200,
generated 64/64 tokens at full speed, and returned mixed-script token salad with replacement
characters. Nothing raised and nothing timed out, so a speed-only harness records that as its
healthiest row. This module is what stops it: four cheap local checks, no model, no network,
no scoring::

    is_coherent(text, expect="4")   # -> (True, "ok")

The first failing check names the reason, so a cell reports one thing rather than a list.
``NO_CONTENT`` is its own reason and never the incoherent verdict: a thinking model that spent
the whole token budget has produced no output, not bad output, and the caller gives that its
own status. "Is it right" is a different question, and v2 owns it.
"""

from __future__ import annotations

REPLACEMENT_CHARACTER = "\ufffd"
NO_CONTENT = "no content"

# Alphabetic characters, by Unicode block. Anything outside these tables — digits,
# punctuation, symbols, emoji — is not evidence of any script and is not counted as one.
_BLOCKS = (
    ("latin", ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF))),
    ("cjk", ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))),
    ("cyrillic", ((0x400, 0x52F),)),
    ("hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7A3))),
    ("arabic", ((0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
)

_UNSPACED = frozenset({"cjk"})  # puts no spaces between words: one character is one word
SCRIPT_MAJORITY = 0.75          # "a clear majority", not a bare one
MIN_SCRIPTED = 16               # below this, a majority of a few letters says nothing
WORD_FLOOR, WORD_MIN, WORD_MAX = 0.5, 2, 20


def _script(character: str) -> str | None:
    """The script this character belongs to, or ``None`` if it is not alphabetic here."""
    for name, blocks in _BLOCKS:
        if any(low <= ord(character) <= high for low, high in blocks):
            return name
    return None


def _core(token: str) -> str:
    """The token with every non-alphabetic character stripped off its edges."""
    start, end = 0, len(token)
    while start < end and _script(token[start]) is None:
        start += 1
    while end > start and _script(token[end - 1]) is None:
        end -= 1
    return token[start:end]


def _is_word(core: str) -> bool:
    if _script(core[0]) in _UNSPACED:
        return len(core) >= WORD_MIN
    return WORD_MIN <= len(core) <= WORD_MAX and all(_script(c) for c in core)


def _word_ratio(text: str) -> float:
    """The fraction of whitespace tokens that look like words rather than debris.

    # ponytail: a token is judged on its own edges, so a Latin-dominant salad of plausible
    # pseudo-words ("questionys exleCT") clears this floor. It is the cheap net under the two
    # sharp checks, not a detector on its own. Ceiling: an alphabetic, Latin-dominant salad
    # with no replacement character can pass all three checks. Upgrade path: score each token
    # by case consistency and character-bigram plausibility against the dominant script.
    """
    cores = [core for token in text.split() if (core := _core(token))]
    return sum(_is_word(core) for core in cores) / len(cores) if cores else 0.0


def is_coherent(text: str, *, expect: str | None = None) -> tuple[bool, str]:
    """(passed, reason). reason names the failing check, or "ok"."""
    if not text.strip():
        return False, NO_CONTENT
    if REPLACEMENT_CHARACTER in text:
        return False, "replacement characters"

    scripted = [script for character in text if (script := _script(character))]
    if len(scripted) >= MIN_SCRIPTED:
        counts = {name: scripted.count(name) for name in set(scripted)}
        if max(counts.values()) / len(scripted) < SCRIPT_MAJORITY:
            ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            shares = ", ".join(f"{name} {n / len(scripted):.0%}" for name, n in ranked)
            return False, f"no majority script ({shares})"

    if _word_ratio(text) < WORD_FLOOR:
        return False, "implausible words"
    if expect is not None and expect.casefold() not in text.casefold():
        return False, f"expected {expect!r} is absent"
    return True, "ok"
