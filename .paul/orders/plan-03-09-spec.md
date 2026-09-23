# Work Order: Plan 03-09 — Automated Interactive Pareto Visualization

## Objective
Build an automated interactive Pareto visualization system for OhYesMLX that renders standalone, zero-dependency HTML5/SVG interactive charts displaying the multi-dimensional Pareto frontier connecting Speed (decode tok/s, TTFT), Memory Footprint (`phys_footprint`, on-disk bytes), and Quality (MMLU, GSM8K, IFEval task accuracy) across all evaluated models (`Qwen3.5-4B`, `LFM2.5-8B-A1B`, `Qwen3.6-35B-A3B`) and serving runtimes (`vMLX`, `Osaurus`, `mlx-lm`, `oMLX`, `OptiQ`).

## Background & Standing Boundaries
- **Zero External Dependencies:** The HTML visualization must be completely self-contained. No CDNs, no external JavaScript libraries, no remote stylesheets, no internet access required.
- **Single-Variable Discipline:** Renders frontiers within declared models and runtimes, preserving the rule that memory rankings do not cross runtime boundaries (`CROSS_RUNTIME_UNCOMPARABLE`) and accuracy rankings do not cross loaders without caveat.
- **Accurate Coordinates:** Every coordinate is quoted from the verified research records (Plans 01-01 through 03-07), carrying its drift markers, intervals, and dominance classifications intact.
- **Stdlib Only:** Python generator uses stdlib only.

## Requirements & Acceptance Criteria

### 1. Visualization Generator (`ohyesmlx/pareto.py`)
- Curate and structure the Pareto dataset covering:
  - **Dense `Qwen3.5-4B`:** `jang4s` (frontier leader), `oq4` (on frontier), `stock4bit` (on frontier, disk leader), `oq4e` (IFEval leader), `optiq` (strictly dominated).
  - **MoE `LFM2.5-8B-A1B`:** `stock4bit` (control, on frontier), `oq4e` (MMLU leader, on frontier), `jang2l` (density leader, 36% disk savings, IFEval preserved), `optiq` (dominated on MMLU), `oq4` (dominated, 21.9% floor).
  - **35B MoE `Qwen3.6-35B-A3B`:** Resident serving (58–70 tok/s, 19.5–20.5 GB RAM) vs Native MTP (+31% speedup, 103.1 tok/s) vs SSD Expert Streaming (4.3–8.2 tok/s, 3.2–3.9 GB RAM).
- Provide functions:
  - `build_pareto_dataset() -> list[dict]`
  - `generate_pareto_html(dataset=None) -> str`
- Embedded interactive SVG visualization featuring:
  - Axis toggles: Throughput vs Accuracy (Speed vs Quality), Throughput vs Peak Memory (Speed vs Footprint), Footprint vs Accuracy (Memory vs Quality), and 35B Scaling & Acceleration.
  - Model and runtime interactive filters.
  - Interactive Pareto convex hull line overlay connecting non-dominated frontier points.
  - Rich hover tooltips displaying complete metric cards (Format, Runtime, Decode Rate, Drift, Peak RAM, Disk Size, Accuracy Scores, Confidence Intervals, Dominance Status).
  - Responsive, dark-mode native styling conforming to Apple/Obsidian aesthetic.

### 2. CLI Integration (`ohyesmlx/cli.py`)
- Add `pareto` subcommand:
  `ohyesmlx pareto [--out <path>]`
- Defaults to `results/pareto_frontier.html` if `--out` is not specified.
- Clean exit codes: 0 on success, 2 on invalid arguments.

### 3. Test Coverage (`tests/test_pareto.py`, `tests/test_cli.py`)
- Unit tests verifying:
  - Dataset compilation integrity and coordinate bounds.
  - HTML generation produces valid, self-contained HTML with inline SVG and script.
  - CLI `ohyesmlx pareto` generates output file and exits 0.
  - All existing tests continue to pass (100% green, expanding to 510+ tests).

## Deliverables
- `ohyesmlx/pareto.py`
- `ohyesmlx/cli.py` (updated with `pareto` subcommand)
- `tests/test_pareto.py`
- `tests/test_cli.py` (updated with `pareto` tests)
- `results/pareto_frontier.html`
- `.paul/orders/plan-03-09-spec.md`
