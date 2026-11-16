---
description: "Executable plan for a token-efficient whole-project review of OYMLX with Claude Fable 5.2 as reviewer, Opus as orchestrator, MiMo v2.6 Pro building dossiers and Kimi K3.1 Pro as the main verification worker"
type: Plan
about: "OhYesMLX"
---

# Fable 5.2 review of OYMLX — executable plan

Written 2026-11-14 by the Opus coordinator. Amended the same day after Jason confirmed his budget and worker
choices. Everything here is decided. The next session executes it in order and asks Jason only the four numbered
checkpoint questions (marked **ASK**). The order files are already written in `.paul/review/fable-5.2/orders/`.

**Amended at execution, 2026-11-14 evening (these override the sections below):**
- `Agent(model: "fable")` resolves to `claude-fable-5-1` (the API response's model field). Fable sections therefore run headless:
  `claude -p --model claude-fable-5-2 --allowedTools Read Grep Glob Write --output-format json "<§5 + section line>"`, in the
  background, logging to `orders/fable-S<n>.json`. The CLI warns `unrecognized_model`; the API serves `claude-fable-5-2`.
- Command Code's 5-hour window went from 6% to 70% during P0-2 (7 parallel MiMo Pro workers; S2 spawned its own subagents).
  So: **verification runs on `deepseek`, at most 2 at a time, after the Command Code window resets**; `kimi-pro` only for
  High re-checks. Dossier S2 was stopped at 16 minutes of silence and is rebuilt alone, with no subagents.
- Command Code budget (Jason, 2026-11-15: weekly 42%, monthly 24%): High/Medium findings get one DeepSeek verifier each
  (`orders/run_verify.sh`); **Lows are batched, one DeepSeek run per section** (`orders/run_verify_batch.sh`). Fable runs one
  section per Anthropic 5-hour window unless Jason reports headroom (`orders/run_fable.sh S<n>`).
- Kimi's GOAT price is $2.00/$10.00 per M with $0.20 cache reads: bench mean $0.087/run, about 10× `mimo-pro`.

This is a review, not a phase: its output is a verified, ranked findings list (`FINDINGS.md`). Fixes go through
normal PAUL plans afterwards, and they need no Fable.

## 0. Budget and deadline (Jason's usage panel, 2026-11-14)

| Item | What it does | Expires |
|---|---|---|
| Fable 5.2 inside the Pro plan | Fable may use up to 50% of the weekly limit | **Tue 2026-11-17 2:59 AM EST** (= Mon Nov 16 11:59 PM PT) |
| **1 Fable reset** | Refills the 5-hour limit and the Fable allowance, and gives back what Fable used of the weekly limit. It does not reset the whole week. | Tue 2026-11-17 2:59 AM EST (the same moment) |
| **4 full resets** | Reset the whole usage week | First expires Wed 2026-12-10 5:00 PM EST |

So the Fable capacity inside the promotion is **the current allowance plus one Fable reset**, about two Fable
allowances. The full resets outlive the promotion and are worth more afterwards (Opus orchestration, the Phase 5
close-out). Policy:

1. Spend the **Fable reset first**, the moment Fable's allowance or the 5-hour window runs out. It expires with the
   promotion, so it is free to use and lost if unused.
2. Use **at most one full reset** for Fable, and only if S1–S3 are not all done by the time both allowances are spent.
   Keep the other three for after the promotion.
3. **No Fable section starts after Mon 2026-11-16 11:30 PM EST.** A section takes roughly 20–45 minutes, and a
   half-run section wastes its reads. Anything left falls back to Kimi (§6).

Opus's own usage counts against the same 5-hour window, so the orchestrator stays lean: it reads findings and
verdicts, never whole source files.

## 1. Roles (decided)

| Role | Who | How it runs |
|---|---|---|
| Orchestrator, final verdicts | Claude Opus 5.5 (the session running this plan) | Dispatches, gates, spot-checks, and writes FINDINGS.md |
| Reviewer | **Claude Fable 5.2**, one background subagent per section | `Agent(model: "fable", run_in_background: true)`; writes only its findings file |
| Dossier builder | **MiMo v2.6 Pro** (approved route `mimo-pro`) | `CC_ROUTE=mimo-pro .paul/orders/dispatch.sh implement …` |
| **Main worker**: verifier, red-test writer, later fixer | **Kimi K3.1 Pro** (`moonshotai/kimi-k3.1-pro`), approved by Jason 2026-11-14 as a new route `kimi-pro` | `CC_ROUTE=kimi-pro .paul/orders/dispatch.sh implement …` once P0-1 has added the route |
| Fallback worker | DeepSeek V4.1 Flash (`deepseek`, the default) | Used if Kimi is rate-limited or fails its bench |

Why these (research 2026-11-14, Vals Index of Nov 9 and Artificial Analysis):

- **Kimi K3.1 Pro** scores 62.5% at $6.44 per task; it is #4 overall on Artificial Analysis (55.1) and first on
  Terminal-Bench 4.0.
- **DeepSeek V4.1 Flash** scores 61.3% at $0.66 per task.
- **Qwen 3.8 Max** scores 59.1% at $8.73 per task, so both models above beat it, and it costs more per task. **Skip it and
  Max Prime**, which is the same model served faster.
- **MiMo v2.6 Pro** scores 57.8% at $0.43 per task, with a 1M context and a $0.0036/M cache read: an excellent reader
  for dossiers.

**Fable is not the orchestrator, and there is no single whole-repo pass.** About 250K tokens of source (16.5K Python,
5.7K Swift and 2K script lines, plus 26K lines of tests), read agentically, is millions of tokens, mostly re-reads.
It could not stop at a reset, and one failure would lose it all. Sections over curated dossiers put Fable's tokens
on judgment.

## 2. Sections (priority order)

| # | Section | If the window closes early |
|---|---|---|
| S1 | Security and trust boundaries (server, installers, fetch, ledger, launcher, signing, threat model) | Must do |
| S2 | Measurement integrity (transport, measure, coherence, report paths, canary, quickbench numbers) | Must do |
| S3 | The SwiftUI app (AppModel, launcher, client, views, a11y, design fidelity) | Must do |
| S4 | Onboarding backend (engines, fetch, quickbench, catalog, recommend, hardware; P5-11 known) | Kimi fallback |
| S5 | Runtime lifecycle and host safety (runtimes, Osaurus pin) | Kimi fallback |
| S6 | Packaging and release (build/check/fetch/SBOM scripts, plist, gatekeeper doc) | Kimi fallback |

The exact scope, contracts, scan patterns and open questions per section are in `orders/dossier-S<n>.md`.

## 3. Timeline (EST, which is what Jason's panel shows)

| When | Step | Fable? |
|---|---|---|
| Session start, Sat 11/14 evening or Sun 11/15 morning | HANDOFF "Start here" with Jason (about 15 min) | no |
| +0:15 | P0-1 Kimi route, P0-2 dossiers ×6 and W1 dispatched in parallel, P0-3 Fable ping | ping only |
| about +1:30 | P0-4 Opus spot-checks the dossiers; rebuild any bad one | no |
| Sun 11/15 | F: S1 → S2 → S3, with V verification pipelined on Kimi as each lands | yes |
| Sun 11/15 or Mon 11/16 | F: S4 → S5 → S6 if the allowance remains (otherwise the Kimi fallback) | yes |
| **Mon 11/16 11:30 PM** | **The last Fable section may start** | — |
| Tue 11/17 onward | V finishes; FINDINGS.md; fix plans via PAUL (Kimi or DeepSeek workers) | no |

Live Phase 5 checks (Stop now, a download) must not overlap any worker or Fable run (AGENTS.md). Do them before P0 or
after V, whichever Jason picks.

## 4. Steps

### P0-1 — Add the `kimi-pro` route (coordinator, in `~/AI/Agent-Environment`)

The bench was started on 2026-11-14 by the previous session:
`scripts/fleet/model-bench.py --out reports/paid-fleet/model-bench-2026-11-14-kimi --reps 3 --jobs 6 moonshotai/kimi-k3.1-pro`
(18 graded runs, the same battery that approved the current routes).

1. **Bench done 2026-11-14: `moonshotai/kimi-k3.1-pro` 18/18 graded passes, 0 collateral deletions, median 80.2 s/run**
   (`python3 scripts/fleet/model-bench.py --summarize reports/paid-fleet/model-bench-2026-11-14-kimi`; $/run shows n/a until
   step 3 adds its price). It meets the pass bar, so go straight to step 2.
   **Pass bar:** at least 17/18 graded passes and **zero** collateral deletions (the 2026-09-24 standard). If it is
   unfinished, wait. If it failed, Kimi does not get the route; use `mimo-pro` for verification and tell Jason.
2. That repo has **another session's uncommitted edits** (`AGENTS.md`, `docs/deepwiki-documentation-policy.md`). Do not
   touch or commit them; stage only your own files.
3. Add the route the way the existing ones are defined:
   - `scripts/fleet/paid-routes.sh`: a `kimi-pro) model='moonshotai/kimi-k3.1-pro' ;;` case in `paid_route_model`,
     and `kimi-pro` in the routes loop.
   - `scripts/fleet/cc-agent.sh`: the usage string.
   - `policies/provider-fleet.json`: a route entry marked **explicit-only** ("approved by Jason 2026-11-14 for the
     Fable 5.2 review and its fixes"). Do not add it to the fallback order or to any profile default.
   - `scripts/fleet/route-cost.py`: a PRICING entry from the bench's own events (`route-cost <events.ndjson>`);
     if Command Code's cache-read price cannot be derived, enter OpenRouter's $2/$10 per M and mark it provisional.
   - A `DECISIONS.md` row, plus `reports/paid-fleet/kimi-route-adoption-2026-11-14.md` with the bench table.
4. Re-run `scripts/install-orca-agent-layer.sh`, then `--check`. Verify with
   `cc-agent implement --route kimi-pro --check-only`, which must print `READY: … model=moonshotai/kimi-k3.1-pro`.

### P0-2 — Dossiers and W1 (MiMo v2.6 Pro, all seven in parallel, background)

```sh
cd ~/Dev/active/OhYesMLX
export CC_AGENT_MAX_TURNS=200
for s in S1 S2 S3 S4 S5 S6; do
  (CC_ROUTE=mimo-pro .paul/orders/dispatch.sh implement .paul/review/fable-5.2/orders/dossier-$s.md \
     .paul/review/fable-5.2/orders/dossier-$s.log &)
done
(CC_ROUTE=mimo-pro .paul/orders/dispatch.sh implement .paul/review/fable-5.2/orders/W1-sweep.md \
   .paul/review/fable-5.2/orders/W1-sweep.log &)
```

Arm one 5-minute progress Monitor across all seven: stall if a dossier file does not exist by 15 minutes. All seven
orders share the byte-identical brief `orders/_dossier-brief.md` as their prefix, after the project PREAMBLE, so they
are cache reads. Outputs: `.paul/review/fable-5.2/dossier-S1.md` … `dossier-S6.md`, and `W1-sweep.md`.

### P0-3 — Fable ping (seconds of Fable)

Spawn `Agent(model: "fable")` with "Reply with only your exact model id." If the answer is not Fable 5.2, the fallback
is §6-a. Also ask Jason (**ASK 1**) for the usage panel's 5-hour % and weekly % now. This is the baseline for
calibration.

### P0-4 — Dossier gate (Opus, about 15 minutes total)

For each dossier, open three random Map lines and two "Already known" lines and check them against the code and git.
Any false line means rebuilding that dossier with a note saying what was wrong; do not hand a bad map to Fable. Also
check that each is under 30K tokens (characters / 4).

### F — Fable sections (S1 first, one at a time)

For each section, spawn **one** background subagent:

```
Agent(
  description: "Fable review S<n>",
  model: "fable",
  run_in_background: true,
  prompt: <the standing brief in §5, byte-identical> + "\n\nSECTION: S<n>. Dossier: .paul/review/fable-5.2/dossier-S<n>.md. Findings file: .paul/review/fable-5.2/S<n>-findings.md. W1 sweep (for context only): .paul/review/fable-5.2/W1-sweep.md"
)
```

Sections run **sequentially**: one Fable at a time keeps the usage readable and stops cleanly at a boundary. While a
section runs, Opus starts verification of the previous section on Kimi, so the two overlap.

**Calibration after S1 (ASK 2):** Jason reads the panel again. Let `x` = the weekly % S1 used, and `w` = the 5-hour %
it used. Then:

- **Sections that fit in this allowance** ≈ (50% − weekly Fable % already used) / x. **Sections per 5-hour window** ≈ 90 / w.
- Run until either budget would be exceeded by the next section. Then use the **Fable reset** (**ASK 3**: Jason
  triggers it in Settings → Usage) and continue.
- If both allowances are spent before S3 is done, **ASK 4**: offer one full reset for the rest of S1–S3. S4–S6 never
  use a full reset; they fall back to Kimi.

Each Fable section returns only `done, <N> findings, coverage <c>/<t>`. If coverage is below 80%, do not rerun it on
Fable; the uncovered hotspots go to the Kimi fallback.

### V — Verification (Kimi K3.1 Pro, pipelined)

Create one worktree for all verification tests:
`orca worktree create --repo path:"$(git rev-parse --show-toplevel)" --name fable-verify --base-branch main --setup skip --json`
(branch `review/fable-verify`). For each finding `S<n>-F<k>`, write an order of `orders/_verify-brief.md` + the
finding's text, and dispatch it in that worktree:

```sh
cat .paul/review/fable-5.2/orders/_verify-brief.md <(sed -n '/^### F<k>/,/^### F/p' .paul/review/fable-5.2/S<n>-findings.md) \
  > /tmp/verify-S<n>-F<k>.md
(cd ~/orca/workspaces/OhYesMLX/fable-verify && CC_ROUTE=kimi-pro CC_AGENT_MAX_TURNS=120 \
   ~/Dev/active/OhYesMLX/.paul/orders/dispatch.sh implement /tmp/verify-S<n>-F<k>.md /tmp/verify-S<n>-F<k>.log &)
```

Parallelism: up to 4 Python verifiers at once. Swift verifiers run **one at a time**, because SwiftPM locks `.build`.
Each writes `.paul/review/fable-5.2/verify/S<n>-F<k>.md`, ending in a `VERDICT:` line, **inside the worktree**
(`~/orca/workspaces/OhYesMLX/fable-verify/…`). Opus reads them there and copies the reports into the main checkout with FINDINGS.md.

Opus then:
- re-runs every CONFIRMED red test itself;
- reads every REFUTED verdict, and every High, against the code;
- writes `.paul/review/fable-5.2/FINDINGS.md`: ranked, each finding with its verdict, test, and severity after
  check.

**A Fable finding is not a fact until its verifier and Opus say so** (AGENTS.md).

### After

Group CONFIRMED findings into PAUL plans (audit → APPLY with `kimi-pro` workers, `deepseek` for trivial ones → two-axis
review → unify). The red tests on `review/fable-verify` become each fix's first test. P5-11 is already known; it joins
the S4 fixes.

## 5. The standing brief for every Fable section (byte-identical; it is the cached prefix)

```
You are the final, most senior reviewer of OhYesMLX (OYMLX), a Mac tool that benchmarks local LLM serving
and now ships a SwiftUI onboarding app over a Python localhost backend. Your job is judgment, not reading:
cheaper agents already mapped this section for you in a dossier.

Rules of the project that outrank convenience: vary one thing at a time; a fast cell that emits garbage
is a FAILED cell; never report an unreconciled number; one definition of everything; nothing the user owns
changes without consent and restore; the API is localhost-only, token-guarded, and its client is not trusted.

Token discipline:
1. Read the dossier named below first, completely.
2. Read source ONLY at the ranges the dossier lists, or to chase one specific lead (say which).
   Never read a file over 400 lines whole. Never read tests unless a finding depends on one.
3. Do not re-report anything in the dossier's "Already known" list.
4. Stop when you have covered every hotspot and open question. Breadth over polish.
5. Write ONLY the findings file named below. Do not edit code, run servers, engines, or test suites.

Report ONLY defects a senior engineer would act on: correctness, security, data loss, a misleading
number or label, a race, a broken contract, a missing safety check. No style, no naming, no
"consider adding docs". For each finding, write to the findings file:

### F<k> — <one-line claim>
- Severity: High | Medium | Low   (High = harm to the user's Mac/data/trust, or a wrong published number)
- Where: path:line[-line]
- Failure scenario: concrete inputs/state -> wrong outcome
- Evidence: the code path, quoted minimally
- Confidence: 0-100, and what would raise it
- Fix direction: one or two sentences
- Test idea: the smallest test that would fail today

End the file with "Coverage:" listing each dossier hotspot and open question as covered / not covered.
Return to the orchestrator only: "done, <N> findings, coverage <c>/<t>".
```

## 6. Fallbacks

- **a. `model: "fable"` is not Fable 5.2.** Jason opens a Fable 5.2 Claude Code session in this repo (confirm the exact id
  in `/model`) and pastes §5 plus the section line, once per section. Opus keeps P0, V and FINDINGS.
- **b. The promotion window closes, or the budget runs out.** The remaining sections run on Kimi with the same §5 brief and
  dossier as an order file: `CC_ROUTE=kimi-pro .paul/orders/dispatch.sh implement <§5 + section line>.md`. It is
  `implement` (not `review`) because it must write its findings file. Their findings are marked "non-Fable" in
  FINDINGS.md.
- **c. Kimi rate-limited or failed the bench.** Verification on `mimo-pro`, red tests on `deepseek`.
- **d. A bad dossier.** Rebuild it; never let Fable rediscover the map.

## 7. Done means

- `FINDINGS.md` exists, every finding has a verdict, and Opus has re-checked every High and every REFUTED.
- The `review/fable-verify` branch holds one red test per CONFIRMED-with-test finding (unmerged).
- STATE.md gains a row for the review. HANDOFF names the fix plans to write. The Deep Wiki project page's next step
  is updated, and a decision note is proposed to Jason (not written) if the review changes direction.
