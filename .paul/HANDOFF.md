---
description: "OhYesMLX — session handoff, 2026-09-17 (v1 closed, ready for v2 Track 1 JANG planning)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-17 (Transition to v2: Track 1 JANG Study)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 is 100% closed and published.** All core milestones and both immediate closeout candidates (Candidate 3: Non-hybrid KV cache split; Candidate 4: vMLX 32k watchdog prefill resolution) are complete, verified, and committed on `origin/main` (HEAD: `060ab23`).
- **Tests:** 495 tests pass (`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`).
- **Ports & Processes:** All ports (1337, 8080, 8081, 8100, 8000) are free. No background runtimes or sweeps are active.
- **Osaurus State:** Jason's host Osaurus settings (`~/.osaurus/config/server-runtime.json` and `server.json`) are byte-exact to baseline (`cache.prefix.enabled: true`, `cache.blockDisk.enabled: true`, `modelIdleResidencyPolicy.seconds: 30`).
- **Deep Wiki:** Project page active at `/Users/jrazz/Documents/ObsidianNotes/10 Wiki/Projects/OhYesMLX/OhYesMLX.md`; vault validation passes.

---

## Immediate Next Task: v2 Track 1 (The JANG Study)

We are entering **v2**, starting with **Track 1: The JANG Study** as prioritized in `.paul/v2-options-note.md`.

### Core Problem to Solve
JANG formats (`JANG_4S`, `JANG_2L`, `JANGTQ`) achieved high throughput in earlier tests, but are proprietary bundles supported only by vMLX and Osaurus. In v1 they could not be placed on the format axis without violating the single-variable rule.

### The v2 Study Design
Design a single-variable study holding runtime constant:
1. **JANG vs Portable in vMLX:** Compare `Qwen3.5-4B-JANG_4S` against `Qwen3.5-4B-4bit` (stock) and `Qwen3.5-4B-oQ4` inside vMLX.
2. **JANG vs Portable in Osaurus:** Compare the same models/formats inside Osaurus.
3. **Cross-Runtime JANG:** Compare `JANG-on-vMLX` vs `JANG-on-Osaurus`.

---

## Orchestration & Delegation Protocol (Command Code & Orca)

As the manager and orchestrator:

1. **Prompt Cache Preservation ($0.003/M vs $0.15/M — 50x discount):**
   - Delegate implementation/research to `cc-agent` workers on `deepseek/deepseek-v4.1-flash`.
   - **Always dispatch via:** `.paul/orders/dispatch.sh <role> <order-file>` (roles: `implement`, `refactor`, `test`, `explain`, `review`).
   - `dispatch.sh` prepends `.paul/orders/PREAMBLE.md` verbatim.
   - **NEVER** edit `PREAMBLE.md` without necessity.
   - **NEVER** prepend anything to `PREAMBLE.md`. Order-specific text goes strictly AFTER it so DeepSeek hits prompt cache reads at $0.003/M.
   - Set `CC_AGENT_MAX_TURNS=200` for non-trivial tasks.

2. **Delegation & Verification Contracts:**
   - Every order must specify: clear acceptance criteria, the exact files the worker may touch, and "touch nothing else."
   - **Worker reports are NOT evidence.** The coordinator must personally inspect the git diff and observe a green test run before accepting work or closing orders.

3. **Standing Invariants:**
   - **Vary one thing at a time:** The defining rule of the project.
   - **Osaurus KV Cache Guarantee:** Jason approved controlling Osaurus on the strict condition that his KV caches (`prefix` and `blockDisk`) and idle residency are restored byte-exact upon completion. Verify with `cmp`.
   - **Process Safety:** Never sweep using the bare name `osaurus` (Jason's `osaurus mcp` must stay running). Sweep by full binary path: `^/Applications/osaurus.app/Contents/MacOS/osaurus`.
   - **Thermal & Contention:** Exactly one model resident in memory at a time. Never run background jobs, tests, git operations, or downloads while measuring a cell.
   - **Deep Wiki:** Consult `10 Wiki/` and `20 Records/` before planning. End final reports with `Deep Wiki: <files changed>` or `Deep Wiki: no durable change`. Never commit or push the Obsidian vault.

---

## Prompt for Next AGY Session

Copy and paste the following prompt when starting the new session:

```text
Please read .paul/HANDOFF.md, .paul/STATE.md, and AGENTS.md. You are the manager and orchestrator for OhYesMLX. 

v1 is completely closed and published. We are now beginning v2 planning, starting with Track 1: The JANG Study.

Please:
1. Review the JANG study requirements in .paul/HANDOFF.md and .paul/v2-options-note.md.
2. Verify our existing on-disk JANG artifacts (e.g. in ~/.cache/huggingface/hub/ and ~/MLXModels/) for Qwen3.5-4B and LFM2.5-8B-A1B.
3. Formulate the single-variable test matrix for JANG-in-vMLX vs portable formats and JANG-in-Osaurus vs portable formats.
4. Prepare the v2 Phase 1 study design and plan before running any measurements.

Remember to utilize orca orchestration and delegate implementation/writing tasks to cc-agent via .paul/orders/dispatch.sh, preserving the byte-identical PREAMBLE prefix for the $0.003/M cache read hit rate. Observe all standing invariants (single variable, Osaurus cache restoration guarantee, quiet machine during measurements).
```
