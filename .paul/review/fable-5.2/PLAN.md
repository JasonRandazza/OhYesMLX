---
description: "Plan for a token-efficient whole-project review of OYMLX with Claude Fable 5.2 as the reviewer, Opus as orchestrator and Command Code workers for preparation and verification"
type: Plan
about: "OhYesMLX"
---

# Fable 5.2 review of OYMLX — plan

Written 2026-11-14 by the Opus coordinator at Jason's request. Execute it in the session after Jason's
to-do list (HANDOFF "Start here") is done. This is a review, not a phase: its output is a verified findings
list, and fixes go through normal PAUL plans afterwards.

## 0. The constraint that shapes everything

**The Pro-plan Fable 5.2 promotion ends Sunday 2026-11-16 at 11:59 PM PT.** Until then Fable 5.2 runs inside
the plan for up to 50% of the weekly limit. Afterwards, Pro bills Fable to usage credits (Anthropic help article
"Claude Fable 5.2 launch offers"; Notebookcheck 2026-11-09). Jason reports 5 resets available. Confirm that
count in Settings → Usage before relying on it: the published offer gives Pro one reset and Max/Ultra one
to three, which expire 2027-03-08.

Two consequences follow:

- **Every Fable token must go to judgment, not reading.** Command Code workers do all the reading, mapping and
  verification, and they cost nothing scarce.
- **Preparation must be finished before the first Fable call.** Dossiers are built in parallel by workers, and
  Fable sections then run back to back in priority order, so the most valuable sections land first if the
  window closes.

## 1. The shape: Opus orchestrates, Fable reviews in sections, workers prepare and verify

**Not one massive pass.** The source is about 16.5K lines of Python, 5.7K of Swift and 2K of packaging scripts
(about 250K tokens before 26K lines of tests). An agentic reviewer re-reads as it goes, so a whole-repo pass would
be millions of tokens, mostly re-reads. It would also run against context limits on the way. One failure would
lose everything, and it could not stop at a reset boundary.

**Fable is not the orchestrator.** Orchestration is waiting, routing and bookkeeping, and doing that at Fable's
price wastes it. The Opus session that runs this plan spawns Fable once per section as a subagent:
`Agent(model: "fable", run_in_background: true)`. Opus reads only the findings file each one writes.

**Section sizing.** A section is sized so Fable reads a curated dossier of about 15–25K tokens, plus about
40–80K tokens of targeted source ranges the dossier names. It writes one findings file.

