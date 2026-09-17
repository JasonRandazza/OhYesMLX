---
description: "OhYesMLX — session handoff, 2026-09-16 (evening, after the prompt-length sweep)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-16, evening

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading. If this file starts growing per-session
> headings, it has become a log — rewrite it.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

## Where the project is

**Phase 6 (sweeps): 06-01a, 06-01b and 06-01c are done. 06-02 (cold/warm KV split) is next.**
Milestone ~98%.

- `main` is clean and **pushed**; the last code commit is `0898fd7`, and CI (`tests.yml`) is green on it.
- **468 tests** pass, observed by the coordinator with
  `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
- **Nothing is in flight.** Before starting anything, check anyway:
  `lsof -i :1337 -i :8080 -i :8081 -i :8100 -i :8000`,
  `pgrep -fl "^/Applications/osaurus.app"`, `pgrep -fl "cc-agent|ohyesmlx.cli run|run_grid|probe_"`.
- `osaurus mcp` is Jason's and must stay up. **Never sweep by the name `osaurus`.** An Osaurus
  app instance launched by the CLI reappeared once, ~60 s after a probe killed it, and did not
  respawn when killed again; origin unknown. The sweep runner now sweeps before each cell as well
  as after.
- **The Osaurus app was killed by the reruns and has not been reopened.** Jason may reopen it.

## Osaurus is now 0.25.5, and its settings drift

Osaurus updates often (sometimes twice a day). 0.25.5 migrated
`~/.osaurus/config/server.json`: it added `_modelIdleResidencyPolicyVersion: 2` and set
`modelIdleResidencyPolicy.seconds` to **30**. The committed baseline says **900**, so the drift
guard reads one difference and **any Osaurus run refuses to start until it is resolved.**

30 s matters: the harness cools down 30 s between visits, so at 30 the model unloads and reload
time lands inside TTFT. The Osaurus 128 rerun set it to 900 for the run and restored Jason's 30
byte-exact afterwards. Before 06-02, either do the same in the runner, or ask Jason whether 900
should be the host setting and then refresh the baseline. Do not rewrite the baseline to 30
without that conversation.

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

## What is next, in order

1. **Resolve the Osaurus residency drift** (section above) before any Osaurus run.
2. **06-02 — cold/warm KV split.** Jason authorised the Osaurus cache toggle for it; the other
   four clear their cache by restart. Read `docs/research/2026-09-16-phase6-design.md` for the
   design, and use `scripts/run_sweep_prompt.sh` as the model for toggling and restoring.
3. **Update `docs/interfaces.md`** for the short-window fix: `summarize(results, *, measured=None)`
   and `CellResult.lost_visit_reason`, `cold_load_after_lost_visit`, `measured_pin`.
4. Small defects, recorded in STATE.md "Deferred Issues": runner stdout logs (`runner.log`, the
   rerun logs) come out 0 bytes although runs complete; drift markers in a TTFT-ranked sweep are
   decode-rate drift and read as TTFT drift.

## Open questions for Jason

- **vMLX 32k:** test whether a smaller prefill chunk / step setting avoids the GPU watchdog? A
  separate rerun, not a change to the published FAIL.
- **Osaurus residency:** should the host keep 0.25.5's 30 s, or go back to 900?
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

Publishable run dirs (`results/` is gitignored; these exist only on this machine):

- **Dense grid:** `results/grid/20260916T034308Z-format` (mlx-lm), `…T061309Z` (oMLX),
  `…T044750Z` (mlx-optiq), `…T051603Z` (vMLX), `…T054434Z` (Osaurus).
- **MoE grid:** `results/grid-moe/20260916T071532Z-format`, `…T073145Z`, `…T074854Z`,
  `…T080547Z`, `…T082354Z`.
- **Prompt sweep:** all 25 `results/sweep-prompt/*-format` dirs.
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
- Runners: `scripts/run_grid.sh`, `scripts/run_grid_moe.sh`, `scripts/run_sweep_prompt.sh`.
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
