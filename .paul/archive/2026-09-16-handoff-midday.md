---
description: "OhYesMLX — session handoff, 2026-09-16 (midday, before the prompt-length sweep)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-16, midday

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading. If this file starts growing per-session
> headings, it has become a log — rewrite it.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

## Where the project is

**Phase 6 (sweeps) in progress. 06-01a and 06-01b are done; 06-01c's code is built, reviewed,
and probed live, and its sweep has not been run.** Milestone ~97%.

- `main` is clean. **Three local commits are NOT pushed**: `9fd4d68` (the prompt-length pin),
  `446d182` (probe results), `d458c1b` (doc wording), plus this handoff's commit. Push when
  Jason says so, then check CI: `gh run list --workflow=tests.yml`.
- **428 tests** pass, observed by the coordinator with
  `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
- **Nothing is in flight.** Jason killed the stray Osaurus app (pid 24495, launched by CLI
  mid-session, origin unknown — possibly his `osaurus mcp`, possibly the worker). Before
  starting anything, check anyway: `lsof -i :1337 -i :8080 -i :8081 -i :8100 -i :8000`,
  `pgrep -fl "^/Applications/osaurus.app"`, `pgrep -fl "cc-agent|ohyesmlx.cli run|run_grid|probe_"`.
- `osaurus mcp` is Jason's and must stay up. **Never sweep by the name `osaurus`.**
- Osaurus settings drift reads **NONE** against the committed baseline; its caches are **on**.

## What 06-01c built this session

All of it is in `docs/interfaces.md`, section "Phase 6 plan 06-01c — the prompt-length pin",
and `docs/research/2026-09-16-prompt-length-context-limits.md`. In short:

- `ohyesmlx run ... --prompt-tokens N` measures **one** workload, `prefill` (cap 64), whose
  prompt is `cli.sized_prompt(counter, N)`: a head, a whitespace-boundary cut of the MS-7
  excerpt followed by the frozen fixture `ohyesmlx/longtext.md`, and a tail asking what the
  document is about. Achieved on Qwen3.5-4B: **128 / 1024 / 4096 / 16384 / 32765**.
- The header records `"prompt_tokens": {"target": N, "achieved": M}` (or `None`).
- Join guard 1 (`report.PIN_FIELDS`) now compares `concurrency` and `prompt_tokens`; an absent
  `concurrency` reads as `1`. **This closed a real defect**: 06-01b never added `concurrency`,
  so `ohyesmlx grid` would have joined an N=8 run into the N=1 grid.
- OptiQ is started with `--max-context off`. An integer cap rotates the KV window rather than
  refusing; it was a no-op on Qwen3.5 and LFM2, so no published number moves.

**Measured live** (`scripts/probe_context.py <runtime> 16384 32768`, oQ4 cell): mlx-lm, oMLX,
OptiQ and vMLX all serve 16k and 32k **whole** (`prompt_tokens` = sent + a constant 5–12
template tokens), coherent, and **none prefix-caches a repeated prompt** (second TTFT within
5%; oMLX's 16k pair −10.5% is the one to watch). TTFT ≈ 30 s at 16k, ≈ 70 s at 32k.

**Not built, deliberately:** a `REFUSED` status. The design says a context refusal is `—`,
never `FAIL`. No runtime has refused, so it is built only if Osaurus (or the sweep) produces
one. Until then a 400/413 reports as `FAIL` and a sweep containing one is not published.

## What is next, in order

1. **Probe Osaurus.** Its caches must be off, or the repeat TTFT is a lookup. Do the toggle by
   hand exactly as `osaurus_cache off` / `on` in `scripts/run_sweep_prompt.sh` does it (copy
   the config byte-exact, flip `cache.prefix.enabled` and `cache.blockDisk.enabled`,
   `osaurus_settings.write_baseline()`, probe, copy back,
   `git checkout -- config/osaurus-settings-baseline.json`, **verify drift NONE**). Then run
   `scripts/probe_context.py osaurus 16384 32768`. Unknowns: whether it honours
   `chat.json contextLength 128000` or `cache.defaultMaxKVSize 65536`, and what
   `cache.longPromptMultiplier 2` does. If it refuses or truncates, build `REFUSED` first.
   Record the result in the research doc's "Measured" section.
2. **Run the sweep:** `scripts/run_sweep_prompt.sh` → `results/sweep-prompt/`. One run per
   (runtime, length), oq4 cell, lengths alternating ascending/descending between runtimes,
   Osaurus toggled off and restored, and it exits non-zero unless drift reads NONE at the end.
   **Budget 4–5 hours**: a 32k cell is ≥20 requests at ~70 s each under the plateau rule. The
   runner has **never been executed** — read it once before launching, and launch it in the
   background with a waiter that polls for `SWEEPDONE` or a non-zero exit in its output, not
   a `pgrep` loop (that one matches itself and never exits). **Nothing else runs on the
   machine while it does** — no git, no pytest, no edits to `ohyesmlx/*.py`.
3. **Check every sweep cell for a cache hit**: warmup request 1 TTFT against the measured
   median. A collapse after request 1 is a cache lookup, whatever the runtime.
4. **Build `render_sweep(runs, *, varying, rank)`** (pinned in `docs/interfaces.md`, not built).
   For `varying="prompt_tokens"` the workloads' `messages` necessarily differ between runs, so
   the workload half of guard 1 must allow that field to differ *only* for this pin. The
   five-runtime concurrency comparison was done by hand; it should render through this too.
5. **Drift caveat at N>1** — `measured_drift` reads per-request rates; at concurrency > 1
   positive drift means "per-request rate still moving", not "under-warmed". Any concurrency
   sweep table must carry that sentence.
6. **06-02 — cold/warm KV split.** Jason authorised the Osaurus cache toggle for it; the other
   four clear their cache by restart.

## Open questions nobody has answered

- **Column-entry effect.** In the fixed-warmup grid the first cell measured in a column drifted
  high in 3 of 5 columns (~+15%). Never re-examined under the plateau rule. Cheap: read the
  first cell's drift in each dense column below.
- **Should a cell that hangs be abandoned rather than retried?** mlx-optiq on JANG accepted a
  request and never answered until the 600 s timeout. Jason's decision, not a worker's.
- **Ties are rendered as orderings.** Adjacent runtime-axis cells within ~2.5% swap under a
  late-window re-rank; the renderer still prints rank numbers for them.
- **Warmup at 32k.** The plateau rule's floor of 10 costs ~12 minutes of warmup per 32k cell.
  It is the pinned rule and the sweep uses it; whether long-prompt cells need that floor is
  unexamined.

## What is established — read the documents, not a summary of them

| result | document |
|---|---|
| Dense format axis: `stock4bit > oq4 > oq4e > OptiQ`, 60/60 PASS | `docs/research/2026-09-16-phase5-joined-grid.md` |
| Runtime axis publishable after per-cell warmup; remaining instabilities are ties 0.3–2.5% apart | same, "The re-measured grid" |
| MoE format axis: stock wins by 11–17%, the three specialized formats tie | `docs/research/2026-09-16-moe-format-axis.md` |
| `phys_footprint` counts different page classes per runtime | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| **None of the five runtimes batch** — N=8 aggregate gains 0.99–1.15× | `docs/research/2026-09-16-concurrency-omlx.md` |
| A sweep is a run *pin*, never a third `--study` axis | `docs/research/2026-09-16-phase6-design.md` |
| Context limits per runtime, from source; four serve 32k whole, none caches it | `docs/research/2026-09-16-prompt-length-context-limits.md` |

Publishable grids — named explicitly, because `results/` holds superseded run dirs too:

- **Dense:** `results/grid/20260916T034308Z-format` (mlx-lm), `…T061309Z` (oMLX), `…T044750Z`
  (mlx-optiq), `…T051603Z` (vMLX), `…T054434Z` (Osaurus).
- **MoE:** `results/grid-moe/20260916T071532Z-format` (mlx-lm), `…T073145Z` (oMLX),
  `…T074854Z` (mlx-optiq), `…T080547Z` (vMLX), `…T082354Z` (Osaurus).
- **Discarded, kept on purpose:** `results/grid/20260916T041544Z-format` (machine not quiet).
- **Concurrency N=8:** `results/sweep-conc8/` (four runtimes) and `results/sweep-conc/` (oMLX
  N=1/2/4/8).

`results/` is gitignored; these exist only on this machine.

## Machine state and runners

- 238 GiB free. Osaurus 0.25.4, oMLX 0.6.4, mlx-optiq 0.5.6, vMLX 1.6.59, mlx-lm 0.31.3 in its
  own venv at `~/.local/share/ohyesmlx/mlx-lm-0.31.3` (**must be on `PATH`**; the runners
  export it).
- `~/.osaurus/config/server-runtime.json.ohyesmlx-backup` matches the live config in content
  but **not in bytes** — restore from a byte-exact copy taken at toggle time, as the sweep
  runner does, not from that backup.
- Runners: `scripts/run_grid.sh`, `scripts/run_grid_moe.sh`, `scripts/run_sweep_prompt.sh`
  (new, unrun). Probes: `probe_context.py` (new), `probe_grid_moe.py`, `probe_footprint.py`,
  `probe_concurrency_warmup.py`. No probe writes to `results/`.
- Delegation: `.paul/orders/dispatch.sh implement <order>` with `CC_AGENT_MAX_TURNS=200`. The
  last order, `.paul/orders/prompt-length-pin.md`, is a good template. Its worker was reliable
  and flagged the provenance-rendering gap itself.
- **Create an output directory before redirecting a runner into it.**
