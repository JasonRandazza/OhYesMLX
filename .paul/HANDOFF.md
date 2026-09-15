---
description: "OhYesMLX — session handoff, 2026-09-15 (evening)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-15, evening

Read this, then `.paul/STATE.md`, then `AGENTS.md`. The previous handoff (morning) is
superseded; everything still true from it is restated here.

## Where the project is

**325 tests pass.** Phases 1, 2, 2.1 and 4 are complete. Phase 3 is 90% done: the grid ran
end to end, and the re-run is the remaining work.

The repo is clean and pushed through `9f751ff`. Nothing is in flight — no workers, no servers,
no held ports. Osaurus's config is back in its normal state (cache on) and its 9 GB KV cache
was never touched.

## The one big shift in direction

**v1's milestone is now the sparse format × runtime grid, not the format axis alone.** The
reason is worth understanding before changing anything:

A grid contains both single-variable studies as its slices. A **row** is one format across
runtimes — the runtime axis. A **column** is one runtime across formats — the format axis. The
**best cell** answers "what should I actually run", which varies both and is therefore a
recommendation, never an attribution. The founding rule was never "don't measure the diagonal";
it was "don't attribute a difference when two variables moved". The grid honours that exactly.

**The grid needs no new CLI mode to be collected.** `--study format` holds the runtime constant,
so each column is already a legal single-variable run. Five runs, joined. Phase 5 is a report
that joins five run directories, not a new measurement mode. `scripts/gridspec.sh` and
`scripts/run_grid.sh` do this.

## The grid, measured

Qwen3.5-4B, five formats (15.6 GB), five runtimes. **20 of 25 cells live.**

| format | mlx-lm | oMLX | mlx-optiq | vMLX | Osaurus |
|---|---|---|---|---|---|
| stock-4bit | ✓ | ✓ | ✓ | ✓ | ✗ not registered |
| oQ4 | ✓ | ✓ | ✓ | ✓ | ✓ |
| oQ4e | ✓ | ✓ | ✓ | ✓ | ✓ |
| OptiQ | ✓ | ✓ | ✓ | ✗ vision map | ✓ |
| JANG_4S | ✗ shape | ✗ shape | ✗ shape | ✓ | ✓ |

Both holes are explained, not empty: see `docs/research/2026-09-15-grid-loadability-probe.md`.

**The format-axis result, replicated across two independent runtimes** (decode tok/s):
stock-4bit and oQ4 are neck-and-neck at the top, oQ4e next, **OptiQ consistently slowest** —
and OptiQ is also the largest on disk (4.04 GB vs 3.06). That ordering held in oMLX and
mlx-optiq, which share no code. This is the unoccupied ground the project set out to claim.

## The three things that matter most

**1. Every defect found today was a measurement-validity bug, not a crash.** Six of them. The
static suite was green at 199 tests this morning and blind to every one, because none of them
raised. This is the project's own thesis turned on itself:

| | the column said | the column measured |
|---|---|---|
| mlx-lm on a 256-expert MoE | fastest healthy row | token salad |
| oMLX decode rate | 1,532,954,517 tok/s | a zero-length window |
| oMLX TTFT | 5.499 s first-token latency | time-to-completion, wrong channel |
| oMLX cold load | fastest loader | time until listening |
| Osaurus peak memory | 4.7 MB | a dying launcher process |
| Osaurus prefill | 4301 tok/s | a KV cache hit |

Read a number that looks plausible and check it anyway. That is the whole method.

**2. A negative capability claim needs source or settings evidence.** The rule is in
`AGENTS.md`. It was bought three times today: "oMLX cannot stream" (it streams in the
reasoning channel), predicted grid refusals (every one wrong), and "osaurus_settings.py
doesn't check the cache keys" (it already watched both, and caught my own change by name).
`--help` documents a command line, not a runtime. `docs/runtimes/*.md` are ~3,900 lines of
per-runtime capability reference written from shipped source — read them before claiming a
runtime cannot do something.

**3. Content versus reasoning is the recurring trap.** Four separate defects came from it, and
one more while writing the *probe* meant to detect it. Runtimes disagree completely: mlx-lm and
vMLX answer **only** in the reasoning channel, oMLX **mirrors** reasoning into content, optiq
answers directly via its `:no-think` id. `docs/interfaces.md` pins which channel is the output
stream and why.

## What to do next

