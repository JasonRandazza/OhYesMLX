---
phase: v5-onboarding
plan: phase-5.5
completed: 2026-11-21
description: "Phase 5.5 deferred cleanup: all 10 items closed in four plans (055-01..04), plus the day-run follow-ups: median-of-3 canary baselines, 35B r4, the vMLX cold-load probe and the 35B paper notes"
type: Summary
about: "OhYesMLX"
---

# Phase 5.5 — Deferred cleanup (complete 2026-11-21)

## Items

| # | Item | Closed by |
|---|---|---|
| 1 | README full rewrite with the LMRE lineage | 055-03 |
| 2 | Retry of an interrupted evict opens the confirm sheet | 055-02 |
| 3 | `alreadyRunning` activates the other instance | 055-02 |
| 4 | A malformed `lab-paths.json` no longer breaks `ps`/`lsof` | 055-01 |
| 5 | One process-scan `sweep()` replaces 20 kill-by-port copies; pin copies matched where identical | 055-03 |
| 6 | A cancel interrupts `_verify` mid-file (about every 16 MiB) | 055-01 |
| 7 | A legacy bare-pid `download.lock` held by a non-ohyesmlx pid is reclaimed | 055-01 |
| 8 | "Free disk on <volume>" when the HF cache is not on `/` (new `Hardware.disk_volume`) | 055-02 |
| 9 | vMLX 1.6.84 TTFT and cold load, measured on a quiet machine | `docs/research/2026-11-20-vmlx-1.6.84-quiet-canaries.md` |
| 10 | S5-F2 correction notes on every flipped cold-load ordering (16 notes, 10 papers) | 055-03 |

## Follow-ups that came out of item 9 (Jason, 2026-11-20/21)

- **Five-engine canary and a fourth 35B replicate (r4) on current builds.**
  - **Format orderings:** every one holds.
  - **mlx-lm and OptiQ:** back near their 09-20 levels.
  - **oMLX:** 0.7.3 reads +7–16%, and its TTFT has more than halved.
  - **Runtime order:** below oMLX it is not stable between replicates.
  - Write-up: `docs/research/2026-11-20-canaries-and-35b-r4.md`.
- **The two 35B papers now carry r4 notes.**
- **vMLX 1.6.84 35B cold-load probe.** It shows about 4 s from page-cache state, about an 11 s fixed warm floor, and at most 1–3 s attributable to the version against 1.6.59. See §4 of the write-up.
- **055-04: canary baselines are the median of N interleaved runs** (`--repeat N`). All five engines were re-recorded with `--repeat 3` (spread ≤3.7%). OptiQ's baseline is now on the build the harness runs (0.5.13).

## Gates at close

- **pytest:** 1707 passed on `main`.
- **swift test:** 131 (055-02).
- **`sh -n`:** clean on `scripts/*.sh`.

`check_bundle` was not re-run: no packaging change. The DMG is unchanged from 0.3.0, and the app changes from 055-02 are not in a rebuilt DMG yet.

## Carried forward

- **Measurement hazard (Jason's config, not the repo).** Orca's 15-minute Antigravity usage poll (`agy -p /usage`) starts the Cloudflare MCP server from `~/.gemini/config/mcp_config.json`, and some instances outlive `agy` and spin at 100% CPU (first misattributed to claude-mem; corrected 2026-11-21). Four of them voided the first baseline attempt on 2026-11-21. Fix this before the next measurement.
- **35B runtime-axis ranking below the top.** It moves with engine versions and with the session. Any future runtime-axis claim needs replicates.
- **Release.** The 055-02 app changes ship only after the next `scripts/build_app.sh` + `check_bundle.sh`.
- **Phase 5.6** (UI aesthetics) waits on Jason's list.
