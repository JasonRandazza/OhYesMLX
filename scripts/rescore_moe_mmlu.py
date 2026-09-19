"""Offline re-scoring of the Osaurus MoE MMLU cell: recover the score that
lm-eval's `get_response` filter discarded.

Plan 02-03 ran `jang2l__osaurus` through lm-eval 0.4.13's `mmlu_generative` task
and recorded 3.77% (43 / 1,140). The task's `get_response` filter reduces every
completion to its **first line** before scoring, and this artifact states its
answer at the **end** of a prose response. 1,016 of the 1,140 items were judged
on a string that never contained the answer.

Two numbers are derived here from the same untouched sample rows, so the second
can be read against the first:

* **baseline** — `resp.strip() == target.strip()` applied to lm-eval's own
  `filtered_resps`, the truncated string it scored. This must reproduce
  43 / 1,140 exactly; the run refuses to publish anything if it does not.
* **recovered** — the stated answer extracted from the *full* completion
  (`resps[0][0]`) by a five-pattern cascade, each pattern read from the end of
  the text, in the priority order given.

An empty completion extracts nothing and scores zero. A completion that hits the
generation ceiling mid-sentence and never names a letter also scores zero, and
both are counted separately so the two are never confused.

Stdlib only. Nothing here starts a server, loads a model, or reads a tensor: it
is a re-reading of rows already on disk.

    python scripts/rescore_moe_mmlu.py --self-test
    python scripts/rescore_moe_mmlu.py
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELL_DIR = ROOT / "results" / "accuracy-moe" / "study-2c" / "jang2l__osaurus"
MMLU_DIR = CELL_DIR / "mmlu_generative" / "lfm2.5-8b-a1b-jang_2l"
SUMMARY_PATH = CELL_DIR / "mmlu_rescored.json"

EXPECTED_FILES = 57
EXPECTED_ITEMS = 1140
LM_EVAL_REPORTED_MATCHES = 43
LM_EVAL_REPORTED_SCORE = 0.0377
Z_95 = 1.959963984540054

BASELINE_METHOD = (
    "strict equality, resp.strip() == target.strip(), on lm-eval's filtered_resps "
    "(the completion reduced to its first line by the get_response filter)"
)
RECOVERED_METHOD = (
    "five-pattern cascade over the full completion (resps[0][0]); first pattern "
    "with a match wins, and within a pattern the last (rightmost) match is taken"
)

ANSWER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("stated_answer", re.compile(r"(?:Answer|answer):\s*(?:\*\*)?([A-D])(?:\*\*)?(?:\.|\b)")),
    ("lettered_option", re.compile(r"\b([A-D])\.\s+[A-Za-z]")),
    ("bold_letter", re.compile(r"\*\*([A-D])\*\*")),
    ("correct_answer_is", re.compile(r"(?i:the correct answer is\s+(?:\*\*)?([A-D]))")),
    ("isolated_letter", re.compile(r"(?<![A-Za-z])[A-D](?![A-Za-z])")),
)


def extract_answer(completion: str) -> tuple[str | None, str | None]:
    """The answer letter a completion states, and the pattern that found it.

    Patterns are tried in priority order. Within a pattern the last match wins,
    because the artifact restates its choice at the end of an explanation and an
    earlier mention is usually the option list or a rejected candidate. Returns
    `(None, None)` for an empty or letterless completion.
    """
    if not completion or not completion.strip():
        return None, None
    for label, pattern in ANSWER_PATTERNS:
        matches = list(pattern.finditer(completion))
        if matches:
            match = matches[-1]
            return (match.group(1) if match.groups() else match.group(0)), label
    return None, None


def wilson_interval(matches: int, items: int) -> tuple[float, float]:
    """Two-sided 95% Wilson score interval for a binomial proportion."""
    if items <= 0:
        return 0.0, 0.0
    p = matches / items
    z2 = Z_95 * Z_95
    denom = 1.0 + z2 / items
    center = (p + z2 / (2 * items)) / denom
    spread = (Z_95 / denom) * ((p * (1 - p) / items + z2 / (4 * items * items)) ** 0.5)
    return max(0.0, center - spread), min(1.0, center + spread)


def load_items() -> tuple[list[str], list[dict]]:
    """Every sample row under the cell's MMLU task, tagged with its subject."""
    paths = sorted(glob.glob(str(MMLU_DIR / "samples_*.jsonl")))
    items: list[dict] = []
    for path in paths:
        name = Path(path).name
        subject = name.split("samples_mmlu_", 1)[1].split("_generative", 1)[0]
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            completion = row["resps"][0][0]
            letter, rule = extract_answer(completion)
            items.append(
                {
                    "subject": subject,
                    "target": row["target"].strip(),
                    "completion": completion,
                    "baseline_match": row["filtered_resps"][0].strip() == row["target"].strip(),
                    "extracted": letter,
                    "rule": rule,
                }
            )
    return paths, items


