---
description: "OhYesMLX — session handoff, 2026-09-16 (after the overnight session)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-16, morning

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading. If this file starts growing per-session
> headings, it has become a log — rewrite it.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

## Where the project is

**v1's measurement work is done. Phase 6 (sweeps) is in progress, plans 06-01a and 06-01b
complete.** Milestone ~97%.

- `main` is clean and pushed. **413 tests** pass. CI (`.github/workflows/tests.yml`, macOS
  runners) is green at HEAD — **check `gh run list --workflow=tests.yml` rather than trusting
  that line.** It failed on two of the overnight pushes and nobody noticed for hours:
  `test_a_batchs_span_is_shorter_than_the_sum_of_its_requests` slept 20 ms per request, and
  shared runners' ~30 ms thread-pool startup swamped the overlap it was measuring. Now 250 ms.
- **Nothing is in flight**: no workers, no grid, no held ports. Before starting anything, check
  anyway — `lsof -i :1337 -i :8080 -i :8081 -i :8100 -i :8000`,
  `pgrep -fl "^/Applications/osaurus.app"`, and `pgrep -fl "cc-agent|ohyesmlx.cli run|run_grid"`.
  The last one found two **zombie waiter loops** from a previous session's job this morning:
  `until [ $(pgrep -f cc-agent | wc -l) -eq 0 ]` matches its own command line, so it never
  exits. Swept. Write a waiter that polls a sentinel in a log file instead.
- The only process that must stay up is `osaurus mcp` (pid varies). It is Jason's. **Never
  sweep by the name `osaurus`.**

## What is established — read the documents, not a summary of them

| result | document |
|---|---|
| Dense format axis: `stock4bit > oq4 > oq4e > OptiQ`, 60/60 PASS, three unrelated codebases agree | `docs/research/2026-09-16-phase5-joined-grid.md` |
| Runtime axis publishable after per-cell warmup; mlx-lm drift +17.0% → −2.2%; remaining instabilities are ties 0.3–2.5% apart | same, section "The re-measured grid" |
| MoE format axis (LFM2.5-8B-A1B, 32 experts): stock wins by 11–17%, the three specialized formats **tie** — the dense tail ordering does not transfer | `docs/research/2026-09-16-moe-format-axis.md` |
| Stock mlx-lm serves a 32-expert MoE coherently; mlx-optiq *hangs* on JANG rather than refusing | `docs/research/2026-09-16-moe-loadability-probe.md` |
| `phys_footprint` counts different page classes per runtime (Osaurus wired GPU pages, oMLX anonymous) — the file-backed explanation was wrong and is deleted | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| **None of the five runtimes batch** — N=8 aggregate gains 0.99–1.15×; concurrency is pure latency cost | `docs/research/2026-09-16-concurrency-omlx.md` |
| Phase 6 design: a sweep is a run *pin*, never a third `--study` axis | `docs/research/2026-09-16-phase6-design.md` |

The publishable grids — named explicitly, because `results/` holds superseded run dirs too and a
glob would join the wrong ones:

- **Dense:** `results/grid/20260916T034308Z-format` (mlx-lm), `…T061309Z` (oMLX — the quiet
  re-run), `…T044750Z` (mlx-optiq), `…T051603Z` (vMLX), `…T054434Z` (Osaurus).
- **MoE:** `results/grid-moe/20260916T071532Z-format` (mlx-lm), `…T073145Z` (oMLX),
  `…T074854Z` (mlx-optiq), `…T080547Z` (vMLX), `…T082354Z` (Osaurus).
- **Discarded, kept on purpose:** `results/grid/20260916T041544Z-format`. The machine was not
  quiet while it ran. It is named with that reason in the Phase 5 write-up.

`results/` is gitignored. These directories exist only on this machine.

## What is next, in order

1. **06-01c — prompt-length sweep.** 128 / 1k / 4k / 16k / 32k **tokens**, verified against the
   serving tokenizer (`token_counter.TokenCounter`), achieved count recorded beside target. Seed
   the text from `cli.PREFILL_PROMPT`, cut at a token boundary — never repeated filler. A prompt
   past a runtime's context is `—` with the refusal recorded, never `FAIL`, never silently
   truncated. First question to answer per runtime: can its context be raised from its start
   command? Design: `docs/research/2026-09-16-phase6-design.md`.
2. **Build `render_sweep(runs, *, varying, rank)`.** Designed and pinned in `docs/interfaces.md`,
   **not built**. The five-runtime concurrency comparison was done by hand. Every sweep result so
   far is a research comparison, not a tool output.
3. **Drift caveat at N>1.** `measured_drift` reads per-request rates; at concurrency > 1 the
   warmup window closed on aggregate, so positive drift means "per-request rate still moving",
   not "under-warmed". The function is correct; the report's drift note is not yet
   concurrency-aware. Any sweep table must carry that sentence.
4. **06-02 — cold/warm KV split.** Jason **authorised** toggling
   `~/.osaurus/config/server-runtime.json` (`cache.prefix.enabled`, `cache.blockDisk.enabled`)
   on 2026-09-16, provided it is restored from `server-runtime.json.ohyesmlx-backup` and the
   drift guard verified back to **NONE** before anything else runs. The other four clear their
   cache by restart.

## Open questions nobody has answered

- **Column-entry effect.** In the fixed-warmup grid the first cell measured in a column drifted
  high in 3 of 5 columns (~+15%). Mentioned in the Phase 5 write-up, **never re-examined** under
  the plateau rule. Cheap to check: read the first cell's drift in each of the dense columns
  above.
- **Should a cell that hangs be abandoned rather than retried on the next visit?** mlx-optiq on
  JANG accepted a request and never answered; only the 600 s request timeout ended it. A
  measurement-design decision — Jason's, not a worker's.
- **Ties are rendered as orderings.** Adjacent runtime-axis cells within ~2.5% swap under a
  late-window re-rank. The renderer still prints rank numbers for them.

## Machine state

- **238 GiB free.** The 21.9 GB of LFM2.5-8B-A1B artifacts are in the HF cache.
- Installed: Osaurus 0.25.4, oMLX 0.6.4, mlx-optiq 0.5.6, vMLX 1.6.59, and mlx-lm 0.31.3 in
  its own venv at `~/.local/share/ohyesmlx/mlx-lm-0.31.3`.
- Osaurus settings drift reads **NONE** against the recorded baseline; its KV cache is **on**.
- Wall clock under the current pins (`warmup` plateau rule, `measured 9`): dense grid **2 h
  28 m**, MoE grid **1 h 24 m**, one N=8 column **~45 m**. Budget for it — the old 67-minute
  figure is gone.
- `docs/runtimes/osaurus.md` was written against 0.25.3 and is stale in unknown ways.

## Runners and probes

- `scripts/run_grid.sh` (dense), `scripts/run_grid_moe.sh` (MoE). Both export the mlx-lm venv
  onto `PATH` — **not optional**, a probe launched without it reported mlx-lm failing on every
  format — and both sweep stale Osaurus app instances by full executable path between columns.
- Probes in `scripts/`: `probe_grid_moe.py` (loadability), `probe_footprint.py` (memory page
  classes), `probe_concurrency_warmup.py` (which series a concurrent warmup settles on). None of
  them writes to `results/` or produces a published figure.
- **Create an output directory before launching a runner into it.** The first concurrency sweep
  lost its N=1 run to a redirect into a directory that did not exist yet.
