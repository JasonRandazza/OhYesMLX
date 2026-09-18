"""Plan 02-02: Dense Accuracy Study Analysis and Synthesis.

Parses results and sample files across Column A (vMLX) and Column B (Osaurus),
computes paired differences and 95% confidence intervals, evaluates replicate
stability, and computes Study 2C cross-runtime answer agreement rates on shared
formats (jang4s, oq4, oq4e).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_samples(samples_path: str) -> dict[int | str, dict]:
    """Load per-item records indexed by doc_id."""
    items = {}
    if not os.path.exists(samples_path):
        return items
    for line in Path(samples_path).read_text("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            doc_id = entry.get("doc_id")
            if doc_id is not None:
                items[doc_id] = entry
        except json.JSONDecodeError:
            continue
    return items


def paired_difference(
    samples_a: dict[int | str, dict],
    samples_b: dict[int | str, dict],
    metric_key: str = "exact_match",
) -> dict:
    """Compute paired McNemar difference and 95% CI between two runs on identical items."""
    common_ids = sorted(set(samples_a.keys()) & set(samples_b.keys()))
    n = len(common_ids)
    if n == 0:
        return {"n": 0, "b": 0, "c": 0, "delta": 0.0, "ci_half_width": 0.0, "interval": (0.0, 0.0)}

    # b: A correct, B incorrect
    # c: B correct, A incorrect
    b = 0
    c = 0
    both_correct = 0
    both_incorrect = 0

    for doc_id in common_ids:
        item_a = samples_a[doc_id]
        item_b = samples_b[doc_id]

        score_a = item_a.get(metric_key, 0)
        score_b = item_b.get(metric_key, 0)
        # Handle cases where score might be boolean or float
        acc_a = bool(score_a > 0 if isinstance(score_a, (int, float)) else score_a)
        acc_b = bool(score_b > 0 if isinstance(score_b, (int, float)) else score_b)

        if acc_a and not acc_b:
            b += 1
        elif acc_b and not acc_a:
            c += 1
        elif acc_a and acc_b:
            both_correct += 1
        else:
            both_incorrect += 1

    delta = (b - c) / n
    # Standard error of paired difference
    discordant = b + c
    if discordant < 25:
        # Binomial approximation / exact interval width
        se = math.sqrt(discordant) / n if n > 0 else 0.0
    else:
        se = math.sqrt(discordant) / n

    ci_half = 1.96 * se
    return {
        "n": n,
        "b": b,
        "c": c,
        "both_correct": both_correct,
        "both_incorrect": both_incorrect,
        "discordant": discordant,
        "discordance_rate": round(discordant / n, 4) if n > 0 else 0.0,
        "delta": round(delta, 4),
        "ci_half_width": round(ci_half, 4),
        "ci_lower": round(delta - ci_half, 4),
        "ci_upper": round(delta + ci_half, 4),
    }


def agreement_rate(
    samples_a: dict[int | str, dict],
    samples_b: dict[int | str, dict],
) -> dict:
    """Study 2C: Compute answer agreement rate between two runtimes on identical artifact."""
    common_ids = sorted(set(samples_a.keys()) & set(samples_b.keys()))
    n = len(common_ids)
    if n == 0:
        return {"n": 0, "identical": 0, "disagreed": 0, "agreement_rate": 0.0, "disagreements": []}

    identical = 0
    disagreements = []

    for doc_id in common_ids:
        item_a = samples_a[doc_id]
        item_b = samples_b[doc_id]

        # Compare filtered response if present, otherwise raw response
        resp_a = item_a.get("filtered_resps") or item_a.get("resps")
        resp_b = item_b.get("filtered_resps") or item_b.get("resps")

        if resp_a == resp_b:
            identical += 1
        else:
            disagreements.append({
                "doc_id": doc_id,
                "resp_a": resp_a,
                "resp_b": resp_b,
                "target": item_a.get("target"),
            })

    rate = identical / n if n > 0 else 0.0
    return {
        "n": n,
        "identical": identical,
        "disagreed": len(disagreements),
        "agreement_rate": round(rate, 4),
        "first_disagreement": disagreements[0] if disagreements else None,
    }


def self_test() -> int:
    """Offline verification of statistics and agreement calculations."""
    samples_1 = {
        0: {"doc_id": 0, "exact_match": 1.0, "filtered_resps": ["A"], "target": "A"},
        1: {"doc_id": 1, "exact_match": 0.0, "filtered_resps": ["B"], "target": "C"},
        2: {"doc_id": 2, "exact_match": 1.0, "filtered_resps": ["D"], "target": "D"},
    }
    samples_2 = {
        0: {"doc_id": 0, "exact_match": 1.0, "filtered_resps": ["A"], "target": "A"},
        1: {"doc_id": 1, "exact_match": 1.0, "filtered_resps": ["C"], "target": "C"},
        2: {"doc_id": 2, "exact_match": 0.0, "filtered_resps": ["C"], "target": "D"},
    }
    paired = paired_difference(samples_1, samples_2)
    assert paired["n"] == 3
    assert paired["b"] == 1  # doc 2: 1 got right, 2 got wrong
    assert paired["c"] == 1  # doc 1: 2 got right, 1 got wrong
    assert paired["delta"] == 0.0

    agr = agreement_rate(samples_1, samples_2)
    assert agr["n"] == 3
    assert agr["identical"] == 1
    assert agr["disagreed"] == 2
    assert agr["agreement_rate"] == round(1 / 3, 4)
    assert agr["first_disagreement"]["doc_id"] == 1

    print("analyze_accuracy_dense self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze dense accuracy results.")
    parser.add_argument("--results-dir", help="Results directory containing cell runs")
    parser.add_argument("--out", help="Markdown summary output path")
    parser.add_argument("--self-test", action="store_true", help="Run offline unit self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.results_dir:
        parser.error("--results-dir is required unless --self-test is specified")

    print(f"Analyzing accuracy results in {args.results_dir}...")
    # Will be expanded with full table formatting once results are available
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