def build_summary(paths: list[str], items: list[dict]) -> dict:
    total = len(items)
    baseline_matches = sum(1 for it in items if it["baseline_match"])
    recovered_matches = sum(1 for it in items if it["extracted"] == it["target"])
    empty = sum(1 for it in items if not it["completion"].strip())
    unextractable = sum(1 for it in items if it["extracted"] is None)

    rule_usage: dict[str, int] = {}
    rule_matches: dict[str, int] = {}
    for label, _ in ANSWER_PATTERNS:
        used = [it for it in items if it["rule"] == label]
        rule_usage[label] = len(used)
        rule_matches[label] = sum(1 for it in used if it["extracted"] == it["target"])

    subjects = []
    for subject in sorted({it["subject"] for it in items}):
        rows = [it for it in items if it["subject"] == subject]
        s_base = sum(1 for it in rows if it["baseline_match"])
        s_rec = sum(1 for it in rows if it["extracted"] == it["target"])
        subjects.append(
            {
                "subject": subject,
                "items": len(rows),
                "baseline_matches": s_base,
                "baseline_accuracy": s_base / len(rows),
                "recovered_matches": s_rec,
                "recovered_accuracy": s_rec / len(rows),
            }
        )

    recovered_low, recovered_high = wilson_interval(recovered_matches, total)
    baseline_low, baseline_high = wilson_interval(baseline_matches, total)

    baseline_score = baseline_matches / total
    return {
        "cell": "jang2l__osaurus",
        "runtime": "osaurus",
        "model_id": "lfm2.5-8b-a1b-jang_2l",
        "task": "mmlu_generative",
        "metric": "exact_match",
        "source_glob": str((MMLU_DIR / "samples_*.jsonl").relative_to(ROOT)),
        "sample_files": len(paths),
        "items": total,
        "baseline": {
            "method": BASELINE_METHOD,
            "matches": baseline_matches,
            "accuracy": baseline_score,
            "accuracy_95_wilson": {"low": baseline_low, "high": baseline_high},
            "lm_eval_reported_matches": LM_EVAL_REPORTED_MATCHES,
            "lm_eval_reported_score": LM_EVAL_REPORTED_SCORE,
            "reconciled": baseline_matches == LM_EVAL_REPORTED_MATCHES,
        },
        "recovered": {
            "method": RECOVERED_METHOD,
            "patterns": [{"priority": i, "rule": label, "regex": pattern.pattern}
                         for i, (label, pattern) in enumerate(ANSWER_PATTERNS, 1)],
            "matches": recovered_matches,
            "accuracy": recovered_matches / total,
            "accuracy_95_wilson": {"low": recovered_low, "high": recovered_high},
            "rule_usage": rule_usage,
            "rule_matches": rule_matches,
            "recovered_over_baseline_matches": recovered_matches - baseline_matches,
            "baseline_hits_lost": baseline_matches - sum(
                1 for it in items if it["baseline_match"] and it["extracted"] == it["target"]
            ),
        },
        "unscored": {
            "empty_completion": empty,
            "no_letter_found": unextractable - empty,
            "total": unextractable,
            "note": "both classes score 0.0: an empty completion states no answer, "
                    "and a completion truncated at max_gen_toks without naming a letter "
                    "makes no claim to be right or wrong",
        },
        "distribution": {
            "extracted": {
                letter: sum(1 for it in items if it["extracted"] == letter)
                for letter in ("A", "B", "C", "D")
            }
            | {"none": unextractable},
            "targets": {
                letter: sum(1 for it in items if it["target"] == letter)
                for letter in ("A", "B", "C", "D")
            },
        },
        "subjects": subjects,
        "attribution": (
            "Offline re-reading of completed, verified model outputs already on disk under "
            "results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_generative/. No runtime was "
            "started, no model was loaded, no benchmark item was re-run, and no sample row was "
            "modified or discarded: the record keeps what the model actually emitted, including "
            "the empty and truncated completions this script scores zero."
        ),
    }


def report(summary: dict) -> None:
    base = summary["baseline"]
    rec = summary["recovered"]
    low, high = rec["accuracy_95_wilson"]["low"], rec["accuracy_95_wilson"]["high"]

    print(f"cell          : {summary['cell']} ({summary['runtime']})")
    print(f"model         : {summary['model_id']}")
    print(f"source        : {summary['source_glob']}")
    print(f"sample files  : {summary['sample_files']}")
    print(f"items         : {summary['items']}")
    print()
    print(f"baseline      : {base['matches']}/{summary['items']} = "
          f"{base['accuracy'] * 100:.2f}%  "
          f"(lm-eval reported {base['lm_eval_reported_matches']}/"
          f"{summary['items']} = {base['lm_eval_reported_score'] * 100:.2f}%)")
    print(f"recovered     : {rec['matches']}/{summary['items']} = "
          f"{rec['accuracy'] * 100:.2f}%  95% Wilson [{low * 100:.2f}%, {high * 100:.2f}%]")
    print(f"delta         : {rec['recovered_over_baseline_matches']:+d} items, "
          f"baseline hits lost: {rec['baseline_hits_lost']}")
    print()
    print("pattern usage (priority order, last match wins within a pattern):")
    for entry in rec["patterns"]:
        label = entry["rule"]
        used = rec["rule_usage"][label]
        hit = rec["rule_matches"][label]
        acc = f"{hit / used * 100:5.1f}%" if used else "    -"
        print(f"  {entry['priority']}. {label:18s} used {used:5d}  correct {hit:4d}  {acc}")
    print()
    unscored = summary["unscored"]
    print(f"unscored      : {unscored['total']} "
          f"({unscored['empty_completion']} empty, {unscored['no_letter_found']} no letter found)")
    print()
    print("subject                     n   base  recov")
    for row in summary["subjects"]:
        print(f"  {row['subject']:34s} {row['items']:3d}  "
              f"{row['baseline_matches']:4d}  {row['recovered_matches']:4d}")
    print()
    dist = summary["distribution"]
    print("extracted  : " + "  ".join(f"{k}={v}" for k, v in dist["extracted"].items()))
    print("targets    : " + "  ".join(f"{k}={v}" for k, v in dist["targets"].items()))


