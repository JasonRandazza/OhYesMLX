"""Plan 02-02: Comprehensive Dense Accuracy Analysis Script.

Parses all results and sample files across Column A (vMLX) and Column B (Osaurus),
computes paired McNemar difference intervals, Study 2C cross-runtime agreement
rates, replicate stability, and produces complete statistical summary tables.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_mmlu_samples(mmlu_dir: str) -> dict[str, dict]:
    """Load MMLU samples across all 57 subject jsonl files, keyed by (subject, doc_id)."""
    items = {}
    pattern = os.path.join(mmlu_dir, "**", "samples_*.jsonl")
    for f in glob.glob(pattern, recursive=True):
        basename = os.path.basename(f)
        # extract subject name from samples_mmlu_<subject>_generative_*.jsonl
        parts = basename.split("_")
        sub_name = "_".join(parts[1:-1])  # e.g. mmlu_abstract_algebra_generative
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                doc_id = entry.get("doc_id")
                key = f"{sub_name}:{doc_id}"
                items[key] = entry
    return items


def load_gsm8k_samples(gsm8k_dir: str) -> dict[int, dict]:
    """Load GSM8K samples, filtered by strict-match to yield unique 250 test items."""
    items = {}
    pattern = os.path.join(gsm8k_dir, "**", "samples_*.jsonl")
    for f in glob.glob(pattern, recursive=True):
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("filter") == "strict-match":
                    items[entry["doc_id"]] = entry
    return items


def load_ifeval_samples(ifeval_dir: str) -> dict[int, dict]:
    """Load IFEval samples, keyed by doc_id."""
    items = {}
    pattern = os.path.join(ifeval_dir, "**", "samples_*.jsonl")
    for f in glob.glob(pattern, recursive=True):
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                items[entry["doc_id"]] = entry
    return items


def load_all_cell_samples(cell_dir: str) -> dict[str, dict]:
    return {
        "mmlu": load_mmlu_samples(os.path.join(cell_dir, "mmlu_generative")),
        "gsm8k": load_gsm8k_samples(os.path.join(cell_dir, "gsm8k")),
        "ifeval": load_ifeval_samples(os.path.join(cell_dir, "ifeval")),
    }


def paired_difference(
    samples_a: dict,
    samples_b: dict,
    metric_key: str = "exact_match",
) -> dict:
    common_ids = sorted(set(samples_a.keys()) & set(samples_b.keys()))
    n = len(common_ids)
    if n == 0:
        return {"n": 0, "b": 0, "c": 0, "delta_pp": 0.0, "ci_half_pp": 0.0, "ci": (0.0, 0.0)}

    b = 0
    c = 0
    both_correct = 0
    both_incorrect = 0

    for item_id in common_ids:
        item_a = samples_a[item_id]
        item_b = samples_b[item_id]

        score_a = item_a.get(metric_key, 0)
        score_b = item_b.get(metric_key, 0)

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
    discordant = b + c
    se = math.sqrt(discordant) / n if n > 0 else 0.0
    ci_half = 1.96 * se

    return {
        "n": n,
        "b": b,
        "c": c,
        "both_correct": both_correct,
        "both_incorrect": both_incorrect,
        "discordant": discordant,
        "discordance_rate": round(discordant / n, 4),
        "delta_pp": round(delta * 100, 2),
        "ci_half_pp": round(ci_half * 100, 2),
        "ci_lower_pp": round((delta - ci_half) * 100, 2),
        "ci_upper_pp": round((delta + ci_half) * 100, 2),
    }


def agreement_rate(samples_a: dict, samples_b: dict) -> dict:
    common_ids = sorted(set(samples_a.keys()) & set(samples_b.keys()))
    n = len(common_ids)
    if n == 0:
        return {"n": 0, "identical": 0, "disagreed": 0, "agreement_rate": 0.0, "disagreements": []}

    identical = 0
    disagreements = []

    for item_id in common_ids:
        item_a = samples_a[item_id]
        item_b = samples_b[item_id]

        resp_a = item_a.get("filtered_resps") or item_a.get("resps")
        resp_b = item_b.get("filtered_resps") or item_b.get("resps")

        if resp_a == resp_b:
            identical += 1
        else:
            disagreements.append({
                "item_id": item_id,
                "resp_a": resp_a,
                "resp_b": resp_b,
                "target": item_a.get("target"),
            })

    return {
        "n": n,
        "identical": identical,
        "disagreed": len(disagreements),
        "agreement_pct": round(identical / n * 100, 2),
        "first_disagreement": disagreements[0] if disagreements else None,
    }


def run_full_analysis(results_dir: str) -> dict:
    # 1. Gather all manifests
    manifests = {}
    for mpath in glob.glob(os.path.join(results_dir, "**", "manifest.json"), recursive=True):
        m = json.load(open(mpath))
        cell = m["cell"]
        manifests[cell] = m

    # 2. Load samples for primary cells
    cells = {
        "stock4bit__vmlx": load_all_cell_samples(os.path.join(results_dir, "column-vmlx", "stock4bit__vmlx")),
        "jang4s__vmlx": load_all_cell_samples(os.path.join(results_dir, "column-vmlx", "jang4s__vmlx")),
        "oq4__vmlx": load_all_cell_samples(os.path.join(results_dir, "column-vmlx", "oq4__vmlx")),
        "oq4e__vmlx": load_all_cell_samples(os.path.join(results_dir, "column-vmlx", "oq4e__vmlx")),
        "jang4s__osaurus": load_all_cell_samples(os.path.join(results_dir, "column-osaurus", "jang4s__osaurus")),
        "oq4__osaurus": load_all_cell_samples(os.path.join(results_dir, "column-osaurus", "oq4__osaurus")),
        "oq4e__osaurus": load_all_cell_samples(os.path.join(results_dir, "column-osaurus", "oq4e__osaurus")),
        "optiq__osaurus": load_all_cell_samples(os.path.join(results_dir, "column-osaurus", "optiq__osaurus")),
    }

    # 3. Load replicate samples
    replicates = {
        "stock4bit__vmlx_repl": load_mmlu_samples(os.path.join(results_dir, "replicate", "stock4bit__vmlx", "mmlu_generative")),
        "jang4s__vmlx_repl": load_mmlu_samples(os.path.join(results_dir, "replicate", "jang4s__vmlx", "mmlu_generative")),
        "jang4s__osaurus_repl": load_mmlu_samples(os.path.join(results_dir, "replicate", "jang4s__osaurus", "mmlu_generative")),
    }

    analysis = {
        "primary_scores": {},
        "replicates": {},
        "vmlx_pairwise": {},
        "osaurus_pairwise": {},
        "study_2c_cross_runtime": {},
    }

    # Record primary scores
    for cell_name, cell_manifest in manifests.items():
        if cell_name.endswith("_repl"):
            continue
        tasks_scores = {}
        for tname, tinfo in cell_manifest.get("tasks", {}).items():
            tasks_scores[tname] = {
                "score": tinfo.get("score"),
                "metric": tinfo.get("metric"),
                "duration_s": tinfo.get("duration_s"),
                "items": tinfo.get("items_scored"),
            }
        analysis["primary_scores"][cell_name] = tasks_scores

    # Replicate stability check
    for repl_key, repl_samples in replicates.items():
        base_key = repl_key.replace("_repl", "")
        base_samples = cells[base_key]["mmlu"]
        agr = agreement_rate(base_samples, repl_samples)
        score_base = manifests[base_key]["tasks"]["mmlu_generative"]["score"]
        score_repl = manifests[repl_key]["tasks"]["mmlu_generative"]["score"]
        analysis["replicates"][repl_key] = {
            "score_primary": score_base,
            "score_replicate": score_repl,
            "delta_pp": round((score_repl - score_base) * 100, 4),
            "agreement_pct": agr["agreement_pct"],
            "disagreed": agr["disagreed"],
        }

    # Pairwise within Column A (vMLX) on MMLU
    pairs_vmlx = [
        ("jang4s__vmlx", "stock4bit__vmlx"),
        ("jang4s__vmlx", "oq4__vmlx"),
        ("jang4s__vmlx", "oq4e__vmlx"),
        ("oq4__vmlx", "stock4bit__vmlx"),
        ("oq4e__vmlx", "stock4bit__vmlx"),
        ("oq4__vmlx", "oq4e__vmlx"),
    ]
    for c_a, c_b in pairs_vmlx:
        pair_key = f"{c_a} vs {c_b}"
        analysis["vmlx_pairwise"][pair_key] = {
            "mmlu": paired_difference(cells[c_a]["mmlu"], cells[c_b]["mmlu"]),
            "gsm8k": paired_difference(cells[c_a]["gsm8k"], cells[c_b]["gsm8k"]),
            "ifeval": paired_difference(cells[c_a]["ifeval"], cells[c_b]["ifeval"], metric_key="prompt_level_strict_acc"),
        }

    # Pairwise within Column B (Osaurus)
    pairs_osaurus = [
        ("jang4s__osaurus", "optiq__osaurus"),
        ("oq4__osaurus", "optiq__osaurus"),
        ("oq4e__osaurus", "optiq__osaurus"),
        ("jang4s__osaurus", "oq4__osaurus"),
        ("jang4s__osaurus", "oq4e__osaurus"),
        ("oq4__osaurus", "oq4e__osaurus"),
    ]
    for c_a, c_b in pairs_osaurus:
        pair_key = f"{c_a} vs {c_b}"
        analysis["osaurus_pairwise"][pair_key] = {
            "mmlu": paired_difference(cells[c_a]["mmlu"], cells[c_b]["mmlu"]),
            "gsm8k": paired_difference(cells[c_a]["gsm8k"], cells[c_b]["gsm8k"]),
            "ifeval": paired_difference(cells[c_a]["ifeval"], cells[c_b]["ifeval"], metric_key="prompt_level_strict_acc"),
        }

    # Study 2C: Cross-Runtime agreement on shared formats
    for fmt in ["jang4s", "oq4", "oq4e"]:
        c_vmlx = f"{fmt}__vmlx"
        c_osa = f"{fmt}__osaurus"
        analysis["study_2c_cross_runtime"][fmt] = {
            "mmlu": agreement_rate(cells[c_vmlx]["mmlu"], cells[c_osa]["mmlu"]),
            "gsm8k": agreement_rate(cells[c_vmlx]["gsm8k"], cells[c_osa]["gsm8k"]),
            "ifeval": agreement_rate(cells[c_vmlx]["ifeval"], cells[c_osa]["ifeval"]),
        }

    return analysis


def self_test() -> int:
    samples_1 = {0: {"doc_id": 0, "exact_match": 1.0, "filtered_resps": ["A"], "target": "A"}}
    samples_2 = {0: {"doc_id": 0, "exact_match": 1.0, "filtered_resps": ["A"], "target": "A"}}
    assert paired_difference(samples_1, samples_2)["n"] == 1
    assert agreement_rate(samples_1, samples_2)["agreement_pct"] == 100.0
    print("analyze_accuracy_dense self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze dense accuracy results.")
    parser.add_argument("--results-dir", default="results/accuracy-dense", help="Results directory")
    parser.add_argument("--out", help="Optional JSON output path")
    parser.add_argument("--self-test", action="store_true", help="Run offline unit self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    data = run_full_analysis(args.results_dir)
    out_path = args.out or os.path.join(args.results_dir, "analysis_summary.json")
    Path(out_path).write_text(json.dumps(data, indent=2), "utf-8")
    print(f"Analysis summary written to {out_path}")

    # Print headline findings to console
    print("\n" + "=" * 60)
    print("PLAN 02-02 DENSE ACCURACY STUDY: HEADLINE FINDINGS")
    print("=" * 60)

    print("\n--- 1. Replicate Stability (MMLU 5-shot) ---")
    for rname, rinfo in data["replicates"].items():
        print(f"{rname:<22}: primary={rinfo['score_primary']:.4f} repl={rinfo['score_replicate']:.4f} delta={rinfo['delta_pp']:+.2f}pp agreement={rinfo['agreement_pct']}%")

    print("\n--- 2. Column A (vMLX) Accuracy Scores ---")
    for c in ["stock4bit__vmlx", "jang4s__vmlx", "oq4__vmlx", "oq4e__vmlx"]:
        ts = data["primary_scores"][c]
        print(f"{c:<18}: MMLU={ts['mmlu_generative']['score']*100:.2f}% | GSM8K={ts['gsm8k']['score']*100:.1f}% | IFEval={ts['ifeval']['score']*100:.1f}%")

    print("\n--- 3. Column B (Osaurus) Accuracy Scores ---")
    for c in ["jang4s__osaurus", "oq4__osaurus", "oq4e__osaurus", "optiq__osaurus"]:
        ts = data["primary_scores"][c]
        print(f"{c:<18}: MMLU={ts['mmlu_generative']['score']*100:.2f}% | GSM8K={ts['gsm8k']['score']*100:.1f}% | IFEval={ts['ifeval']['score']*100:.1f}%")

    print("\n--- 4. Q2: JANG_4S vs stock4bit (vMLX) ---")
    q2_mmlu = data["vmlx_pairwise"]["jang4s__vmlx vs stock4bit__vmlx"]["mmlu"]
    print(f"MMLU paired Δ : {q2_mmlu['delta_pp']:+.2f} pp [95% CI: {q2_mmlu['ci_lower_pp']:+.2f} to {q2_mmlu['ci_upper_pp']:+.2f} pp] (discordant={q2_mmlu['discordant']}/{q2_mmlu['n']})")
    q2_gsm = data["vmlx_pairwise"]["jang4s__vmlx vs stock4bit__vmlx"]["gsm8k"]
    print(f"GSM8K paired Δ: {q2_gsm['delta_pp']:+.2f} pp [95% CI: {q2_gsm['ci_lower_pp']:+.2f} to {q2_gsm['ci_upper_pp']:+.2f} pp] (discordant={q2_gsm['discordant']}/{q2_gsm['n']})")
    q2_ife = data["vmlx_pairwise"]["jang4s__vmlx vs stock4bit__vmlx"]["ifeval"]
    print(f"IFEval paired Δ: {q2_ife['delta_pp']:+.2f} pp [95% CI: {q2_ife['ci_lower_pp']:+.2f} to {q2_ife['ci_upper_pp']:+.2f} pp] (discordant={q2_ife['discordant']}/{q2_ife['n']})")

    print("\n--- 5. Q3: OptiQ Pareto Dominance (Osaurus) ---")
    for comp in ["jang4s__osaurus", "oq4__osaurus", "oq4e__osaurus"]:
        key = f"{comp} vs optiq__osaurus"
        diff = data["osaurus_pairwise"][key]["mmlu"]
        print(f"{comp} vs optiq MMLU Δ: {diff['delta_pp']:+.2f} pp [95% CI: {diff['ci_lower_pp']:+.2f} to {diff['ci_upper_pp']:+.2f} pp]")

    print("\n--- 6. Study 2C: Cross-Runtime Agreement (vMLX vs Osaurus) ---")
    for fmt, tasks in data["study_2c_cross_runtime"].items():
        print(f"Format {fmt:<8}: MMLU agreement = {tasks['mmlu']['agreement_pct']}% | GSM8K = {tasks['gsm8k']['agreement_pct']}% | IFEval = {tasks['ifeval']['agreement_pct']}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
