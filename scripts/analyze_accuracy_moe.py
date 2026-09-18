"""Plan 02-03: Comprehensive MoE Accuracy Analysis Script.

Parses all results and sample files across Column A (vMLX), replicates,
and Study 2C MoE (Osaurus) on LFM2.5-8B-A1B, computes paired McNemar
difference intervals, Study 2C cross-runtime agreement rates, replicate
stability, and produces complete statistical summary tables.
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
        parts = basename.split("_")
        sub_name = "_".join(parts[1:-1])
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
        resp_a = samples_a[item_id].get("filtered_resps", [None])[0] or samples_a[item_id].get("resps", [[None]])[0][0]
        resp_b = samples_b[item_id].get("filtered_resps", [None])[0] or samples_b[item_id].get("resps", [[None]])[0][0]

        str_a = str(resp_a).strip() if resp_a is not None else ""
        str_b = str(resp_b).strip() if resp_b is not None else ""

        if str_a == str_b:
            identical += 1
        else:
            disagreements.append({
                "doc_id": item_id,
                "resp_a": str_a[:100],
                "resp_b": str_b[:100],
                "target": str(samples_a[item_id].get("target", "")),
            })

    return {
        "n": n,
        "identical": identical,
        "disagreed": len(disagreements),
        "agreement_rate": round(identical / n, 4) if n > 0 else 0.0,
        "agreement_pct": round(identical / n * 100, 2) if n > 0 else 0.0,
        "first_disagreement": disagreements[0] if disagreements else None,
    }


def run_full_analysis(results_dir: str) -> dict:
    manifests = {}
    cells = {}
    replicates = {}

    vmlx_dir = os.path.join(results_dir, "column-vmlx")
    if os.path.isdir(vmlx_dir):
        for cname in os.listdir(vmlx_dir):
            cp = os.path.join(vmlx_dir, cname)
            mp = os.path.join(cp, "manifest.json")
            if os.path.isfile(mp):
                manifests[cname] = json.loads(Path(mp).read_text("utf-8"))
                cells[cname] = load_all_cell_samples(cp)

    study2c_dir = os.path.join(results_dir, "study-2c")
    if os.path.isdir(study2c_dir):
        for cname in os.listdir(study2c_dir):
            cp = os.path.join(study2c_dir, cname)
            mp = os.path.join(cp, "manifest.json")
            if os.path.isfile(mp):
                manifests[cname] = json.loads(Path(mp).read_text("utf-8"))
                cells[cname] = load_all_cell_samples(cp)

    repl_dir = os.path.join(results_dir, "replicate")
    if os.path.isdir(repl_dir):
        for cname in os.listdir(repl_dir):
            cp = os.path.join(repl_dir, cname)
            mp = os.path.join(cp, "manifest.json")
            if os.path.isfile(mp):
                manifests[cname + "_repl"] = json.loads(Path(mp).read_text("utf-8"))
                replicates[cname + "_repl"] = load_mmlu_samples(os.path.join(cp, "mmlu_generative"))

    analysis = {
        "primary_scores": {},
        "replicates": {},
        "vmlx_pairwise": {},
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
        if base_key in cells and "mmlu" in cells[base_key]:
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

    # Pairwise within Column A (vMLX)
    pairs_vmlx = [
        ("jang2l__vmlx", "stock4bit__vmlx"),
        ("jang2l__vmlx", "oq4__vmlx"),
        ("jang2l__vmlx", "oq4e__vmlx"),
        ("jang2l__vmlx", "optiq__vmlx"),
        ("optiq__vmlx", "stock4bit__vmlx"),
        ("optiq__vmlx", "oq4__vmlx"),
        ("optiq__vmlx", "oq4e__vmlx"),
        ("oq4__vmlx", "stock4bit__vmlx"),
        ("oq4e__vmlx", "stock4bit__vmlx"),
        ("oq4__vmlx", "oq4e__vmlx"),
    ]
    for c_a, c_b in pairs_vmlx:
        if c_a in cells and c_b in cells:
            pair_key = f"{c_a} vs {c_b}"
            analysis["vmlx_pairwise"][pair_key] = {
                "mmlu": paired_difference(cells[c_a]["mmlu"], cells[c_b]["mmlu"]),
                "gsm8k": paired_difference(cells[c_a]["gsm8k"], cells[c_b]["gsm8k"]),
                "ifeval": paired_difference(cells[c_a]["ifeval"], cells[c_b]["ifeval"], metric_key="prompt_level_strict_acc"),
            }

    # Study 2C: Cross-Runtime agreement on JANG_2L (vMLX vs Osaurus)
    if "jang2l__vmlx" in cells and "jang2l__osaurus" in cells:
        c_vmlx = "jang2l__vmlx"
        c_osa = "jang2l__osaurus"
        analysis["study_2c_cross_runtime"]["jang2l"] = {
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
    print("analyze_accuracy_moe self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze MoE accuracy results.")
    parser.add_argument("--results-dir", default="results/accuracy-moe", help="Results directory")
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
    print("PLAN 02-03 MoE ACCURACY STUDY: HEADLINE FINDINGS")
    print("=" * 60)

    print("\n--- 1. Replicate Stability (MMLU 5-shot) ---")
    for rname, rinfo in data["replicates"].items():
        print(f"{rname:<22}: primary={rinfo['score_primary']:.4f} repl={rinfo['score_replicate']:.4f} delta={rinfo['delta_pp']:+.2f}pp agreement={rinfo['agreement_pct']}%")

    print("\n--- 2. Column A (vMLX) Accuracy Scores ---")
    for c in ["stock4bit__vmlx", "jang2l__vmlx", "oq4__vmlx", "oq4e__vmlx", "optiq__vmlx"]:
        if c in data["primary_scores"]:
            ts = data["primary_scores"][c]
            mmlu_s = ts.get('mmlu_generative', {}).get('score', 0) * 100
            gsm_s = ts.get('gsm8k', {}).get('score', 0) * 100
            ife_s = ts.get('ifeval', {}).get('score', 0) * 100
            print(f"{c:<18}: MMLU={mmlu_s:.2f}% | GSM8K={gsm_s:.1f}% | IFEval={ife_s:.1f}%")

    print("\n--- 3. Study 2C: Osaurus Accuracy Scores ---")
    if "jang2l__osaurus" in data["primary_scores"]:
        ts = data["primary_scores"]["jang2l__osaurus"]
        mmlu_s = ts.get('mmlu_generative', {}).get('score', 0) * 100
        gsm_s = ts.get('gsm8k', {}).get('score', 0) * 100
        ife_s = ts.get('ifeval', {}).get('score', 0) * 100
        print(f"jang2l__osaurus   : MMLU={mmlu_s:.2f}% | GSM8K={gsm_s:.1f}% | IFEval={ife_s:.1f}%")

    print("\n--- 4. Q1: Vendor Parity Claim: JANG_2L vs stock4bit (vMLX) ---")
    key_q1 = "jang2l__vmlx vs stock4bit__vmlx"
    if key_q1 in data["vmlx_pairwise"]:
        q1_mmlu = data["vmlx_pairwise"][key_q1]["mmlu"]
        print(f"MMLU paired Δ : {q1_mmlu['delta_pp']:+.2f} pp [95% CI: {q1_mmlu['ci_lower_pp']:+.2f} to {q1_mmlu['ci_upper_pp']:+.2f} pp] (discordant={q1_mmlu['discordant']}/{q1_mmlu['n']})")
        q1_gsm = data["vmlx_pairwise"][key_q1]["gsm8k"]
        print(f"GSM8K paired Δ: {q1_gsm['delta_pp']:+.2f} pp [95% CI: {q1_gsm['ci_lower_pp']:+.2f} to {q1_gsm['ci_upper_pp']:+.2f} pp] (discordant={q1_gsm['discordant']}/{q1_gsm['n']})")
        q1_ife = data["vmlx_pairwise"][key_q1]["ifeval"]
        print(f"IFEval paired Δ: {q1_ife['delta_pp']:+.2f} pp [95% CI: {q1_ife['ci_lower_pp']:+.2f} to {q1_ife['ci_upper_pp']:+.2f} pp] (discordant={q1_ife['discordant']}/{q1_ife['n']})")

    print("\n--- 5. Q3: OptiQ Pareto Dominance (vMLX) ---")
    for comp in ["stock4bit__vmlx", "jang2l__vmlx", "oq4__vmlx", "oq4e__vmlx"]:
        key = f"optiq__vmlx vs {comp}"
        if key in data["vmlx_pairwise"]:
            diff = data["vmlx_pairwise"][key]["mmlu"]
            print(f"optiq vs {comp:<15} MMLU Δ: {diff['delta_pp']:+.2f} pp [95% CI: {diff['ci_lower_pp']:+.2f} to {diff['ci_upper_pp']:+.2f} pp]")

    print("\n--- 6. Study 2C: Cross-Runtime Agreement on JANG_2L (vMLX vs Osaurus) ---")
    if "jang2l" in data["study_2c_cross_runtime"]:
        tasks = data["study_2c_cross_runtime"]["jang2l"]
        print(f"Format jang2l: MMLU agreement = {tasks['mmlu']['agreement_pct']}% | GSM8K = {tasks['gsm8k']['agreement_pct']}% | IFEval = {tasks['ifeval']['agreement_pct']}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
