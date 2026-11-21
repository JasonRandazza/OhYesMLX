---
phase: v5-onboarding
plan: 055-04
completed: 2026-11-21
description: "Canary baselines are now the median of N interleaved runs (`--repeat N`). All five engines were re-recorded with --repeat 3 on a quiet machine."
type: Summary
about: "OhYesMLX"
---

# Plan 055-04: median-of-N canary baselines

**What shipped.**
- `ohyesmlx canary --repeat N` visits every engine N times, interleaved so that rep 1 visits every engine before rep 2 begins.
- The verdict and `--record` use the median per metric (`canary.median_reading`, the one definition).
- `--record` also writes the N readings as `runs`.

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC-1: repeat, interleaved, median | Pass | Interleave order, a run dir per visit, and one median-based line per engine are tested. `--repeat 1` gives today's output byte-for-byte; a review test covers the before→after load pair. `--repeat` below 1 is refused with exit code 2. |
| AC-2: what counts | Pass | A non-PASS rep fails the engine and is named. A noisy rep makes the engine noisy. |
| AC-3: record keeps the readings | Pass | The medians plus `runs` are written in rep order. The docs say what `--repeat` does in three places. |

## Verification

- **Red, then green.** The worker's 19 tests fail against `main` (19 failed, 2 passed). My three review tests were red against the worker's code, then green.
- **Suite.** The full suite is green after the merge: 1707 passed.
- **Review fixes (`395e6e7`).** A single visit keeps the before→after load order. `ESTIMATE` names `--repeat`. A median with an undefined metric is not recorded.

## The live recording (2026-11-21)

- **Attempt 1, 12:37–13:48: nothing recorded.** The load reached 6–7 and the harness correctly refused every baseline as noisy. The cause was four orphaned `mcp-server-cloudflare` processes, each at 100% CPU.
  - **Correction, same day:** they were first blamed on the claude-mem worker. A live capture showed the launcher is Orca's 15-minute Antigravity usage poll (`agy -p /usage`), which starts every MCP server in `~/.gemini/config/mcp_config.json`. Pausing claude-mem was unnecessary; clearing the orphans was the effective part.
  - The fix: the orphans were killed and the worker was paused for the re-run, then restarted with its own command line.
  - The root cause is in Jason's Claude configuration, not in this repo.
- **Attempt 2, 13:57–15:00: all five recorded.** Load was 1.7–3.8, under `LOAD_NOISY`. Osaurus was restored byte-exact.

| Engine | Version | Baseline (median) | The 3 runs | Spread |
|---|---|---|---|---|
| mlx-lm | 0.31.3 | 69.74 tok/s, 0.2220 s | 67.2 / 69.7 / 69.8 | 3.7% |
| Osaurus | 0.25.33 | 64.98 tok/s, 0.2951 s | 63.7 / 65.0 / 65.0 | 2.0% |
| oMLX | 0.7.3 | 82.73 tok/s, 0.1732 s | 82.4 / 82.7 / 82.7 | 0.4% |
| OptiQ | **0.5.13** | 75.36 tok/s, 0.2319 s | 75.5 / 75.4 / 75.4 | 0.1% |
| vMLX | 1.6.84 | 80.68 tok/s, 0.1785 s | 80.8 / 80.7 / 79.9 | 1.1% |

**The baselines' own build.** OptiQ's baseline is now on the build the harness actually runs: 0.5.13, where it was 0.7.8 before. mlx-lm's baseline is now taken after 05-07. The "moved" verdicts printed during the recording compare against the *old* baselines, and the replaced baselines are why they read "moved". They are not version movement.