| Role | Who | Why |
|---|---|---|
| Orchestrator | Claude Opus 5.5 (this plan's session) | It routes, gates and makes the final verdicts. It reads findings, not code. |
| Reviewer | Claude Fable 5.2, one subagent per section | The scarce, high-judgment pass, aimed at what workers cannot see. |
| Dossier builders | Command Code `implement --route mimo-pro` (MiMo v2.6 Pro, an approved route) | Mechanical but careful reading: maps, contracts, known issues. 1M context, about $0.0036/M cache read. |
| Verifiers | Kimi K3.1 Pro if Jason approves a trial route; otherwise `mimo-pro` | Each finding is reproduced with a failing test, or refuted with evidence. |
| Red-test writers / fixers | `implement` (DeepSeek V4.1 Flash, the default) | Proven on this repo (18/18), cheapest, and strongest on Vals among the approved routes. |

### Worker model choice (research 2026-11-14)

Approved Command Code routes are a closed world (`fleet-provider-routing`): only `deepseek`, `mimo`,
`mimo-pro`, `glm` and the explicit-only routes may run. Kimi K3.1 Pro and Qwen 3.8 Max are available in
Command Code but **not approved**; adding one is a policy change that needs Jason's yes.

| Model (Command Code id) | Vals Index (Nov 9, 2026) | Cost per Vals task | Notes |
|---|---|---|---|
| Kimi K3.1 Pro (`moonshotai/kimi-k3.1-pro`) | 62.5% | $6.44 | #4 on Artificial Analysis (55.1). Strongest on Terminal-Bench 4.0 (65.7–67.2). $2 / $10 per M. **Best verifier candidate.** |
| DeepSeek V4.1 Flash (`deepseek`, approved) | 61.3% | $0.66 | Beats both Qwen Max and MiMo Pro on Vals at a fraction of the cost; this repo's proven implementer. |
| GLM 5.3 | 59.9% | $8.52 | Not a candidate (price). |
| Qwen 3.8 Max 0902 (`qwen/qwen3.8-max-0902`) | 59.1% | $8.73 | **Dominated**: below Kimi and DeepSeek Flash, and the most expensive per task. Max Prime is the same model served faster, so no gain in quality. Skip both. |
| MiMo v2.6 Pro (`mimo-pro`, approved) | 57.8% | $0.43 | Cheapest strong long-context reader; already this repo's `review` route. |

Sources: Vals AI Index leaderboard (vals.ai, 2026-11-09), Artificial Analysis via benchlm/benchmarklist, the
OpenRouter comparison page for pricing. These are general benchmarks; this repo's own answer is
`scripts/fleet/model-bench.py` (see step P0).

**Recommendation:** use MiMo v2.6 Pro for dossiers (approved; reading is its strength and it is very cheap), and
Kimi K3.1 Pro for verification if Jason approves a trial route. Skip Qwen 3.8 Max and Max Prime. Without Kimi,
verification runs on `mimo-pro` and red tests on `deepseek`, and the plan still works.

## 2. Sections, in priority order

Priority is risk times value: what could hurt a user's Mac first, then the project's core value (numbers
that are true), then the newest code.

| # | Section | Code (lines) | The questions Fable is asked |
|---|---|---|---|
| S1 | **Security and trust boundaries** | server.py 1051, the security-relevant ranges of engines/fetch/cli/runtimes, the Swift launcher, threat-model §§1–10 | Can anything on or off this Mac drive the API, an installer, a download or a file write to do harm? Are the T-findings really closed? Is anything missing from the threat model? |
| S2 | **Measurement integrity** (the core value) | transport 519, measure 1603, coherence 94, sample 303, token_counter 116, the summary/grid paths of report.py | Can a published or quick number be wrong, mislabelled, attributed to the wrong artifact or run, or survive a failed coherence gate? Does "vary one thing" hold in code? |
| S3 | **The SwiftUI app** | app/Sources 5.7K | State-machine races, concurrency (MainActor, async), the launcher's process handling, honesty of every label, accessibility, fidelity to DESIGN.md. |
| S4 | **Onboarding backend** | engines 1340, fetch 1310, quickbench 1059, catalog 305, recommend 209, hardware 167 | Install, download and evict correctness under failure; quickbench's one-axis rules; the fit math; disk safety. |
| S5 | **Runtime lifecycle and host safety** | runtimes.py 3811, osaurus_settings 411 | Ports, orphans, the Osaurus pin/restore, the ledger, never touching the user's processes. |
| S6 | **Packaging and release** | build_app/check_bundle/fetch/make_sbom/smoke scripts, Info.plist, gatekeeper.md | Signing, the SBOM's truth, translocation, what a user's first launch actually meets. |

Not given to Fable: docs-versus-code drift and tests that cannot fail. Workers do those as a cheap sweep (W1),
and Fable sees only the summary in each dossier.

If the window closes early, S1–S3 are the minimum worth having. S4–S6 then fall back to a Kimi or `mimo-pro`
review using the same dossiers.

## 3. Steps

### P0 — before any Fable call (workers only; about 1–2 hours of wall time, no Fable tokens)

1. **Kimi trial route** (only if Jason approved it): run `scripts/fleet/model-bench.py` on
   `moonshotai/kimi-k3.1-pro` with the standard three tasks and price it with `route-cost`. Add it as a trial route
   per the fleet skill's policy-change steps (`paid-routes.sh`, installer, DECISIONS.md). If it fails the bench,
   use `mimo-pro`.
2. **Dossiers, S1–S6, in parallel**: one `cc-agent implement --route mimo-pro` per section, each writing
   `.paul/review/fable-5.2/dossier-S<n>.md`, at most about 25K tokens each, in a fixed structure:
   - **Map**: every file and function in scope with `file:line` ranges, from `graphify query`/`explain`.
   - **Contracts**: the pinned shapes and rules that bind this code, as pointers into `docs/interfaces/*` and
     AGENTS.md, quoting only the binding sentences.
   - **Already known; do not re-report**: accepted risks (threat-model §9), deferred items (STATE, PHASE
     summaries), and fixed findings from every `.paul/review/*` round, each with its commit.
   - **Hotspots**: the 10–20 ranges where a bug would hurt most, each with one line on why.
   - **Mechanical scan results**: grep findings (subprocess with `shell=True`, `os.system`, unbounded reads, `chmod`,
     `tempfile` misuse, `force_` unwraps, `try!`, `DispatchQueue.main.sync`, and so on), each with a location.
   - **Test inventory**: which tests guard which hotspot, and which hotspots have none.
   - **Open questions for Fable**: 5–10 specific, falsifiable questions.
3. **W1 sweep** (`mimo-pro`, parallel): docs-versus-code drift for `docs/interfaces/*` against the code, and a list of
   tests that cannot fail (asserting a fake's echo, never red-checked). It writes `.paul/review/fable-5.2/W1-sweep.md`.
   Workers are not trusted blindly: Opus spot-checks three claims from each dossier against the code before the
   dossier goes to Fable. A dossier with a false map line is rebuilt.

### F — Fable sections (S1 first, then in order)

For each section, Opus spawns one background Fable subagent with the **standing brief** (§4) followed by one
line naming the section and its dossier. The brief is byte-identical across sections, so it is a cached prefix.
Fable writes `.paul/review/fable-5.2/S<n>-findings.md` and returns only "done, N findings".

Between sections, Opus checks plan usage (Jason can read Settings → Usage). Calibrate after S1: if S1 used X%
of the window, run sections back to back until the window is about 80% spent, then use a reset. Never start a
section that cannot finish in what is left; a half-run section wastes its reads.

### V — verification (pipelined: starts as soon as each section's findings land)

For each finding, one verifier worker (Kimi trial route, or `mimo-pro`) writes
`.paul/review/fable-5.2/verify/S<n>-F<k>.md`, ending in one of:

- **CONFIRMED**: a red test that fails on `main`, written in an Orca worktree by an `implement` worker. It is
  not merged; the fix comes later.
- **CONFIRMED (no test possible)**: concrete evidence (a command and its output, or a code path), with a reason.
- **REFUTED**: the code or test that shows the claim is false.

Opus reads the verdicts, re-checks every High and every REFUTED one personally, and writes the final ranked list
`.paul/review/fable-5.2/FINDINGS.md`. This is AGENTS.md's rule applied to Fable too: a reviewer's report is not
evidence.

### After — fixes

Group confirmed findings into PAUL plans (audit → APPLY with `implement` workers → review → unify), as in Phase 5.
None of this needs Fable, so it can happen after the promotion ends.

## 4. The standing brief for every Fable section (keep it byte-identical)

```
You are the final, most senior reviewer of OhYesMLX (OYMLX), a Mac tool that benchmarks local LLM serving
and now ships a SwiftUI onboarding app over a Python localhost backend. Your job is judgment, not reading:
cheaper agents already mapped this section for you.

Rules of the project that outrank convenience: vary one thing at a time; a fast cell that emits garbage
is a FAILED cell; never report an unreconciled number; one definition of everything; nothing the user owns
changes without consent and restore; the API is localhost-only, token-guarded, and its client is not trusted.

Token discipline:
1. Read the dossier named below first, completely.
2. Read source ONLY at the ranges the dossier lists, or to chase one specific lead (say which).
   Never read a file over 400 lines whole. Never read tests unless a finding depends on one.
3. Do not re-report anything in the dossier's "Already known" list.
4. Stop when you have covered every hotspot and open question. Breadth over polish.

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

End the file with "Coverage:" listing each hotspot and open question as covered / not covered.
Return to the orchestrator only: "done, <N> findings, coverage <c>/<t>".
```

## 5. What this costs, roughly

- **Fable:** six sections at about 60–120K input (mostly first reads, then cache) plus 5–15K output each. The real
  number comes from the S1 calibration, not from this estimate.
- **Opus:** small; it reads about six findings files and the verdicts, plus spot-checks.
- **Command Code:** six dossiers at cents each on MiMo Pro, W1 at cents, verification at about $0.5–3 per
  section on Kimi. Jason has a large Command Code allotment; it is the right place to spend.

## 6. Fallbacks

- If `Agent(model: "fable")` does not resolve to Fable 5.2 (check `/model` in Claude Code first), Jason starts
  a Fable 5.2 Claude Code session in this repo (confirm the exact model id in `/model`; it is probably `claude-fable-5-2`) for each section and pastes the standing brief plus the section line.
  Opus continues to orchestrate the dossiers and verification.
- If the promotion window closes mid-run, the remaining sections run on Kimi K3.1 Pro (or `mimo-pro`) with the same
  brief and dossiers, and their findings are marked "non-Fable".
- If a dossier is wrong, rebuild it. Do not let Fable spend tokens rediscovering the map.
