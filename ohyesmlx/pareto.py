"""Interactive Pareto frontier visualization for OhYesMLX.

Generates standalone, zero-dependency HTML5/SVG interactive visualizations linking
Speed (decode tok/s), Memory Footprint (phys_footprint, disk bytes), and Quality
(MMLU, IFEval, GSM8K accuracy) across evaluated models and serving runtimes on Apple Silicon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Pinned coordinates quoted from the verified research records:
# - Dense Qwen3.5-4B: docs/research/2026-09-18-accuracy-dense.md & 2026-09-19-accuracy-pareto.md
# - MoE LFM2.5-8B-A1B: docs/research/2026-09-19-accuracy-moe.md & 2026-09-19-accuracy-pareto.md
# - 35B MoE Qwen3.6-35B-A3B: docs/research/2026-09-20-35b-moe-serving.md, native-mtp, & streaming
BENCHMARK_DATA: list[dict[str, Any]] = [
    # --- Dense Qwen3.5-4B (vMLX 1.6.59) ---
    {
        "id": "dense_jang4s_vmlx",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "JANG_4S",
        "runtime": "vMLX",
        "decode_tps": 54.2,
        "drift": "+5.9%",
        "peak_mb": 3820,
        "disk_gb": 3.207,
        "mmlu": 68.42,
        "mmlu_ci": "[-0.38, +1.43]",
        "ifeval": 79.2,
        "gsm8k": 87.2,
        "frontier": "on",
        "role": "Throughput Leader (MMLU Parity)",
        "verdict": "On Frontier. +22.6% decode vs control at zero accuracy penalty (MMLU parity, 0.0 pp replicate drift).",
    },
    {
        "id": "dense_oq4_vmlx",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "oQ4",
        "runtime": "vMLX",
        "decode_tps": 47.6,
        "drift": "+14.2%",
        "peak_mb": 3819,
        "disk_gb": 3.161,
        "mmlu": 68.20,
        "mmlu_ci": "[-0.66, +1.10]",
        "ifeval": 80.4,
        "gsm8k": 87.6,
        "frontier": "on",
        "role": "Portable Default",
        "verdict": "On Frontier. Second-fastest portable, second-smallest disk, inside accuracy tie cluster.",
    },
    {
        "id": "dense_stock4bit_vmlx",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "stock4bit",
        "runtime": "vMLX",
        "decode_tps": 44.2,
        "drift": "+16.6%",
        "peak_mb": 3843,
        "disk_gb": 3.061,
        "mmlu": 67.89,
        "mmlu_ci": "control",
        "ifeval": 78.8,
        "gsm8k": 89.6,
        "frontier": "on",
        "role": "Smallest Disk (Baseline Control)",
        "verdict": "On Frontier. Smallest on-disk footprint (3.061 GB); baseline control with solid accuracy.",
    },
    {
        "id": "dense_oq4e_vmlx",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "oQ4e",
        "runtime": "vMLX",
        "decode_tps": 46.0,
        "drift": "+5.4%",
        "peak_mb": 3946,
        "disk_gb": 3.168,
        "mmlu": 66.89,
        "mmlu_ci": "[-1.86, -0.15]",
        "ifeval": 84.0,
        "gsm8k": 84.4,
        "frontier": "off",
        "role": "IFEval Leader",
        "verdict": "Off MMLU Frontier (dominated by JANG_4S on MMLU & peak), but leads column on IFEval (84.0%).",
    },
    # --- Dense Qwen3.5-4B (Osaurus 0.25.6) ---
    {
        "id": "dense_jang4s_osaurus",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "JANG_4S",
        "runtime": "Osaurus",
        "decode_tps": 42.5,
        "drift": "+5.1%",
        "peak_mb": 3400,
        "disk_gb": 3.207,
        "mmlu": 64.87,
        "mmlu_ci": "[+2.45, +5.18] vs optiq",
        "ifeval": 77.6,
        "gsm8k": 82.0,
        "frontier": "on",
        "role": "Throughput Leader",
        "verdict": "On Frontier. Leads decode in Osaurus (+9.8% over OptiQ); dominates OptiQ on MMLU (+3.82 pp).",
    },
    {
        "id": "dense_oq4e_osaurus",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "oQ4e",
        "runtime": "Osaurus",
        "decode_tps": 38.6,
        "drift": "+6.2%",
        "peak_mb": 2216,
        "disk_gb": 3.168,
        "mmlu": 65.44,
        "mmlu_ci": "[+2.76, +6.01] vs optiq",
        "ifeval": 78.0,
        "gsm8k": 80.4,
        "frontier": "on",
        "role": "MMLU & Footprint Leader",
        "verdict": "On Frontier. Lowest peak memory (2,216 MB) and highest MMLU in Osaurus column.",
    },
    {
        "id": "dense_oq4_osaurus",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "oQ4",
        "runtime": "Osaurus",
        "decode_tps": 38.8,
        "drift": "+18.7%",
        "peak_mb": 2466,
        "disk_gb": 3.161,
        "mmlu": 64.17,
        "mmlu_ci": "[+1.82, +4.41] vs optiq",
        "ifeval": 83.6,
        "gsm8k": 81.2,
        "frontier": "on",
        "role": "Portable IFEval Leader",
        "verdict": "On Frontier. Second lowest disk (3.161 GB), ties portables on speed, leads IFEval in Osaurus.",
    },
    {
        "id": "dense_optiq_osaurus",
        "model": "Qwen3.5-4B",
        "model_type": "dense",
        "format": "OptiQ",
        "runtime": "Osaurus",
        "decode_tps": 38.7,
        "drift": "-1.0%",
        "peak_mb": 2472,
        "disk_gb": 4.044,
        "mmlu": 61.05,
        "mmlu_ci": "dominated",
        "ifeval": 74.4,
        "gsm8k": 76.8,
        "frontier": "off",
        "role": "Strictly Dominated",
        "verdict": "Off Frontier (Eliminated). Trails MMLU by 3.1-4.4 pp; +28% larger disk; strictly dominated.",
    },
    # --- MoE LFM2.5-8B-A1B (vMLX 1.6.59) ---
    {
        "id": "moe_jang2l_vmlx",
        "model": "LFM2.5-8B-A1B",
        "model_type": "moe_8b",
        "format": "JANG_2L",
        "runtime": "vMLX",
        "decode_tps": 116.3,
        "drift": "+0.5%",
        "peak_mb": 3624,
        "disk_gb": 3.062,
        "mmlu": None,
        "mmlu_ci": "halted (502)",
        "ifeval": 56.8,
        "gsm8k": None,
        "frontier": "undetermined",
        "role": "Density & Footprint Leader",
        "verdict": "Density Frontier. 36.0% disk reduction, 30.5% memory reduction; IFEval preserved (56.8%).",
    },
    {
        "id": "moe_stock4bit_vmlx",
        "model": "LFM2.5-8B-A1B",
        "model_type": "moe_8b",
        "format": "stock4bit",
        "runtime": "vMLX",
        "decode_tps": 115.3,
        "drift": "+3.9%",
        "peak_mb": 5214,
        "disk_gb": 4.782,
        "mmlu": 35.53,
        "mmlu_ci": "control",
        "ifeval": 52.0,
        "gsm8k": 40.0,
        "frontier": "on",
        "role": "Baseline Control (Replicate-Confirmed)",
        "verdict": "On Frontier. Dominates OptiQ and oQ4 on all three axes; 100.0% replicate determinism.",
    },
    {
        "id": "moe_oq4e_vmlx",
        "model": "LFM2.5-8B-A1B",
        "model_type": "moe_8b",
        "format": "oQ4e",
        "runtime": "vMLX",
        "decode_tps": 97.0,
        "drift": "+10.9%",
        "peak_mb": 5416,
        "disk_gb": 4.995,
        "mmlu": 36.23,
        "mmlu_ci": "[+5.12, +10.84] vs optiq",
        "ifeval": 60.8,
        "gsm8k": 41.6,
        "frontier": "on",
        "role": "MMLU Leader (Outlier Protected)",
        "verdict": "On Frontier. Highest measured MMLU (36.23%); outlier protection gains +14.3 pp over oQ4.",
    },
    {
        "id": "moe_optiq_vmlx",
        "model": "LFM2.5-8B-A1B",
        "model_type": "moe_8b",
        "format": "OptiQ",
        "runtime": "vMLX",
        "decode_tps": 100.6,
        "drift": "+6.1%",
        "peak_mb": 5869,
        "disk_gb": 5.473,
        "mmlu": 28.25,
        "mmlu_ci": "[-10.21, -4.35] vs stock",
        "ifeval": 62.4,
        "gsm8k": 37.6,
        "frontier": "off",
        "role": "Dominated on MMLU",
        "verdict": "Off MMLU Frontier. Dominated on all three pairs by stock4bit (-7.28 pp MMLU, +14% disk).",
    },
    {
        "id": "moe_oq4_vmlx",
        "model": "LFM2.5-8B-A1B",
        "model_type": "moe_8b",
        "format": "oQ4",
        "runtime": "vMLX",
        "decode_tps": 65.6,
        "drift": "+76.0%",
        "peak_mb": 5415,
        "disk_gb": 4.995,
        "mmlu": 21.93,
        "mmlu_ci": "floor failure",
        "ifeval": 48.4,
        "gsm8k": 22.8,
        "frontier": "off",
        "role": "Floor Failure (Unprotected MoE)",
        "verdict": "Off Frontier (Eliminated). Unprotected MoE triggers 21.9% floor collapse; dominated.",
    },
    # --- 35B MoE Qwen3.6-35B-A3B (Serving Scaling & Acceleration) ---
    {
        "id": "35b_stock4bit_vmlx",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "stock4bit",
        "runtime": "vMLX",
        "decode_tps": 67.2,
        "drift": "+1.2%",
        "peak_mb": 20500,
        "disk_gb": 20.43,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "on",
        "role": "35B Resident Control",
        "verdict": "On Frontier. Uniform 4-bit leads decode across 40 layers x 256 experts (67.2 tok/s).",
    },
    {
        "id": "35b_stock4bit_osaurus",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "stock4bit",
        "runtime": "Osaurus",
        "decode_tps": 70.1,
        "drift": "+0.8%",
        "peak_mb": 13300,
        "disk_gb": 20.43,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "on",
        "role": "35B Resident Throughput Leader",
        "verdict": "On Frontier. 70.1 tok/s decode; 13.3 GB footprint reflects wired driver page allocation.",
    },
    {
        "id": "35b_native_mtp_vmlx",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "Native MTP (D=1)",
        "runtime": "vMLX",
        "decode_tps": 103.1,
        "drift": "+0.9%",
        "peak_mb": 20573,
        "disk_gb": 21.03,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "on",
        "role": "Speculative Acceleration Leader",
        "verdict": "On Frontier. +31.0% decode speedup (103.1 tok/s) at 85% acceptance with +73 MB RAM overhead.",
    },
    {
        "id": "35b_jang_tq4_vmlx",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "JANG_TQ4",
        "runtime": "vMLX",
        "decode_tps": 58.4,
        "drift": "+1.5%",
        "peak_mb": 19000,
        "disk_gb": 19.71,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "on",
        "role": "35B Density Leader",
        "verdict": "On Frontier. Saves 720 MB disk and 1.5 GB resident RAM; decode trails stock by -13.1%.",
    },
    {
        "id": "35b_optiq_optiq",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "OptiQ",
        "runtime": "OptiQ",
        "decode_tps": 56.3,
        "drift": "-0.5%",
        "peak_mb": 21500,
        "disk_gb": 24.69,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "off",
        "role": "Strictly Dominated",
        "verdict": "Off Frontier. +20.8% disk penalty (24.69 GB); slowest resident decode (56.3 tok/s).",
    },
    {
        "id": "35b_streaming_optiq",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "OptiQ SSD Streaming",
        "runtime": "OptiQ",
        "decode_tps": 8.1,
        "drift": "+0.2%",
        "peak_mb": 3900,
        "disk_gb": 24.69,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "on",
        "role": "SSD Streaming (16 GB Mac Floor)",
        "verdict": "On Frontier. 75% memory collapse (3.9 GB) enables 35B serving on 16 GB Macs at 8.1 tok/s.",
    },
    {
        "id": "35b_streaming_flashmoe",
        "model": "Qwen3.6-35B-A3B",
        "model_type": "moe_35b",
        "format": "vMLX FlashMoE Streaming",
        "runtime": "vMLX",
        "decode_tps": 4.3,
        "drift": "+0.1%",
        "peak_mb": 3170,
        "disk_gb": 20.43,
        "mmlu": None,
        "mmlu_ci": "n/a",
        "ifeval": None,
        "gsm8k": None,
        "frontier": "on",
        "role": "Zero-RAM Overhead Streaming",
        "verdict": "On Frontier. 88% memory reduction (isolating 2.28 GB backbone) at 4.3 tok/s disk-bound decode.",
    },
]


def build_pareto_dataset() -> list[dict[str, Any]]:
    """Return the curated benchmark coordinates dataset across all verified plans."""
    return list(BENCHMARK_DATA)


def generate_pareto_html(dataset: list[dict[str, Any]] | None = None) -> str:
    """Generate a self-contained, zero-dependency HTML5/SVG interactive visualization."""
    data = dataset if dataset is not None else build_pareto_dataset()
    data_json = json.dumps(data, indent=2)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OhYesMLX — Multi-Dimensional Pareto Frontier Visualization</title>
<style>
  :root {{
    --bg-base: #0f1012;
    --bg-surface: #18191d;
    --bg-card: #202227;
    --border-color: #2e3138;
    --text-main: #f0f2f5;
    --text-muted: #9ba1ad;
    --accent-gold: #e5a93c;
    --accent-cyan: #38bdf8;
    --accent-green: #34d399;
    --accent-red: #f87171;
    --accent-purple: #c084fc;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background-color: var(--bg-base);
    color: var(--text-main);
    font-family: var(--font-sans);
    line-height: 1.5;
    padding: 24px;
  }}
  .container {{ max-width: 1300px; margin: 0 auto; }}
  header {{
    margin-bottom: 24px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--border-color);
  }}
  h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 6px; }}
  .subtitle {{ color: var(--text-muted); font-size: 14px; max-width: 860px; }}
  .badge-bar {{ display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }}
  .badge {{
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-family: var(--font-mono);
  }}
  .badge strong {{ color: var(--accent-cyan); }}

  /* Controls */
  .controls-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 20px;
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    padding: 14px 18px;
    border-radius: 10px;
    align-items: center;
  }}
  .control-group {{ display: flex; flex-direction: column; gap: 4px; }}
  .control-label {{ font-size: 11px; text-transform: uppercase; font-weight: 600; color: var(--text-muted); letter-spacing: 0.05em; }}
  select, button {{
    background: var(--bg-card);
    color: var(--text-main);
    border: 1px solid var(--border-color);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-family: var(--font-sans);
    cursor: pointer;
  }}
  select:focus, button:focus {{ outline: 2px solid var(--accent-cyan); }}
  .btn-active {{ background: var(--accent-cyan); color: #000; font-weight: 600; }}

  /* Layout */
  .main-grid {{
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 20px;
    margin-bottom: 24px;
  }}
  @media (max-width: 960px) {{
    .main-grid {{ grid-template-columns: 1fr; }}
  }}

  /* Chart Area */
  .chart-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 20px;
    position: relative;
  }}
  .chart-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }}
  .chart-title {{ font-size: 15px; font-weight: 600; }}
  svg {{ width: 100%; height: 500px; display: block; overflow: visible; }}

  /* Inspector Sidebar */
  .inspector-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .inspector-title {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 700; }}
  .item-name {{ font-size: 18px; font-weight: 700; color: var(--text-main); }}
  .item-meta {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; }}
  .metric-box {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    padding: 10px 14px;
    border-radius: 8px;
    font-family: var(--font-mono);
    font-size: 13px;
    display: flex;
    justify-content: space-between;
  }}
  .metric-box .label {{ color: var(--text-muted); }}
  .metric-box .val {{ font-weight: 600; color: var(--accent-cyan); }}
  .verdict-box {{
    background: #17232e;
    border: 1px solid #1f3e58;
    color: #93c5fd;
    padding: 12px;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.4;
  }}

  /* Data Table */
  .table-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 20px;
    overflow-x: auto;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
  th {{
    background: var(--bg-card);
    padding: 10px 12px;
    color: var(--text-muted);
    font-weight: 600;
    border-bottom: 1px solid var(--border-color);
    font-family: var(--font-mono);
  }}
  td {{
    padding: 9px 12px;
    border-bottom: 1px solid var(--border-color);
    font-family: var(--font-mono);
  }}
  tr:hover {{ background: rgba(255,255,255,0.03); cursor: pointer; }}
  .pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }}
  .pill-on {{ background: rgba(52, 211, 153, 0.2); color: var(--accent-green); border: 1px solid rgba(52, 211, 153, 0.4); }}
  .pill-off {{ background: rgba(248, 113, 113, 0.2); color: var(--accent-red); border: 1px solid rgba(248, 113, 113, 0.4); }}
  .pill-undetermined {{ background: rgba(192, 132, 252, 0.2); color: var(--accent-purple); border: 1px solid rgba(192, 132, 252, 0.4); }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>OhYesMLX — Multi-Dimensional Pareto Frontier</h1>
    <p class="subtitle">
      Single-variable serving performance, memory footprint, and benchmark accuracy on Apple Silicon across dense 4B, MoE 8B, and MoE 35B models. Standalone, zero-dependency visualization.
    </p>
    <div class="badge-bar">
      <span class="badge">Evaluated Models: <strong>3 (Qwen3.5-4B, LFM2.5-8B, Qwen3.6-35B)</strong></span>
      <span class="badge">Serving Runtimes: <strong>vMLX, Osaurus, mlx-lm, OptiQ, oMLX</strong></span>
      <span class="badge">Verified Cells: <strong>18 configurations</strong></span>
      <span class="badge">Discipline: <strong>Vary one thing at a time</strong></span>
    </div>
  </header>

  <div class="controls-bar">
    <div class="control-group">
      <span class="control-label">Projection View</span>
      <select id="viewSelect">
        <option value="speed_vs_accuracy" selected>1. Speed vs Quality (Decode tok/s vs MMLU %)</option>
        <option value="speed_vs_memory">2. Speed vs Footprint (Decode tok/s vs Peak RAM)</option>
        <option value="speed_vs_disk">3. Speed vs On-Disk Size (Decode tok/s vs Disk GB)</option>
        <option value="memory_vs_accuracy">4. Quality vs Footprint (MMLU % vs Disk GB)</option>
        <option value="scaling_35b">5. 35B MoE Scaling (Resident vs MTP vs Streaming)</option>
      </select>
    </div>
    <div class="control-group">
      <span class="control-label">Model Filter</span>
      <select id="modelFilter">
        <option value="all" selected>All Models</option>
        <option value="Qwen3.5-4B">Dense Qwen3.5-4B</option>
        <option value="LFM2.5-8B-A1B">MoE LFM2.5-8B-A1B</option>
        <option value="Qwen3.6-35B-A3B">MoE Qwen3.6-35B-A3B</option>
      </select>
    </div>
    <div class="control-group">
      <span class="control-label">Runtime Filter</span>
      <select id="runtimeFilter">
        <option value="all" selected>All Runtimes</option>
        <option value="vMLX">vMLX 1.6.59</option>
        <option value="Osaurus">Osaurus 0.25.x</option>
        <option value="OptiQ">OptiQ 0.5.6</option>
      </select>
    </div>
    <div class="control-group">
      <span class="control-label">Frontier Hull Overlay</span>
      <button id="toggleHull" class="btn-active">Draw Pareto Frontier</button>
    </div>
  </div>

  <div class="main-grid">
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title" id="chartHeading">Decode Throughput (tok/s) vs Accuracy (MMLU %)</div>
        <div style="font-size: 12px; color: var(--text-muted);">Hover points for details</div>
      </div>
      <svg id="chartSvg" viewBox="0 0 800 500"></svg>
    </div>

    <div class="inspector-card" id="inspectorCard">
      <div class="inspector-title">Configuration Inspector</div>
      <div class="item-name" id="inspName">JANG_4S (vMLX)</div>
      <div class="item-meta" id="inspMeta">Model: Qwen3.5-4B | Status: On Frontier</div>
      <div class="metric-box"><span class="label">Decode Rate:</span><span class="val" id="inspDecode">54.2 tok/s (+5.9% drift)</span></div>
      <div class="metric-box"><span class="label">Peak Footprint:</span><span class="val" id="inspPeak">3,820 MB</span></div>
      <div class="metric-box"><span class="label">Disk Size:</span><span class="val" id="inspDisk">3.207 GB</span></div>
      <div class="metric-box"><span class="label">MMLU Accuracy:</span><span class="val" id="inspMmlu">68.42% (Parity)</span></div>
      <div class="metric-box"><span class="label">IFEval Accuracy:</span><span class="val" id="inspIfeval">79.2%</span></div>
      <div class="metric-box"><span class="label">GSM8K Accuracy:</span><span class="val" id="inspGsm8k">87.2%</span></div>
      <div class="verdict-box" id="inspVerdict">
        On Frontier. Replicated +22.6% decode advantage over uniform 4-bit control at zero measured accuracy cost (0.0 pp replicate drift).
      </div>
    </div>
  </div>

  <div class="table-card">
    <h3 style="font-size: 15px; margin-bottom: 12px; font-weight: 600;">Verified Pareto Coordinate Matrix</h3>
    <table id="dataTable">
      <thead>
        <tr>
          <th>Model</th>
          <th>Format</th>
          <th>Runtime</th>
          <th>Decode (tok/s)</th>
          <th>Peak (MB)</th>
          <th>Disk (GB)</th>
          <th>MMLU (%)</th>
          <th>IFEval (%)</th>
          <th>Frontier Status</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>

<script>
const RAW_DATA = {data_json};

let currentView = 'speed_vs_accuracy';
let currentModel = 'all';
let currentRuntime = 'all';
let showHull = true;

const svg = document.getElementById('chartSvg');
const viewSelect = document.getElementById('viewSelect');
const modelFilter = document.getElementById('modelFilter');
const runtimeFilter = document.getElementById('runtimeFilter');
const toggleHullBtn = document.getElementById('toggleHull');
const chartHeading = document.getElementById('chartHeading');

viewSelect.addEventListener('change', (e) => {{ currentView = e.target.value; render(); }});
modelFilter.addEventListener('change', (e) => {{ currentModel = e.target.value; render(); }});
runtimeFilter.addEventListener('change', (e) => {{ currentRuntime = e.target.value; render(); }});
toggleHullBtn.addEventListener('click', () => {{
  showHull = !showHull;
  toggleHullBtn.classList.toggle('btn-active', showHull);
  render();
}});

function getFilteredData() {{
  return RAW_DATA.filter(d => {{
    if (currentModel !== 'all' && d.model !== currentModel) return false;
    if (currentRuntime !== 'all' && d.runtime !== currentRuntime) return false;
    if (currentView === 'speed_vs_accuracy' && d.mmlu === null) return false;
    if (currentView === 'memory_vs_accuracy' && d.mmlu === null) return false;
    if (currentView === 'scaling_35b' && d.model !== 'Qwen3.6-35B-A3B') return false;
    return true;
  }});
}}

function getAxisProps(view) {{
  switch(view) {{
    case 'speed_vs_accuracy':
      return {{
        xKey: 'decode_tps', xLabel: 'Decode Throughput (tok/s) [Higher is Better]',
        yKey: 'mmlu', yLabel: 'MMLU Accuracy (%) [Higher is Better]',
        title: 'Speed vs Quality: Decode Throughput vs MMLU Accuracy',
        invertY: false
      }};
    case 'speed_vs_memory':
      return {{
        xKey: 'decode_tps', xLabel: 'Decode Throughput (tok/s) [Higher is Better]',
        yKey: 'peak_mb', yLabel: 'Peak Memory Footprint (MB) [Lower is Better]',
        title: 'Speed vs Memory: Decode Throughput vs Peak Memory (phys_footprint)',
        invertY: true
      }};
    case 'speed_vs_disk':
      return {{
        xKey: 'decode_tps', xLabel: 'Decode Throughput (tok/s) [Higher is Better]',
        yKey: 'disk_gb', yLabel: 'On-Disk Size (GB) [Lower is Better]',
        title: 'Speed vs Storage: Decode Throughput vs Disk Footprint',
        invertY: true
      }};
    case 'memory_vs_accuracy':
      return {{
        xKey: 'disk_gb', xLabel: 'On-Disk Size (GB) [Lower is Better]',
        yKey: 'mmlu', yLabel: 'MMLU Accuracy (%) [Higher is Better]',
        title: 'Quality vs Storage: On-Disk Footprint vs MMLU Accuracy',
        invertX: true, invertY: false
      }};
    case 'scaling_35b':
      return {{
        xKey: 'decode_tps', xLabel: 'Decode Throughput (tok/s) [Higher is Better]',
        yKey: 'peak_mb', yLabel: 'Peak Memory Footprint (MB) [Lower is Better]',
        title: '35B MoE Scaling: Resident vs Native MTP vs SSD Streaming',
        invertY: true
      }};
  }}
}}

function updateInspector(d) {{
  document.getElementById('inspName').innerText = `${{d.format}} (${{d.runtime}})`;
  document.getElementById('inspMeta').innerText = `Model: ${{d.model}} | Status: ${{d.frontier.toUpperCase()}} (${{d.role}})`;
  document.getElementById('inspDecode').innerText = `${{d.decode_tps}} tok/s (${{d.drift}})`;
  document.getElementById('inspPeak').innerText = `${{d.peak_mb.toLocaleString()}} MB`;
  document.getElementById('inspDisk').innerText = `${{d.disk_gb}} GB`;
  document.getElementById('inspMmlu').innerText = d.mmlu !== null ? `${{d.mmlu}}% (${{d.mmlu_ci}})` : 'N/A (halted/omitted)';
  document.getElementById('inspIfeval').innerText = d.ifeval !== null ? `${{d.ifeval}}%` : 'N/A';
  document.getElementById('inspGsm8k').innerText = d.gsm8k !== null ? `${{d.gsm8k}}%` : 'N/A';
  document.getElementById('inspVerdict').innerText = d.verdict;
}}

function render() {{
  const items = getFilteredData();
  const {{ xKey, xLabel, yKey, yLabel, title, invertX, invertY }} = getAxisProps(currentView);
  chartHeading.innerText = title;

  svg.innerHTML = '';
  const W = 800, H = 500;
  const padL = 70, padR = 40, padT = 30, padB = 60;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  if (items.length === 0) {{
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', W/2); t.setAttribute('y', H/2);
    t.setAttribute('fill', '#9ba1ad'); t.setAttribute('text-anchor', 'middle');
    t.textContent = 'No matching benchmark points for current filters.';
    svg.appendChild(t);
    return;
  }}

  const xVals = items.map(d => d[xKey]);
  const yVals = items.map(d => d[yKey]);

  let xMin = Math.min(...xVals);
  let xMax = Math.max(...xVals);
  let yMin = Math.min(...yVals);
  let yMax = Math.max(...yVals);

  // Add padding margins
  const xSpan = (xMax - xMin) || 1;
  const ySpan = (yMax - yMin) || 1;
  xMin = Math.max(0, xMin - xSpan * 0.08);
  xMax = xMax + xSpan * 0.08;
  yMin = Math.max(0, yMin - ySpan * 0.08);
  yMax = yMax + ySpan * 0.08;

  function toX(val) {{
    const ratio = (val - xMin) / (xMax - xMin);
    return padL + (invertX ? (1 - ratio) : ratio) * plotW;
  }}

  function toY(val) {{
    const ratio = (val - yMin) / (yMax - yMin);
    return padT + (invertY ? ratio : (1 - ratio)) * plotH;
  }}

  // Draw Grid & Axes
  const axisG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  axisG.setAttribute('stroke', '#2e3138');
  axisG.setAttribute('stroke-width', '1');

  // X ticks
  const numXTicks = 6;
  for (let i = 0; i <= numXTicks; i++) {{
    const val = xMin + (xMax - xMin) * (i / numXTicks);
    const xPos = toX(val);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', xPos); line.setAttribute('x2', xPos);
    line.setAttribute('y1', padT); line.setAttribute('y2', padT + plotH);
    axisG.appendChild(line);

    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', xPos); txt.setAttribute('y', padT + plotH + 20);
    txt.setAttribute('fill', '#9ba1ad'); txt.setAttribute('font-size', '11');
    txt.setAttribute('font-family', 'ui-monospace, monospace');
    txt.setAttribute('text-anchor', 'middle');
    txt.textContent = val >= 1000 ? (val/1000).toFixed(1) + 'k' : val.toFixed(1);
    svg.appendChild(txt);
  }}

  // Y ticks
  const numYTicks = 5;
  for (let i = 0; i <= numYTicks; i++) {{
    const val = yMin + (yMax - yMin) * (i / numYTicks);
    const yPos = toY(val);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', padL); line.setAttribute('x2', padL + plotW);
    line.setAttribute('y1', yPos); line.setAttribute('y2', yPos);
    axisG.appendChild(line);

    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', padL - 12); txt.setAttribute('y', yPos + 4);
    txt.setAttribute('fill', '#9ba1ad'); txt.setAttribute('font-size', '11');
    txt.setAttribute('font-family', 'ui-monospace, monospace');
    txt.setAttribute('text-anchor', 'end');
    txt.textContent = val >= 1000 ? (val/1000).toFixed(1) + 'k' : val.toFixed(1);
    svg.appendChild(txt);
  }}
  svg.appendChild(axisG);

  // Axis Labels
  const xLabelEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  xLabelEl.setAttribute('x', padL + plotW / 2); xLabelEl.setAttribute('y', H - 15);
  xLabelEl.setAttribute('fill', '#f0f2f5'); xLabelEl.setAttribute('font-size', '12');
  xLabelEl.setAttribute('font-weight', '600'); xLabelEl.setAttribute('text-anchor', 'middle');
  xLabelEl.textContent = xLabel;
  svg.appendChild(xLabelEl);

  const yLabelEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  yLabelEl.setAttribute('transform', `rotate(-90)`);
  yLabelEl.setAttribute('x', -(padT + plotH / 2)); yLabelEl.setAttribute('y', 20);
  yLabelEl.setAttribute('fill', '#f0f2f5'); yLabelEl.setAttribute('font-size', '12');
  yLabelEl.setAttribute('font-weight', '600'); yLabelEl.setAttribute('text-anchor', 'middle');
  yLabelEl.textContent = yLabel;
  svg.appendChild(yLabelEl);

  // Draw Pareto Hull if requested
  if (showHull) {{
    const frontierPoints = items.filter(d => d.frontier === 'on');
    // Sort points by x
    frontierPoints.sort((a, b) => a[xKey] - b[xKey]);
    if (frontierPoints.length >= 2) {{
      const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      let pathStr = `M ${{toX(frontierPoints[0][xKey])}} ${{toY(frontierPoints[0][yKey])}}`;
      for (let i = 1; i < frontierPoints.length; i++) {{
        pathStr += ` L ${{toX(frontierPoints[i][xKey])}} ${{toY(frontierPoints[i][yKey])}}`;
      }}
      pathEl.setAttribute('d', pathStr);
      pathEl.setAttribute('fill', 'none');
      pathEl.setAttribute('stroke', '#38bdf8');
      pathEl.setAttribute('stroke-width', '2');
      pathEl.setAttribute('stroke-dasharray', '5 4');
      svg.appendChild(pathEl);
    }}
  }}

  // Draw Points
  items.forEach((d) => {{
    const cx = toX(d[xKey]);
    const cy = toY(d[yKey]);

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = 'pointer';

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', cx);
    circle.setAttribute('cy', cy);
    circle.setAttribute('r', d.frontier === 'on' ? '8' : '6');

    let fill = '#38bdf8';
    if (d.frontier === 'off') fill = '#f87171';
    else if (d.frontier === 'undetermined') fill = '#c084fc';
    else if (d.role.includes('Leader')) fill = '#e5a93c';

    circle.setAttribute('fill', fill);
    circle.setAttribute('stroke', '#18191d');
    circle.setAttribute('stroke-width', '2');

    // Label on point
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', cx + 10);
    label.setAttribute('y', cy + 4);
    label.setAttribute('fill', '#f0f2f5');
    label.setAttribute('font-size', '11');
    label.setAttribute('font-family', 'ui-monospace, monospace');
    label.textContent = `${{d.format}} (${{d.runtime}})`;

    g.appendChild(circle);
    g.appendChild(label);

    g.addEventListener('mouseenter', () => {{
      circle.setAttribute('r', '11');
      circle.setAttribute('stroke', '#fff');
      updateInspector(d);
    }});
    g.addEventListener('mouseleave', () => {{
      circle.setAttribute('r', d.frontier === 'on' ? '8' : '6');
      circle.setAttribute('stroke', '#18191d');
    }});
    g.addEventListener('click', () => updateInspector(d));

    svg.appendChild(g);
  }});
}}

function renderTable() {{
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';
  RAW_DATA.forEach(d => {{
    const tr = document.createElement('tr');
    tr.addEventListener('click', () => updateInspector(d));
    const pillClass = d.frontier === 'on' ? 'pill-on' : (d.frontier === 'off' ? 'pill-off' : 'pill-undetermined');
    tr.innerHTML = `
      <td>${{d.model}}</td>
      <td><strong>${{d.format}}</strong></td>
      <td>${{d.runtime}}</td>
      <td>${{d.decode_tps}}</td>
      <td>${{d.peak_mb.toLocaleString()}}</td>
      <td>${{d.disk_gb}}</td>
      <td>${{d.mmlu !== null ? d.mmlu + '%' : '—'}}</td>
      <td>${{d.ifeval !== null ? d.ifeval + '%' : '—'}}</td>
      <td><span class="pill ${{pillClass}}">${{d.frontier.toUpperCase()}}</span></td>
    `;
    tbody.appendChild(tr);
  }});
}}

// Initial load
render();
renderTable();
updateInspector(RAW_DATA[0]);
</script>
</body>
</html>
"""
    return html


def save_pareto_html(target_path: str | Path) -> Path:
    """Generate and write the Pareto frontier visualization to *target_path*."""
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = generate_pareto_html()
    path.write_text(html, encoding="utf-8")
    return path
