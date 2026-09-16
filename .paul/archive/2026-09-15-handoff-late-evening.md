---
description: "OhYesMLX — ARCHIVED handoff, 2026-09-15 late evening"
type: Archive
about: "OhYesMLX"
---

> **This is history. It is NOT required reading.**
>
> Archived 2026-09-16 when the overnight session rewrote `.paul/HANDOFF.md`. It describes the
> *fixed-warmup* grid (`warmup=3`, `measured=5`), whose runtime axis was later shown to be
> measuring warmup speed rather than serving speed and was re-measured under the plateau rule.
> Its numbers are superseded by `docs/research/2026-09-16-phase5-joined-grid.md`, and its "next
> build" (Phase 5), "unpushed commits", "open questions" and "unfixed findings" are all closed.
>
> **Where this disagrees with `AGENTS.md`, `.paul/STATE.md`, or the current `.paul/HANDOFF.md`,
> those win.** Kept because the reasoning in it produced plan 05-02, not because any of it is
> current.

---
description: "OhYesMLX — session handoff, 2026-09-15 (late evening)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-15, late evening

Read this, then `.paul/STATE.md`, then `AGENTS.md`. The previous handoff (evening) is
superseded; everything still true from it is restated here.

## Where the project is

**Phase 3 is complete.** The full grid re-ran end to end: **60 of 60 cells PASS** across five
columns, and **353 tests** pass. Phases 1, 2, 2.1, 3 and 4 are done. Phase 5 — the report that
joins the five run directories — is the next build.

**Four commits are unpushed.** `origin/main` is at `3d37c48`; local `main` carries `7945067`,
`5d72d08`, `a6e9cc2` and the drift work. Push is the first thing the next session should do.

Nothing is in flight: no workers, no servers, no held ports. Osaurus settings drift reads
`NONE` against the recorded baseline, cache still on. The only process left standing is
`osaurus mcp` (pid varies) — that is Jason's long-running process and **must not be swept**.

## What the re-run answered

**The open question is closed.** mlx-lm and vMLX both send `usage.completion_tokens` —
`token_source = usage`, 5/5 observations, on every row. The feared failure mode (rows trading
a "no content-delta timing" failure for `token_source='none'`) never materialised. All 24 rows
from those two runtimes, which failed entirely before `9f751ff`, now PASS.

**The format ordering replicated across all five runtimes, not the two the last handoff
claimed.** Decode tok/s, `workload=decode`:

| format | mlx-lm | oMLX | mlx-optiq | vMLX | Osaurus |
|---|---|---|---|---|---|
| stock-4bit | 66.4 | 75.8 | 77.4 | 74.7 | — |
| oQ4 | 62.6 | 75.4 | 75.6 | 72.7 | 66.7 |
| oQ4e | 61.6 | 67.9 | 69.8 | 65.9 | 64.6 |
| OptiQ | 59.7 | 65.0 | 66.5 | — | 63.6 |
| JANG_4S | — | — | — | 78.0 | 69.4 |

`stock4bit > oQ4 > oQ4e > OptiQ` holds identically in mlx-lm, oMLX and mlx-optiq — three
codebases that share nothing. vMLX and Osaurus each lack one of the end formats, but every
pairwise comparison they can make agrees. **Zero inversions in five columns.**

**OptiQ is slower and larger.** Last in every column that carries it, and 4.04 GB on disk
against stock-4bit's 3.06 GB.