**Task #3 — Osaurus `peak_mb` samples the launcher.** It publishes 4.7 MB from 1 sample against
2,699–4,172 MB and 11–14 samples elsewhere. `osaurus serve` hands off to the app and exits.
Resolve the real pid from the port, as the stop path now does.

**Task #6 — re-run the full grid.** Two columns (mlx-lm, vMLX) produced no figures before
`9f751ff`, which is fixed but unverified against a live server. **Open question the first
post-fix row answers:** do those runtimes send `usage.completion_tokens`? Without it,
reasoning-only rows stop failing on "no content-delta timing" and start failing on
`token_source='none'`.

**Task #4 — surface `runtime_version` mismatches in the join.** It is recorded in every result
and read by nothing. Osaurus updated 0.25.3 → 0.25.4 mid-session and a cache comparison would
have silently spanned both versions. Jason caught it, not the harness.

**Deferred-load threshold over-fires.** `DEFERRED_LOAD_EXCESS_S = 1.0` flags 15 of 60 recorded
rows; the extras are eager loaders on the short `prefill` workload where a 3.6–5.0 s first
request sits on a ~1.0 s median. No single threshold separates them. The fix is to compare
within one workload's own requests, or against an eager-loader baseline — not a bigger number.

## Osaurus needs care

- Its KV cache **cannot be disabled from any command line** — only `~/.osaurus/config/server-runtime.json`,
  keys `cache.prefix.enabled` and `cache.blockDisk.enabled`. With it on, prefill is **8.3×**
  faster because it is a cache lookup, not prefill.
- Changing those keys trips the settings drift guard, which refuses to run and names them. That
  is correct. **Re-record the baseline** with `osaurus_settings.write_baseline()` after changing
  them, and restore both afterwards.
- Backups: `~/.osaurus/config/server-runtime.json.ohyesmlx-backup`,
  `config/osaurus-settings-baseline.json.pre-cache-disable`. The baseline on disk currently
  records cache **on**.
- `osaurus stop` frees the port and **leaves the app process alive**. Fixed in `4426238`, but
  sweep processes as well as ports after every live run. Never sweep by name: `osaurus mcp` is
  a long-running user process.
- Osaurus discovers the Hugging Face cache on its own, and names models after the repo,
  lowercased — an HF-cache path ending in a commit hash never resolves.

## Machine state

- **312 GiB free.** The disk constraint is gone. Jason cleared JANG-era models and deleted the
  Time Machine local snapshots that were pinning ~250 GiB of freed blocks.
- `mlx-lm 0.31.3` now lives at **`~/.local/share/ohyesmlx/mlx-lm-0.31.3`**, not `/tmp`. It is
  the control arm of every runtime-axis comparison; the old `/tmp/mlxspike` would not have
  survived a reboot.
- Installed: Osaurus **0.25.4** (updated mid-session), oMLX 0.6.4, mlx-optiq 0.5.6, vMLX 1.6.59
  (`vmlx` wrappers in `~/.local/bin` — symlinks break, the bundled console scripts resolve
  python3 relative to their own directory).
- `docs/runtimes/osaurus.md` was written against 0.25.3 and is stale in unknown ways.

## How this project is run

- **PAUL is the only spine.** `.paul/STATE.md` is the single state store. If a second appears,
  delete it.
- **Delegate to Command Code.** Orders live in `.paul/orders/`, dispatched by
  `.paul/orders/dispatch.sh <role> <order-file>`, which prepends `PREAMBLE.md` **byte-identically**
  so it lands as a DeepSeek prompt-cache prefix at $0.003/M against $0.15/M fresh. Order text
  goes strictly after it. `CC_AGENT_MAX_TURNS=200` raises the turn cap (default is now 100).
- **Pin interfaces in `docs/interfaces.md` before fanning out.** Shapes are the coupling, not
  files. This is what let concurrent workers compose all day.
- **Opus reviews every diff and re-runs the suite personally.** Worker prose is not evidence.
  Verify with `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
  (needs `tokenizers` installed; there is no pytest in the repo venv).
- **Workers block well — let them.** Several BLOCKED reports this session found genuine
  contradictions in orders, and several flagged consequences the order had not anticipated.
  Treat a BLOCKED as a finding.
- The collateral-deletion guard **was fixed mid-session and is now trustworthy.** It fired
  three false positives before the fix and two true positives after. Read the next warning.
