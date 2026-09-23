# Deep review 2026-09-23: verified summary

Six read-only reviewers on `gpt-6-luna` (orders in `.paul/orders/review/`) produced 44 findings,
one file per area in this directory. Every finding below was checked against the code by the
coordinator (Claude Opus). Duplicates across areas are merged. The per-area files keep the quoted
evidence.

Verdicts: **confirmed** (the code does this), **conflict** (two authoritative documents disagree
and a decision is needed), **not a defect** (see the reason given).

## A. Wrong numbers can be published

| # | Finding | Source | Verdict |
|---|---|---|---|
| A1 | The leaderboard table and metric card print TTFT, decode, aggregate and prefill figures for **FAIL** rows, which the coherence rule forbids ("reports FAIL … never a tok/s figure"). Only the grid and sweep suppress them. Aggregate on a FAIL row also divides tokens from the requests that did come back by the time of spans that include failed batches. | metrics F1 | confirmed (`report._cells` / `_card` render every row's numbers) |
| A2 | A single-delta response gets two separate `time.monotonic()` calls (`transport.py:303-304`), so `last_content_s - ttft_s` is float noise rather than zero. `measure.decode_tps` has no delta-count domain check, so `measured_drift` and the concurrency-1 warmup plateau consume the bogus rate. This is the documented 1.5-billion-tok/s bug, still live in drift and warmup. | metrics F2, docs F3 | confirmed |
| A3 | v3 research numbers come from probe scripts that reimplement the metrics instead of calling the harness: `(tokens-1)/span` for decode (`probe_kv_quant`, `probe_multiturn_sweep`), `total - ttft` for decode (`probe_native_mtp_35b`), `0.0` for undefined rates, a `ps` RSS fallback for memory (`probe_native_mtp_35b`, `probe_speculative_draft`), coherence recorded but not gating, multi-turn means that include cold turns, and raw observations reduced to snippets. Those papers' figures are therefore not comparable with harness-produced figures. | scripts F3–F8 | confirmed |
| A4 | `probe_grid.py` and `probe_grid_moe.py` label an incoherent-but-HTTP-200 cell `LOADS`. These probes chose grid membership. | scripts F2 | confirmed |
| A5 | Reasoning-only and mirrored streams are timed on the reasoning channel and published as TTFT and decode. AGENTS.md says "Reasoning tokens are not content"; `docs/interfaces.md` documents the reasoning-channel timing as intended. | invariants F1, docs F6 | **conflict**: needs a decision |
| A6 | Sampling is only partly pinned. The request pins temperature 0 and a seed. No runtime pins `top_p`/`repetition_penalty`, and OptiQ injects `generation_config.json` sampler flags into its argv. `docs/runtimes/optiq.md` documents that injection and its one-flag fix, and the fix was never applied. At temperature 0, `top_p` is inert, but a runtime-side `repetition_penalty` would not be. Per-runtime impact is not verified. | invariants F2, docs F4 | confirmed (impact unverified) |
| A7 | Runtime-axis grids still print an ordering for `peak_mb` and `cold_load_s`, with a warning. AGENTS.md says `peak_mb` "carries no cross-runtime ranking". | invariants F6 | **conflict**: warn or refuse |

## B. The one-model-resident rule can be broken silently

| # | Finding | Source | Verdict |
|---|---|---|---|
| B1 | Stale port-free Osaurus apps are not swept. AGENTS.md documents the hazard and the fix (sweep by full executable path), and no code does it. | invariants F4 | confirmed |
| B2 | If `lsof` fails, `_listener_pids` returns `()`, so a handed-off Osaurus app is never captured. `osaurus stop` then frees the port and shutdown returns "clean". | failures F3 | confirmed |
| B3 | A failed cleanup after a failed start is swallowed (`except RuntimeLifecycleError: pass`). The visit returns "retry" and the run moves on to the next cell, which may be a different runtime on a different port, while the first process may still hold weights. | failures F2 | confirmed |
| B4 | The second `_await_exit` after SIGKILL is ignored. A free port lets shutdown return while the spawned pid may still be alive. | failures F7 | confirmed |

## C. Data loss and leftover state

| # | Finding | Source | Verdict |
|---|---|---|---|
| C1 | An exception or Ctrl-C inside a visit loses that visit's observations: `write_jsonl` runs only after `_visit` returns. | failures F4 | confirmed |
| C2 | Between `runtime.start()` returning and the `try/finally`, a Ctrl-C skips `handle.stop()`. The reviewer rated this critical; downgraded because the window is a few assignments. | failures F1 | confirmed (medium) |
| C3 | An existing-but-unreadable Osaurus baseline disables the drift gate the same way an absent one does. | failures F5, invariants F3 | confirmed |
| C4 | `Sampler.stop()` can return with its thread still alive; an oMLX scratch dir leaks if construction fails mid-way; a failed `write_jsonl` leaves `.tmp` behind. | failures F6, F8, F9 | confirmed (low) |

## D. Contract gaps

| # | Finding | Source | Verdict |
|---|---|---|---|
| D1 | End-to-end latency P50/P90/P99 is required by AGENTS.md and not reported; only TTFT percentiles exist. | invariants F7 | confirmed |
| D2 | No harness revision in the run header, so columns run on different code join silently. | invariants F8 | confirmed |
| D3 | A generic `unknown: …` version string passes the one-version-per-runtime guard. | invariants F9 | confirmed |

## E. Tests that cannot catch regressions

| # | Finding | Source | Verdict |
|---|---|---|---|
| E1 | The measure fakes never carry an API key, so dropping `api_key=handle.api_key` from `_request` stays green (real oMLX would return 401). | tests F1 | confirmed |
| E2 | The SSE test server always returns 200 with an event-stream response, so the HTTP-status and non-SSE rejection paths are untested. | tests F2 | confirmed |
| E3 | There is no test of the request deadline (a short `timeout_s` against a stalled server). | tests F3 | confirmed |

## F. Documentation drift

`docs/interfaces.md` record and header schema (docs F1, F7, F9, F12); README runtime tables omit
vMLX and list MLX Studio (docs F2, F5, F8); stale
line citations in `docs/runtimes/*.md` (docs F11). All confirmed as drift, with no measurement impact.

## Not defects

- scripts F1: the speculative-draft probe keeps both models resident **by design**. The published
  finding is about dual-model residency, and the paper reports the +3,072 MB overhead.
- invariants F5: the quiet-machine rule is declared unenforceable in AGENTS.md. A cheap
  pre-run check (another runtime or download process alive) is a possible addition, not a defect.
- invariants F10: discarding runs is a process rule, not code.
- **docs F10 is fabricated.** It quotes `| Version | 0.0.1 |` / `| Status | Prototype |` at README.md:27-34, and no such lines exist anywhere in README.md (`grep -i "0.0.1\|prototype"` finds nothing). Rejected.

## Reviewer quality (gpt-6-luna, first use)

All 6 workers finished, and none changed anything outside its output file (checked with `git status`). Every
finding but one carried quoted evidence that matched the code; **docs F10 quoted README lines that do
not exist** (a fabricated finding, caught only by checking). That is the failure the fleet policy
warns about, and the reason every luna finding and diff is verified against the repo, not its report. One severity was overstated (C2), and one
design decision was reported as a defect (scripts F1). The tests reviewer did not run the
coverage command it was offered. This is an observation, not the owed route trial.