**JANG_4S is fastest in both runtimes that can load it** — 78.0 on vMLX (beating stock-4bit's
74.7) and 69.4 on Osaurus (beating oQ4's 66.7). It still cannot be a format-axis row, because
no runtime loads it alongside the others. Per the Phase 3 decision this is the legal reading:
two independent runtimes, format held constant, same verdict.

**One caveat on the headline.** "stock-4bit and oQ4 neck-and-neck" is true in oMLX (75.8 v
75.4) and mlx-optiq (77.4 v 75.6), both within ~2%. In mlx-lm the gap is 66.4 v 62.6, about 6%.
mlx-lm is the drift-contaminated column (below), so read that 6% as drift rather than format —
but it is the one place mlx-lm disagrees with its peers, and it should be re-checked once the
warmup question is settled.

## The seventh measurement-validity defect: drift

`measure.measured_drift()` was computed into every result row and **read by nothing** — the same
shape as `runtime_version` before `7945067`. A cell that moved 28% across its own measurement
window rendered identically to one that moved 0.5%.

Measured across all 60 cells:

| column | median | range | rows over 5% |
|---|---|---|---|
| mlx-lm | **+17.0%** | −1.3% .. +28.4% | **11 of 12** |
| oMLX | +2.6% | −0.2% .. +14.9% | 1 of 12 |
| mlx-optiq | −0.0% | −1.7% .. +14.9% | 2 of 12 |
| vMLX | +0.5% | −3.0% .. +4.6% | 0 of 12 |
| Osaurus | +1.0% | −5.7% .. +16.9% | 4 of 12 |

Every large value is **positive** — cells getting *faster* across their window, which is
insufficient warmup, not the thermal slowdown the original docstring reasoned about.

Why it matters on the format axis specifically: in the mlx-lm column the runtime is held
constant and drift still ranges −1.3% to +28.4% **between formats**. That is not a common-mode
offset a reader can subtract out; it lands differently on each format and contaminates exactly
the ordering that column exists to produce.

**Now shipped** (`report.py`): a signed `drift %` column beside `decode tok/s`, a `drift_pct`
card line, a footnote, and `DRIFT_ANNOTATION_PCT = 5.0` which **annotates and never fails** —
a cell that was still moving is ranked with the rest, because the row saying the window was too
short is the row that must not be thrown away. Verified against all 60 real rows: 18 annotate,
11 of them mlx-lm's.

## Two open questions this bought

**1. Warmup is a per-runtime property and the harness treats it as universal.** mlx-lm needs a
longer budget; the other four settle almost immediately. Do not fix this by raising the global
warmup — that would pay mlx-lm's cost on four runtimes that do not need it. This is a
measurement-design decision, not a worker's.

**2. A column-entry effect.** The first cell measured in a column drifts high in 3 of 5 columns
— oMLX +14.9%, mlx-optiq +14.9%, Osaurus +15.4%. Three near-identical numbers across runtimes
that share no code point at the machine or the harness, not the runtime. vMLX is the exception
at +4.6%, and it is also by far the slowest loader (`cold_load_s` 6.1–8.1s against 1.4–3.8s
elsewhere), so its process may simply arrive warm. **That is a hypothesis, not a finding.**
mlx-lm cannot distinguish the two effects because it drifts on every row.

## Smaller findings, unfixed

- **mlx-optiq reports `runtime_version` as `"mlx-optiq, version 0.5.6"`**, not a bare `0.5.6`.
  Uniform within the column so the new join guard will not misfire, but that guard compares this
  exact string, and a runtime that rephrases its `--version` output would read as a version
  change. Normalise when the guard is next touched.
- **`measured_drift` with `measured=5`** compares a median of two rates against a median of two
  and discards the middle sample. The direction is trustworthy (unanimous across 60 rows); a
  single row's magnitude is not. The annotation text says so explicitly. Do not tighten the
  threshold below 5% without first raising `measured`.

## Osaurus needs care

Unchanged from the last handoff, and all of it still applies:

- Its KV cache **cannot be disabled from any command line** — only
  `~/.osaurus/config/server-runtime.json`, keys `cache.prefix.enabled` and
  `cache.blockDisk.enabled`. With it on, prefill is **8.3×** faster because it is a cache lookup.
- Changing those keys trips the settings drift guard, which refuses to run and names them. That
  is correct. Re-record with `osaurus_settings.write_baseline()` and restore afterwards.
- Backups: `~/.osaurus/config/server-runtime.json.ohyesmlx-backup`,
  `config/osaurus-settings-baseline.json.pre-cache-disable`. The baseline records cache **on**.
- `osaurus stop` frees the port and leaves the app alive (fixed in `4426238`). Sweep processes
  as well as ports. **Never sweep by name** — `osaurus mcp` is a long-running user process.
- Osaurus discovers the HF cache itself and names models after the repo, lowercased.
- **Task #3 is verified live**: `peak_mb` now reads 1331–2765 MB across its twelve rows, against
  the 4.7 MB it published before `7945067`. The port-resolved pid samples the app that holds the
  weights, not the launcher on its way out.

## Machine state

- **275 GiB free.** Unconstrained.
- `mlx-lm 0.31.3` at `~/.local/share/ohyesmlx/mlx-lm-0.31.3` — the control arm of every
  runtime-axis comparison.
- Installed: Osaurus 0.25.4, oMLX 0.6.4, mlx-optiq 0.5.6, vMLX 1.6.59.
- `docs/runtimes/osaurus.md` was written against 0.25.3 and is stale in unknown ways.
- The grid takes **~67 minutes** wall clock, five columns of 13–14 min each, via
  `scripts/run_grid.sh`. Run dirs land in `results/grid/<UTC>-format/`; `results/` is gitignored.

## How this project is run

- **PAUL is the only spine.** `.paul/STATE.md` is the single state store. If a second appears,
  delete it.
- **Delegate to Command Code.** Orders in `.paul/orders/`, dispatched by
  `.paul/orders/dispatch.sh <role> <order-file> [log]`, which prepends `PREAMBLE.md`
  **byte-identically** so it lands as a DeepSeek prompt-cache prefix at $0.003/M against
  $0.15/M fresh. Order text goes strictly after it. `CC_AGENT_MAX_TURNS=200` raises the turn cap.
  Default route is `deepseek`/`deepseek-v4.1-flash`; peak windows are a price bump the launcher
  announces and proceeds through, not a blocker.
- **Pin interfaces in `docs/interfaces.md` before fanning out.** Shapes are the coupling.
- **Opus reviews every diff and re-runs the suite personally.** Worker prose is not evidence.
  Verify with `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
  (needs `tokenizers`; there is no pytest in the repo venv).
- **Never edit `ohyesmlx/*.py` while a grid is running.** `run_grid.sh` re-enters the CLI once
  per column, so a mid-run edit means the five columns ran different code and cannot be joined.
- **A worker's justification is not verified because its tests pass.** The drift worker's own
  threshold comment claimed 5% cleanly split every row in every column. It does not — it splits
  the column medians. The code was right, the tests were right, the stated reason was wrong, and
  only running it against the real 60 rows showed that. Read what a worker claims, not just what
  it built.
- **Workers block well — let them.** The drift worker correctly flagged that rule 3 required
  editing a file outside its list, made the minimal docstring-only change, and said so. Treat a
  BLOCKED or a flagged scope note as a finding.
