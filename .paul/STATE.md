---
description: "OhYesMLX — current position and accumulated context"
type: ProjectState
about: "OhYesMLX"
---

# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-09-14)

**Core value:** A Mac user can find out whether their serving runtime or their quantization is what's actually costing them speed and memory.
**Current focus:** v5.0 Onboarding App (2026-10-29, takes precedence; MTPLX parked on `mtplx-wip`). Previously: v3.1 Hardening — Phases 1–4 done (2026-09-25); what remains of the milestone is Jason's call

## Current Position

Milestone: v5.0 — Onboarding App (started 2026-10-29; takes precedence over v3.1/v4.0). Phases 0-3 complete on `main`; Phase 4: 04-01, 04-01b, 04-02, 04-02b, 04-03a, 04-03b built 2026-11-02, 1144 tests; 04-03c closed 2026-11-03 (Osaurus baseline gap fixed); Phase 4 code review done 2026-11-03 (Standards + Spec, 9 verified findings fixed, 1164 tests); UAT 8/8 pass 2026-11-03 (`04-UAT.md`, one known minor). **Phase 4 complete** (`PHASE-4-SUMMARY.md`). Phase 4.5 security hardening: planning, split model→fix→smoke (Jason 2026-11-03); 045-01 closed 2026-11-03 (`docs/threat-model.md`: 6 medium + 10 low, none high; triage approved; `045-01-SUMMARY.md`). 045-02 split in two (Jason 2026-11-03): `045-02a` (server + lifecycle: T-02/03/04/05/08/09/10/11) closed 2026-11-09 (`4b35ef8`, `9bc9388`, review fixes `6c4d616`; 1222 tests; probe 32/32; code review 10 verified + 1 rejected; `045-02a-SUMMARY.md`); 045-02b (installers + fetch: T-01/06/07/12/13/16) closed 2026-11-13 (`a031ad4`, `fb4e61c`, review fixes `7393715`; `045-02b-SUMMARY.md`); 045-03 clean-account smoke closed 2026-11-13 (`743ada3`, `369f180`, `f7c22e0`; 21/21 as `oymlxtest`; two defects fixed; 1329 tests; `045-03-SUMMARY.md`). **Phase 4.5 complete** (`PHASE-4.5-SUMMARY.md`). Phase 5 (SwiftUI app): prototype answered 2026-11-13; 05-01 Stop now (`93d374c`), 05-02 app skeleton (`004171c`), 05-03 design (`99d2a55`), wave-1 review fixes (`ac0de1b`): 1366 pytest + 52 swift tests. 05-04 shell/Your Mac/Engines (`3495886`), 05-05 Models/Benchmark/Results (`bb762c6`), 05-06 packaging (`101df7c`), wave-2 review fixes; 1370 pytest + 81 swift tests; check_bundle 9/9.
Plan: `.paul/phases/v5-onboarding/PLAN.md`; per-phase plans, audits and summaries beside it.
Status: Phase 2.5-3 code review done 2026-11-02 (Standards + Spec, 9 findings fixed, 957 tests); T2.5.5 done (pip installs use committed `ohyesmlx/constraints/` freezes, 959 tests); 04-01 closed (SUMMARY written). Handoff: `.paul/HANDOFF.md`.
Last activity: 2026-11-03 — 04-03c: quickbench re-run live, all 5 engines PASS incl. Osaurus 131.3 tok/s, restore byte-exact; hero-model safetensors proven to be the pinned tensors. 2026-11-02: quickbench first live run (Osaurus refused by baseline-path gap). Before: 04-02 unified: jobs + SSE (live scratch download/evict). 04-01b: gpu_cores from ioreg. Before it, 04-01: `ohyesmlx app` guarded loopback API (`1c157b0`).
v3.1 (0.3.1 bump) and v4.0 MTPLX (branch `mtplx-wip`) are paused, not abandoned.

## Loop Position