def run() -> int:
    paths, items = load_items()
    if len(paths) != EXPECTED_FILES or len(items) != EXPECTED_ITEMS:
        print(f"REFUSING TO PUBLISH: expected {EXPECTED_FILES} sample files / "
              f"{EXPECTED_ITEMS} items, found {len(paths)} / {len(items)}.")
        return 1

    summary = build_summary(paths, items)
    report(summary)

    if not summary["baseline"]["reconciled"]:
        print()
        print(f"REFUSING TO PUBLISH: baseline reproduced "
              f"{summary['baseline']['matches']}/{summary['items']}, not lm-eval's "
              f"{LM_EVAL_REPORTED_MATCHES}/{EXPECTED_ITEMS}. The recovery is not "
              f"readable against a baseline that does not reconcile.")
        return 1

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"baseline reconciled with lm-eval's reported {LM_EVAL_REPORTED_SCORE * 100:.2f}%.")
    print(f"wrote {SUMMARY_PATH.relative_to(ROOT)}")
    return 0


SELF_TEST_CASES: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("stated_answer", "Answer: B", "B", "stated_answer"),
    ("stated_answer", "**Answer: B. Media tour**", "B", "stated_answer"),
    ("stated_answer", "answer: D.", "D", "stated_answer"),
    ("lettered_option", "B. Media tour", "B", "lettered_option"),
    ("bold_letter", "**D**", "D", "bold_letter"),
    ("correct_answer_is", "Therefore, the correct answer is C", "C", "correct_answer_is"),
    ("bold beats later pattern", "So the correct answer is **A**", "A", "bold_letter"),
    ("isolated_letter", "A", "A", "isolated_letter"),
    ("isolated_letter", "I would pick (C)", "C", "isolated_letter"),
    ("last match wins", "Answer: A looks right here,\n\nbut on reflection\n\nAnswer: C", "C",
     "stated_answer"),
    ("priority beats position", "**B** somewhere\n\nAnswer: D", "D", "stated_answer"),
    ("empty", "", None, None),
    ("whitespace only", "   \n\t ", None, None),
    ("letterless", "The polynomial has roots at x=0 and x=4.", None, None),
    ("truncated prose", "The standard GARCH(1,1) model", None, None),
    ("out-of-range letter is not an answer", "Therefore, the correct answer is E", None, None),
)


def self_test() -> int:
    failures = 0
    for name, completion, want_letter, want_rule in SELF_TEST_CASES:
        got_letter, got_rule = extract_answer(completion)
        if got_letter != want_letter or got_rule != want_rule:
            failures += 1
            print(f"FAIL  {name}: {completion!r} -> letter={got_letter!r} rule={got_rule!r}, "
                  f"want letter={want_letter!r} rule={want_rule!r}")
        else:
            print(f"ok    {name}: {completion!r} -> {got_letter!r} via {got_rule}")

    extracted = {extract_answer(completion)[0] for _, completion, _, _ in SELF_TEST_CASES}
    stray = sorted(letter for letter in extracted if letter is not None and letter not in "ABCD")
    checks = (
        ("every extraction is on the A-D answer key", stray, []),
        ("strict equality trims", (" A ".strip() == "A".strip()), True),
        ("wilson bounds a proportion", wilson_interval(43, 1140)[0] < 43 / 1140
         < wilson_interval(43, 1140)[1], True),
        ("wilson zero matches starts at 0", wilson_interval(0, 1140)[0], 0.0),
        ("wilson all matches ends at 1", wilson_interval(1140, 1140)[1], 1.0),
        ("wilson of no items is empty", wilson_interval(0, 0), (0.0, 0.0)),
    )
    for name, got, want in checks:
        if got != want:
            failures += 1
            print(f"FAIL  {name}: got {got!r}, want {want!r}")
        else:
            print(f"ok    {name}")

    print()
    if failures:
        print(f"SELF-TEST FAILED: {failures} failure(s)")
        return 1
    print(f"SELF-TEST PASSED: {len(SELF_TEST_CASES) + len(checks)} checks")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
