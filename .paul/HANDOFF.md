---
description: "OhYesMLX — session handoff, 2026-09-16 (late night, Phase 6 complete)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-16, late night

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading. If this file starts growing per-session
> headings, it has become a log — rewrite it.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

## Where the project is

**Phase 6 (sweeps) is complete: 06-01a/b/c and 06-02 are done.** Phase 7 is the only remaining
milestone content — read `.paul/ROADMAP.md` for its scope before planning. Milestone ~99%.

- `main` is clean and **pushed**; CI (`tests.yml`) was green at `0898fd7` — check the latest run with `gh run list --workflow=tests.yml`.
- **487 tests** pass, observed by the coordinator with
  `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
- **Nothing is in flight.** Before starting anything, check anyway:
  `lsof -i :1337 -i :8080 -i :8081 -i :8100 -i :8000`,
  `pgrep -fl "^/Applications/osaurus.app"`, `pgrep -fl "cc-agent|ohyesmlx.cli run|run_grid|probe_"`.
- `osaurus mcp` is Jason's and must stay up. **Never sweep by the name `osaurus`.** An Osaurus
  app instance launched by the CLI reappeared once, ~60 s after a probe killed it, and did not
  respawn when killed again; origin unknown. The sweep runner now sweeps before each cell as well
  as after.
- **The Osaurus app was killed by the runs and has not been reopened.** Jason may reopen it.

## Osaurus is now 0.25.5, and its settings drift

Osaurus updates often (sometimes twice a day). 0.25.5 migrated
`~/.osaurus/config/server.json`: it added `_modelIdleResidencyPolicyVersion: 2` and set
`modelIdleResidencyPolicy.seconds` to **30**. The committed baseline says **900**, so the drift
guard reads one difference, and **a runner that does not pin 900 for the run cannot start Osaurus.**

30 s matters: the harness cools down 30 s between visits, so at 30 the model unloads and reload
time lands inside TTFT. **Jason's decision (2026-09-16): the host keeps 30; each Osaurus run pins
900 and restores byte-exact.** `scripts/run_sweep_cache.sh` does this and verifies with `cmp`
(drift NONE cannot be the check while the host differs from the committed baseline). The older
runners (`run_grid.sh`, `run_grid_moe.sh`, `run_sweep_prompt.sh`) do NOT pin it yet and will
refuse to start Osaurus on drift — port the toggle before re-running any of them.

Its prefix and block-disk caches are **on** (Jason's setting), restored after every toggle.

## What this session established

Full write-up: `docs/research/2026-09-16-prompt-length-sweep.md` (includes a "Reruns" section).
Context-limit probes, now for all five runtimes: `docs/research/2026-09-16-prompt-length-context-limits.md`.

**The sweep** — `results/sweep-prompt/`, 25 run dirs, oq4 cell, 128/1024/4096/16384/32768,
Osaurus 0.25.4 with caches off. Wall time 6 h 15 min (32k cells 38–49 min each; the handoff's
4–5 h budget was low). Rendered:

```
ohyesmlx sweep --varying prompt_tokens --rank ttft_p50_s results/sweep-prompt/*-format
```

stored as `results/sweep-prompt/sweep-ttft.md` (rendered before the short-window fix; re-render
to get the `(n=4 of 9)` marker). TTFT p50 in seconds:

| runtime | 128 | 1k | 4k | 16k | 32k |
|---|---|---|---|---|---|
| mlx-lm | 0.476 | 2.021 | 7.835 | 30.202 | 76.981 |
| oMLX | 0.728 | 2.586 | 8.141 | 36.848 | 85.573 |
| OptiQ | 0.549 | 2.422 | 9.026 | 42.418 | 91.101 |
| vMLX | 0.404 | 2.171 | 9.020 | 41.203 | FAIL |
| Osaurus | 0.592 (n=4 of 9) | 2.246 | 8.266 | 37.729 | 80.335 |

- mlx-lm leads from 1k up (16k by 22%); the doc names the ties within 3%.
- **No cell served a repeat from a cache**: min TTFT / measured median ≥ 0.68 everywhere.
- **vMLX 32k is FAIL, published as FAIL (Jason's decision).** Streams close with
  "chat stream produced no content", no HTTP error. The vMLX server log shows the cause:
  `[METAL] Command buffer execution failed: Impacting Interactivity
  (kIOGPUCommandBufferCallbackErrorImpactingInteractivity)` during prefill — the macOS GPU
  watchdog. 28/49 failed in the sweep, **43/49 on a separate rerun** (`results/rerun-vmlx-32k/`).
  The context probe earlier served 32k twice; the failure is intermittent-to-dominant, not a
  refusal. Why the other four avoid it is **unverified**.
- **Osaurus 128 measured 4 of 9.** Visit 1's `runtime.start()` raised; visit 2 measured its
  quota of 4; `_set_status` rewrote the row to PASS and erased the reason. Rerun on 0.25.5
  (`results/rerun-osaurus-128/`): 9 of 9, 0 failures, p50 0.640 s. It cannot join the 0.25.4
  sweep table.
- **Osaurus's `usage.prompt_tokens` is chars/4, not tokens** (51,404 chars → 12,851 exactly).
  `prefill_tps` from usage understates Osaurus ~20% on this text and is not comparable across
  runtimes. The published grids rank on `decode_tps` and are unaffected. Rank prompt sweeps on
  TTFT.

**06-02, the cold/warm KV split** — `results/sweep-cache/`, 10 run dirs, oq4 at 4,096 tokens, each
runtime `--cache-state off` then `on`, Osaurus 0.25.5. Write-up:
`docs/research/2026-09-17-cache-state-split.md`. TTFT p50 off → on: mlx-lm 7.825 → 7.845, oMLX
8.487 → **0.487 (17.4×)**, OptiQ 9.813 → 9.983, vMLX 8.283 → 8.260, Osaurus 9.401 → **0.404
(23.3×)**. All PASS, 303/303 requests returned.

- **mlx-lm and OptiQ cannot serve a hit on Qwen3.5**: entries are stored keyed by prompt + output,
  so a repeat is a strict prefix, and serving a longer entry needs a trimmable cache; the hybrid
  model's `ArraysCache` is not (`mlx_lm/models/cache.py:146-147, 88-92`).
- **vMLX declines itself**: `mllm_scheduler.py:758-770` disables the prefix cache for a hybrid
  model when paged and block-disk caches are off ("no RAM fallback"), and the harness keeps block
  disk off in both states by the single-variable rule.
- Whether a non-hybrid model turns those three over is untested.

**vMLX 32k with `--prefill-step-size 512`** (`results/probe-vmlx-32k-step512/`, diagnostic):
42 of 49 still die. The hybrid prefill path logs `path=one-shot seq_len=32775` regardless of the
flag, so the FAIL is a property of vMLX 1.6.59 on Qwen3.5 at 32k. Recorded in the sweep doc.

**Code built and fixed this session** (all by Command Code workers, reviewed and committed by the
coordinator; orders in `.paul/orders/`):

- `report.render_sweep(runs, *, varying, rank)` and `ohyesmlx sweep` — `render-sweep.md`.
  Guard 1 reused; `messages` relaxed only for `prompt_tokens`; drift caveat sentence printed at
  concurrency > 1.
- `_aggregate_tps` used summed per-request clocks, so a concurrent cell read ~N× too slow (oMLX
  chat 66/42/25/14 instead of a flat 66). Now uses `batch_spans` — `aggregate-tps-spans.md`. The
  five-runtime concurrency comparison can now render through `ohyesmlx sweep --varying
  concurrency --rank aggregate_tps`.
- The CI-flaky concurrent warmup test uses a fake monotonic clock — `flaky-concurrent-warmup-test.md`.
- A lost visit keeps its reason on a PASS row; a row short of its measured pin prints
  `(n=K of N)` and a note; a cold load from a later start is noted — `short-window-note.md`,
  diagnosis in `short-measured-window.md`. Forward-looking: existing records carry no reason.
  Only one row on disk is short (Osaurus 128 above); every published grid renders byte-identical.
- `ohyesmlx run --cache-state off|on` (header pin; absent = None, never "off") with per-runtime
  flags, `render_sweep(varying="cache_state")`, and `scripts/run_sweep_cache.sh` —
  `cache-state-pin.md`. `docs/interfaces.md` is current, including the short-window fix.

## What is next, in order

1. **Phase 7.** Read `.paul/ROADMAP.md` and `.paul/STATE.md` for its scope; plan it with Jason.
2. **Port the Osaurus residency pin** (900 for the run, byte-exact restore, `cmp` check) into
   `run_grid.sh`, `run_grid_moe.sh` and `run_sweep_prompt.sh` before any of them runs Osaurus again.
3. Small defects in STATE.md "Deferred Issues": runner stdout logs come out 0 bytes (seen again in
   `results/sweep-cache/runner.log`); drift markers in a TTFT-ranked sweep are decode drift.
4. Optional: repeat the cache split on a non-hybrid model to see whether mlx-lm, OptiQ and vMLX hit.

## Open questions for Jason

- **Is a warm-cache TTFT a publishable prefill number, or a lookup number** that belongs in its own
  column? (oMLX 0.49 s and Osaurus 0.40 s at 4k are lookups.)
- **Should a cell that hangs be abandoned rather than retried?** (mlx-optiq on JANG, 600 s.)
- **Ties are rendered as orderings.** Adjacent cells within ~2.5–3% still get rank numbers.
- **Column-entry effect** (first cell in a column drifted ~+15% in 3 of 5 fixed-warmup columns)
  never re-examined under the plateau rule.
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
- `~/.osaurus/config/server-runtime.json.ohyesmlx-backup` matches the live config in content but
  not in bytes — restore from a byte-exact copy taken at toggle time. `…sweep-prompt-orig` and
  `…probe-orig` are stale copies from this session; delete them only after checking they are not
  needed.
- Runners: `scripts/run_grid.sh`, `scripts/run_grid_moe.sh`, `scripts/run_sweep_prompt.sh`,
  `scripts/run_sweep_cache.sh`.
  Probes: `probe_context.py`, `probe_grid_moe.py`, `probe_footprint.py`,
  `probe_concurrency_warmup.py`. No probe writes to `results/`.
- **Delegation:** `.paul/orders/dispatch.sh <role> <order> [log]` with `CC_AGENT_MAX_TURNS=200`;
  the default route is DeepSeek V4.1 Flash (`cc-agent implement --check-only x` confirms). Write
  the log to a file: the worker's report is the log's tail. `explain` is read-only and suits
  diagnosis during a measurement. Workers never run git; the coordinator commits and pushes.
- **While a measurement runs:** no pytest, no edits to `ohyesmlx/*.py`, no worker that runs tests.
  Read-only workers are fine.
- Use a background job's own exit notification to wait on a long run, not a polling loop.
- Create an output directory before redirecting a runner into it.