Current loop state:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ◐     [Phase 5: 05-01..05-06 built, reviewed (2 waves) and committed 2026-11-14 (`101df7c`); open: 05-06 AC-6 clean-account smoke (Jason's sudoers step), live Stop-now + download checks (Jason's go-ahead), Phase 5 UAT]
```

## Performance Metrics

**Velocity:**
- Total plans completed: 0 (not tracked per plan; see each SUMMARY)
- Average duration: —
- Total execution time: —

## Accumulated Context

### Decisions

Recent only. The full log, every row verbatim, is `.paul/DECISIONS.md`.

| Decision | Phase | Impact |
|----------|-------|--------|
| 2026-11-10: Enterprise audit performed on .paul/phases/v5-onboarding/045-02b-PLAN.md. Applied 3 must-have, 4 strongly-recommended upgrades. Deferred 4. Verdict: conditionally acceptable | v5.0 Phase 4.5 | pip step gains `--only-binary :all:` (hash mode skips sdist build deps); late-uploaded files reviewed before trusting a freeze; live install proves real Application Support untouched |
| ~~2026-11-10: OptiQ install exempts pygame from `--only-binary :all:` (`engines._SOURCE_BUILDS`)~~ **Superseded 2026-11-13 (045-03):** the source build needs SDL headers a clean Mac lacks; optiq now installs with `--no-deps` and no pygame (used only by `optiq game`). | v5.0 Phase 4.5 | Jason's call at a 045-02b BLOCKED: pygame 2.6.1 has no cp314 wheel and mlx-optiq 0.5.13 requires it (game command only); built from source as the lab copy was; build tools unhashed, recorded in threat-model §9 |
| 2026-11-09: 045-02a AC-7 drift check is an injectable `run()` keyword; one existing quickbench test (`test_the_host_pinned_between_pin_and_restore_shows_no_drift`) is edited to inject it at its tmp config dir | v5.0 Phase 4.5 | Jason's call at a BLOCKED from the part-B worker: the plan's 'existing tests unmodified' and 'live config vs pinned baseline' could not both hold, because that test pins a tmp config dir while the default check reads the real ~/.osaurus. No test reads the real Osaurus settings. |
| 2026-11-14: Fable 5.2 review: Opus orchestrates; Fable 5.2 reviews 6 sections as background subagents over MiMo-v2.6-Pro-built dossiers; **Kimi K3.1 Pro approved by Jason as the main worker** (new explicit-only route `kimi-pro`, added after its bench); Qwen 3.8 Max skipped. Budget: the current Fable allowance + 1 Fable reset (both expire 2026-11-17 2:59 AM EST); at most 1 of 4 full resets for Fable | v5.0 review | `.paul/review/fable-5.2/PLAN.md`, order files in `orders/` |
| 2026-11-14: Quickbench `best` names its format and repo; `Pick.measured_here` is keyed by the repo the winning cell measured | v5.0 Phase 5 | Found in 05-05 review: since 04-03b a stage-B sibling's win was shown on the chosen model. Fixed and red-checked (`bb762c6`). |
| 2026-11-14: The bundled interpreter tree is precompiled (unchecked-hash) and the launcher runs `-I -B` | v5.0 Phase 5 | Found by check_bundle: child interpreters wrote stdlib bytecode into the signed bundle (P5-6). Fixed (`101df7c`). |
| 2026-11-13: Enterprise audits on 05-01-PLAN (1 must-have, 3 strongly-recommended, 2 deferred) and 05-02-PLAN (3 must-have, 2 strongly-recommended, 1 deferred). Verdict both: conditionally acceptable, upgrades applied | v5.0 Phase 5 | Stop now: raise-safe, off the request thread, one stop per job. Launcher: pipes drained, stdin held, child death -> Relaunch, Quit anyway after 150 s |
| 2026-11-13: Phase 5 prototype answers (Jason): Q1 grey out other job controls with the reason; Q2 interrupted job -> banner + Retry, never auto-retry; Q3 both "Stop after this cell" and "Stop now" (new backend mid-cell abort, plan 05-01); Q4 low_disk owned by Models, inline; Q5 re-detect engines on app focus + "Check again"; Q6 unsupported gate absolute; Q7 Results names not_evicted in one plain line | v5.0 Phase 5 | Binding for 05-02..05-05; pinned in `docs/interfaces/v5-app.md` |
| 2026-11-13: optiq installs without pygame (`--no-deps` on every pip step, wheels-only, no exception); app engines exec their in-bundle tool when the bare name is not on PATH | v5.0 Phase 4.5 | Found by the clean-account smoke (045-03): the pygame source build needs Homebrew SDL, and launchd's PATH (P5-9) has none of the per-user shims. Supersedes the 2026-11-10 pygame call. Recorded start commands unchanged. |

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| README.md needs a full rewrite, including a lineage/acknowledgement section naming LMRE as the predecessor and linking its archived repo (`JasonRandazza/local-model-runtime-evaluation-harness`) | Docs 2026-10-09 | M | Jason's call: address the README as a whole, not piecemeal. The lineage wording to draw on is in the Deep Wiki charter record (`OhYesMLX Charter and Origin - 2026-09-14`) |
| Disk audit incomplete — two workers hit the turn cap | Phase 2.1 | S | **Disk has tightened: 40 GiB free on 2026-11-13** (was 238 GiB 2026-09-16). Phase 5 needs little (python-build-standalone ~100 MB, Swift build cache); revisit before any model fetch |
| P5-11: the app cannot offer "Re-download" for a model whose files differ in size, because `Pick.downloaded` is a single bool | Phase 5 (threat-model §10 status) | S | A backend field (e.g. bytes on disk, or a present-but-different flag) plus the Models row copy; also in the Fable S4 scope |
| Eight pre-`first_request_workload_id` run dirs cannot be loaded | Phase 5 | S | `load_run` refuses them by line number rather than defaulting the field. A schema migration, only if those columns are ever wanted |
| Osaurus pin copies remain in run_grid.sh / run_grid_moe.sh / run_sweep_cache*.sh / run_accuracy_* / run_jang_* / run_sweep_prompt.sh | v3.1 2026-09-25 | S | Their semantics differ (idle-900 only, or the cache is the varied pin); listed in `scripts/osaurus-pin.sh`. Consolidate only where identical |
| ~~Harness does not record `usage.cached_tokens`~~ **DONE 2026-09-29** | v3.1 2026-09-25 | S | `Observation.cached_tokens` (transport.py) reads `usage.prompt_tokens_details.cached_tokens` (oMLX/OptiQ/vMLX) or `usage.cached_tokens` (mlx-lm), `None` when unsaid; recorded per observation, not yet surfaced in a report or gate. Old records load as `None`. Osaurus sends neither (`docs/runtimes/osaurus.md:668`), so a `None` there means unsaid, not zero. |
| Thinking-Off MMLU Arm (Candidate 3) | Post-v2 | M | **RUN, NOT MEASURABLE (2026-10-05).** Ran 2×2 on Osaurus 0.25.16 at cap 1024 (`results/accuracy-thinkoff`) and 4096 (`-cap4096`, 8.4 h); vMLX refuses `enable_thinking=false` on LFM2 (HTTP 400). Thinking-off cells scored 0.5–5% with 86–99% empty content. Direct probe (Osaurus 0.25.18, `lfm2.5-8b-a1b-mlx-4bit`, real MMLU prompt, max_tokens 8192): the request-side switches `chat_template_kwargs.enable_thinking`, top-level `enable_thinking`, `reasoning_effort`, `modelOptions.disableThinking` (both shapes) change nothing — reasoning is identical (1,706 chars), ends in ~2 s, content follows. The empties are a **stop-sequence artifact, not truncation or looping**: the thinking-off arm inherits the task's `until: ['</s>', '\n']`, the answer in `content` starts with `\n`, so content is cut to ''. The thinking-on arm overrides `until` to `<|im_end|>`, so the arms differed in the stop list as well as the switch, and the arm is invalid. Per-model plist `disableThinking` for LFM was not tried (host state; needs Jason's yes). Thinking-on at cap 4096: jang2l 46.6%, stock4bit 62.5%, still 6% empty (cap-limited). Next, if wanted: thinking-on at cap 8192 (~8 h), or drop the arm. |

### Blockers/Concerns

| Blocker | Impact | Resolution Path |
|---------|--------|-----------------|
| **AGENTS.md says `top_p`/`repetition_penalty` and the chat template are pinned; only OptiQ's sampler is** (found 2026-09-25) | The harness sends temperature, seed, max_tokens and the messages only; the other four runtimes use their own sampler defaults and chat templates (README says so). At temperature 0 `top_p` cannot change a greedy token, but a non-1.0 default `repetition_penalty` can. | **RESOLVED 2026-09-29 (Decision 131).** Defaults surveyed (Antigravity read-only pass, spot-checked): only vMLX could take a penalty from the artifact, so it is pinned with `--default-repetition-penalty 1.0`; AGENTS.md now states what each runtime pins and that the chat template is each runtime's own. Osaurus's penalty defaults remain *not found*. |
| **Osaurus applies the model bundle's `presence_penalty` / `repetition_penalty`, and the harness does not pin them** (found 2026-09-29 from Osaurus's public source, `MLXBatchAdapter.effectiveGenerationSettings` and `LocalGenerationDefaults`, identical at 0.25.6 and 0.25.14; untouched by the 0.25.15 diff) | Precedence is request, then the host's saved Sampling Default (this host saves none), then the bundle's `generation_config.json`. The Qwen3.5-4B-OptiQ-4bit and Qwen3.6-35B-OptiQ bundles ship `presence_penalty: 1.5`; the LFM2.5-8B-A1B oQ4e and OptiQ bundles ship `repetition_penalty: 1.05`. So every Osaurus `optiq` cell (speed grids, and the dense accuracy study, where OptiQ ran on Osaurus only) ran under a penalty the other formats did not, at any build. That puts the dense accuracy finding "OptiQ strictly Pareto-dominated" (−3.1 to −4.4 pp on MMLU) and its speed readings on Osaurus under an unquantified confound. Not yet known: whether the HTTP request can override `presence_penalty` (the DTO reading in `docs/runtimes/osaurus.md` lists no presence or frequency field). | **TESTED 2026-09-30 (`scripts/run_penalty_test.sh`, Osaurus 0.25.15 both arms, MMLU 5-shot limit 40 = 2,280 items, thinking off, temp 0, caches off; results in gitignored `results/accuracy-penalty/`).** Shipped bundle and a scratch copy with `presence_penalty` removed (weights symlinked) scored **61.01% both** (stderr 0.88 pp), every subject equal, **0 of 2,280 scores flipped**. The generated text differed in 215 of 2,280 responses (9.4%), so the stripped key changed what the model said and did not change whether it was right. Consequence: the dense accuracy finding's OptiQ MMLU number does not depend on the bundle penalty, and the 09-19 61.05% on 0.25.6 agrees. Not established: that the 215 differences come from the penalty and not from run-to-run nondeterminism (no shipped-vs-shipped repeat was run); GSM8K and IFEval were not re-run; the 35B and LFM OptiQ bundles (`repetition_penalty` 1.05) are untested, and the speed-side effect of the penalty is unmeasured. The arms ran 4,110 s and 3,683 s, which is wall time on a machine with a browser open, not a speed reading. Whether an HTTP request can override the penalty is still unknown. Do not cite the 61.01% against 09-19 cells except as agreement, since caches and pin differ |
| **Resolved 2026-11-03: the two hero-model `model.safetensors` files hold the pinned tensors, re-ordered** (found 2026-11-02, 04-02b live check) | `Qwen3.5-4B-4bit` (`0e7ffd5c`) and `LFM2.5-8B-A1B-MLX-4bit` (`146590a4`): the local files are a re-serialisation of the pinned revision. Same tensor names, dtypes and shapes (1221 / 566 tensors), tensor region byte-identical in length; only the header differs (873 / 139 bytes longer) because the tensors sit at different offsets. Proof: fetching only the pinned header (HTTP range, KB) and streaming the local tensor bytes in the pinned offset order reproduces the revision's LFS sha256 exactly, for both. So every published table measured the pinned weights; no caveat needed. Still true: `fetch.downloaded()` reports these two as not downloaded (size check), and mmap/load order differs from a fresh download (no effect on decoded tokens). | Closed, no action. Fresh downloads not needed. |
| **mlx-lm and OptiQ serve repeated prompts from their prompt cache when `cache_state` is unpinned** (found 2026-09-28, `docs/research/2026-09-28-seedless-validation-grids.md` §2.2) | The absent pin passes no `--prompt-cache-size`, so mlx-lm's default cache (10) is on; the seeded path could not hit it, the seedless batched path does. Dense/MoE `prefill` TTFT for these two fell ~91% (MoE mlx-lm 1.04 → 0.09 s) — cache hits, not prefills. oMLX, vMLX and Osaurus already run cache-off without a pin. Also affects the concurrency sweep's mlx-lm/OptiQ `prefill` rows (0.15–0.19 s TTFT). Decode rates are not a cache quantity. | **RESOLVED 2026-09-29 (Decision 130).** Fixed in code 2026-09-28; re-run 2026-09-29 into `results/harden-2026-09-28-cacheoff` (dense, MoE) and `results/sweep-conc-cacheoff` (mlx-lm, OptiQ), all cells exit 0. Cache off, mlx-lm/OptiQ `prefill` TTFT is 2.3 s dense / 1.03 s MoE (09-23 seeded: 2.4 / 1.04), and the concurrency `prefill` aggregate is flat (mlx-lm ×1.08, OptiQ ×1.16, was ×1.57 / ×1.31); the `decode`-shape 1.69× / 1.65× headline holds. Both papers corrected in place (concurrency paper's 2026-09-29 correction section and §5; grids paper §2.2). The OptiQ N=2 dip that run showed did not recur when N=2 was repeated alone (2026-09-29 13:18 → 13:29, `results/optiq-n2-repeat`: decode 44.9/42.3/45.6, aggregate 76.6/75.0/16.3, all PASS) — a session or ordering effect, cause not identified; `cached_tokens` read 0 on all 54 observations. |

## Boundaries (Active)

- `.paul/STATE.md` is the only project state store. If a second appears, delete it.
- No new dependency without naming what it replaces.
- No governance layer: no plan hashing, no sealed evidence, no action grants, no workspace scaffolding.

## Session Continuity

Last session: 2026-11-14 (Claude Opus 5.5 coordinator)
Stopped at: Phase 5 first pass done and documented. Fable 5.2 review planned (`.paul/review/fable-5.2/PLAN.md`).
Next action: open the session by walking Jason through HANDOFF "Start here" (8 items; 1–4 are time-critical because the Fable 5.2 Pro promotion ends 2026-11-16 23:59 PT). Then run `.paul/review/fable-5.2/PLAN.md` as written (P0-1 Kimi route: its bench was started 2026-11-14 into `~/AI/Agent-Environment/reports/paid-fleet/model-bench-2026-11-14-kimi`; P0-2 dossiers; F sections; V on Kimi). Phase 5 close: clean-account smoke, live checks, UAT, P5-11.
Resume file: `.paul/HANDOFF.md`
Open Design: MCP registration (Codex) points at the 0.24.1 payload; the app is 0.26.1. This session ran a headless daemon on 127.0.0.1:17456 plus a stdio shim. Jason to refresh it in the app.
Osaurus on this host is now 0.25.33 (untested build; was 0.25.29 on 2026-11-02).
Engine builds on this host (2026-11-02): Osaurus 0.25.29 and oMLX 0.7.3 (tested, Decision 139), vMLX 1.6.82 still untested (same-build canary 2026-11-02 13:10 read decode 74.5 -> 70.4 tok/s, -5.5%, TTFT +3.9%, load 2.4-2.6: session variance at the 5% floor, not a version effect; 1.6.59 has no baseline, so adoption needs a cool-machine repeat or a 1.6.59 canary, `results/canary/20261102T180945Z-vmlx`), OptiQ 0.7.8 global (0.5.13 lab copy used by the harness via `lab-paths.json`), mlx-lm 0.31.3, vMLX 1.6.82 (untested build).

---
*STATE.md — Updated after every significant action*
*Size target: <100 lines (digest, not archive)*
