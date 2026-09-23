---
description: "OhYesMLX — session handoff, 2026-09-23 evening (v3.1 Hardening: Phase 1 complete)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-23 evening (v3.1 Hardening, Phase 1 complete)

> Read this, then `.paul/STATE.md` (Decisions 117–121), then `AGENTS.md`. STATE wins on conflict.

## Where things stand

- **v0.3.0 released** (GitHub Releases, not PyPI). Milestone **v3.1 Hardening** is in progress.
- **Deep review done:** `.paul/review/2026-09-23/SUMMARY.md` is the verified list (IDs A1–F).
  It had 38 confirmed findings, 1 fabricated (docs F10) and 3 that were not defects.
- **Phase 1 complete** (commits `ef01396`, `5313062`, 530 tests):
  - A1 FAIL rows print no request figures.
  - A2 one-chunk streams have a zero window, and decode/prefill/ITL (so drift and warmup too) refuse below 2 content deltas.
  - B1–B4 residency: stray Osaurus app refusal by executable path, lsof-unknown, cleanup and SIGKILL failures raise.
  - C1–C4 persist on failure or Ctrl-C.
  - A6 OptiQ sampler flags pinned.
  - D2 harness sha in the header.
  - E1–E3 tests that can fail.
- **Operational change:** every run now **refuses to start while an Osaurus app process is alive**.
  Quit Osaurus before measuring.
- **Delegation:** the fleet default is now `gpt-6-luna` (Jason's decision, route trial still owed; see
  `~/AI/orca-agentic-workflow-efficiency` DECISIONS 2026-09-23). Luna workers finish, but their logs
  often contain only `EXIT 0`. Verify from `git diff` and a red-check, never from the report.
  One reviewer fabricated a finding.

## Next moves

1. **Phase 2 (contract decisions, already made):**
   - A5 (Decision 119): label rows timed on the reasoning channel using `transport.timing_channel(obs)`,
     and amend AGENTS.md's TTFT definition.
   - A7 (Decision 120): runtime-axis readings print no ordering for `peak_mb`/`cold_load_s`.
   - D1: end-to-end latency P50/P90/P99 from `total_s`.
   - D3: `unknown: …` runtime versions refused by the join.
   - All four touch `report.py` (A5 and D1 also `measure.py`), so dispatch them as one order.
2. **Phase 3:** caveats on the script-based v3 papers (Decision 121), `probe_grid*` LOADS requires
   coherence (A4), and `docs/interfaces.md` / README drift (F).
3. **Phase 4:** re-run the v3 script studies through the harness (needs a quiet machine).
4. The Luna route trial is owed (roadmap item 11 in the infra repo).
