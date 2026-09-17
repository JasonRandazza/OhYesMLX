---
description: "OhYesMLX — session handoff, 2026-09-17 (midday, v1 closed)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-17, midday

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading. If this file starts growing per-session
> headings, it has become a log — rewrite it.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

## Where the project is

**v1 is closed on paper.** All six closeout items from the 2026-09-16 handoff are done,
committed, and pushed in four commits (`d388ca6`, `b3dac72`, `5e40bc4`, `9e46385`).
CI (`tests.yml`) is green on the latest push — verify with `gh run list --workflow=tests.yml`.
ROADMAP reads Phase 6 complete / 7 of 7 / milestone Complete; STATE reads 100% / UNIFY.

- **491 tests** pass (487 baseline + 4 from the drift fix), observed by the coordinator with
  `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
- **Nothing is in flight.** Before starting anything, check anyway:
  `lsof -i :1337 -i :8080 -i :8081 -i :8100 -i :8000`,
  `pgrep -fl "^/Applications/osaurus.app"`, `pgrep -fl "cc-agent|ohyesmlx.cli run|run_grid|probe_"`.
- `osaurus mcp` is Jason's and must stay up. **Never sweep by the name `osaurus`.**
  Osaurus app (pid 74720) was listening on 1337 at last check — left alone deliberately.
- **Git rule going forward:** Jason approved pushing this session. Default returns to
  local-only commits; push needs his explicit go-ahead each session.

## What this session did (all by cc-agent workers, verified and committed by the coordinator)

1. **v1 on paper** — ROADMAP 7-of-7/milestone Complete (05-02 marked superseded by
   per-cell measured warmup, not deleted), STATE 100%/UNIFY/v1-closed decision row.
   Orders in `.paul/orders/`: `residency-pin-port.md`, `ttft-drift-marker.md`,
   `empty-runner-log.md`, `runner-log-hardening.md`.
2. **Residency pin ported** — `run_grid.sh`, `run_grid_moe.sh` pin
   `modelIdleResidencyPolicy.seconds=900` around the Osaurus column only;
   `run_sweep_prompt.sh` composes the pin with its cache toggle and drops the
   drift-NONE restore (unpassable while the host keeps 30). All verified with `cmp`.
   `sh -n` clean on all three. **Never run.**
3. **TTFT drift fixed in `render_sweep` only** — entries carry the marker solely for
   decode-derived ranks (`DECODE_DERIVED_RANKS = {decode_tps}`; `itl_s` excluded —
   reciprocal sign would invert). Grids byte-identical, both TTFT sweeps marker-free,
   decode renders keep markers. Red-check done by the worker.
4. **runner.log diagnosed then hardened** — cause is launch-side (`cmd & > file`
   unbound redirect), not in-repo. Jason chose the in-repo hardening: both sweep
   runners now `exec > "$OUT/runner.log" 2>&1` after `mkdir -p`. Per-cell redirects
   override per-command, unaffected. Tradeoff: live progress only via `tail -f`.
5. **Jason's decisions, all in STATE.md Decisions:** warm-cache TTFT beside prefill
   numbers (not its own column); v2 leads with cheap closeouts (non-hybrid cache
   repeat, vMLX 32k re-test), then JANG, accuracy last; nothing starts without a
   fresh go-ahead per item.
6. **v2 options note** — `.paul/v2-options-note.md` (plan only).

## Jason's open items (his call, not a worker's)

- **README:** `README.md:60` still says "Nothing is published yet." Propose a short
  Results pointer to the research docs; do not rewrite unasked.
- **Deep Wiki:** no `10 Wiki/Projects/OhYesMLX` page exists — propose one per LEAD.md
  rather than creating it.
- **Stale Osaurus copies:** `~/.osaurus/config/…sweep-prompt-orig` and `…probe-orig`
  predate this session; delete only after confirming unneeded.

## Known follow-ups (need their own orders, all in STATE.md Deferred)

- `ohyesmlx grid --rank ttft_p50_s` has the same latent drift mislabel (frozen by the
  sweep-fix order's scope).
- `CONCURRENCY_DRIFT_SENTENCE` now explains markers on tables that no longer show
  them when ranked non-decode — coordinator call whether to scope it per-rank.
- TTFT-ranked concurrent tables carry no queueing caveat (design says concurrent
  TTFT is a queueing measurement; the render doesn't). Minor.

## Still-open questions for Jason (carried)

- **Should a cell that hangs be abandoned rather than retried?** (mlx-optiq on JANG, 600 s.)
- **Ties are rendered as orderings.** Adjacent cells within ~2.5–3% still get rank numbers.
- **Column-entry effect** (~+15% on the first cell in 3 of 5 columns) never re-examined
  under the plateau rule.
- **Warmup at 32k:** the plateau floor of 10 costs ~12–15 minutes per 32k cell.

## What is established — read the documents, not a summary of them

| result | document |
|---|---|
| Dense format axis: `stock4bit > oq4 > oq4e > OptiQ`, 60/60 PASS | `docs/research/2026-09-16-phase5-joined-grid.md` |
| MoE format axis: stock wins by 11–17%, the three specialized formats tie | `docs/research/2026-09-16-moe-format-axis.md` |
| `phys_footprint` counts different page classes per runtime | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| None of the five runtimes batch — N=8 aggregate gains 0.99–1.15× | `docs/research/2026-09-16-concurrency-omlx.md` |
| A sweep is a run *pin*, never a third `--study` axis | `docs/research/2026-09-16-phase6-design.md` |
| All five serve 32k whole; none caches it; Osaurus usage is chars/4 | `docs/research/2026-09-16-prompt-length-context-limits.md` |
| Prompt-length sweep: TTFT by length, vMLX 32k watchdog FAIL, reruns | `docs/research/2026-09-16-prompt-length-sweep.md` |
| Cold/warm KV: only oMLX (17×) and Osaurus (23×) reuse a cache on Qwen3.5 | `docs/research/2026-09-17-cache-state-split.md` |
| v2 candidates, options only, Jason's order: cheap closeouts → JANG → accuracy | `.paul/v2-options-note.md` |

Publishable run dirs (`results/` is gitignored; these exist only on this machine):

- **Dense grid:** `results/grid/20260916T034308Z-format` (mlx-lm), `…T061309Z` (oMLX),
  `…T044750Z` (mlx-optiq), `…T051603Z` (vMLX), `…T054434Z` (Osaurus).
- **MoE grid:** `results/grid-moe/20260916T071532Z-format`, `…T073145Z`, `…T074854Z`,
  `…T080547Z`, `…T082354Z`.
- **Prompt sweep:** all 25 `results/sweep-prompt/*-format` dirs.
- **Cache split:** all 10 `results/sweep-cache/*-format` dirs.
- **Diagnostic, not published:** `results/probe-vmlx-32k-step512/`.
- **Reruns (not joinable with the sweep):** `results/rerun-vmlx-32k/`, `results/rerun-osaurus-128/`.
- **Concurrency:** `results/sweep-conc8/` (four runtimes, N=8), `results/sweep-conc/` (oMLX N=1/2/4/8).
- **Discarded, kept on purpose:** `results/grid/20260916T041544Z-format` (machine not quiet).

## Machine state and runners

- Osaurus **0.25.5**, oMLX 0.6.4, mlx-optiq 0.5.6, vMLX 1.6.59, mlx-lm 0.31.3 in its own venv at
  `~/.local/share/ohyesmlx/mlx-lm-0.31.3` (**must be on `PATH`**; the runners export it).
- The host keeps `modelIdleResidencyPolicy.seconds = 30` (Jason's choice); **every**
  runner now pins 900 for the Osaurus run and restores byte-exact via `cmp`.
  Both sweep runners own their log via `exec > "$OUT/runner.log" 2>&1` — tail it.
- Runners: `scripts/run_grid.sh`, `scripts/run_grid_moe.sh`, `scripts/run_sweep_prompt.sh`,
  `scripts/run_sweep_cache.sh`.
  Probes: `probe_context.py`, `probe_grid_moe.py`, `probe_footprint.py`,
  `probe_concurrency_warmup.py`. No probe writes to `results/`.
- **Delegation:** `.paul/orders/dispatch.sh <role> <order> [log]` with `CC_AGENT_MAX_TURNS=200`;
  the default route is DeepSeek V4.1 Flash. Orders go AFTER the preamble verbatim —
  never before, or every dispatch pays full input price instead of the $0.003/M cache
  read. Between ~01:00 and ~04:00 UTC DeepSeek bills double; use `--route mimo` there.
  Write the log to a file: the worker's report is the log's tail. `explain` is read-only
  and suits diagnosis during a measurement. Workers never run git; the coordinator commits.
- **While a measurement runs:** no pytest, no edits to `ohyesmlx/*.py`, no worker that runs tests.
  Read-only workers are fine.
- This session the coordinator ran workers as background shell tasks and read reports from
  `$COMMANDCODE_SCRATCHPAD/logs/*.log`. Orca tracks the repo (worktree `OhYesMLX`);
  `orca worktree set --worktree active --comment …` surfaces status visibly.
- Use a background job's own exit notification to wait on a long run, not a polling loop.
- Create an output directory before redirecting a runner into it.
