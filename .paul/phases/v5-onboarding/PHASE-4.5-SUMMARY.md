---
description: "v5.0 Phase 4.5 reconciled: backend threat-modelled, 16 findings fixed or accepted, installers hash-pinned and wheels-only, clean-account smoke 21/21"
type: Summary
about: "OhYesMLX"
---

# Phase 4.5 Summary — Security hardening (UNIFY, 2026-11-13)

Inserted 2026-11-02 (Jason) so the whole v5.0 backend was reviewed as an attack surface before the SwiftUI app
hands it to people who never open a terminal. Split model → fix → smoke (Jason, 2026-11-03).

## Delivered

| Plan | Delivered | Commits |
|---|---|---|
| 045-01 | `docs/threat-model.md`: assets, actors, boundaries, 102 entry-point hits reconciled, live probes; 6 medium + 10 low findings, none high; carried items dispositioned; §10 Phase 5 packaging checklist (P5-1..P5-12) | see `045-01-SUMMARY.md` |
| 045-02a | Server + lifecycle: T-02/03/04/05/08/09/10/11 (startup recovery, orphan-engine ledger, guard and body limits, Application Support 0700, PATH, token never logged) | `4b35ef8`, `9bc9388`, `6c4d616` |
| 045-02b | Installers + fetch: T-01 hash-pinned pip (`--require-hashes`, `--only-binary :all:`), T-07 isolated installer, T-12 validated lab paths, T-06 evict under the download lock, T-13 per-repo evict containment, T-16 snapshot conflict before transfer; ledger follows its cache | `a031ad4`, `fb4e61c`, `7393715` |
| 045-03 | Clean-account smoke as `oymlxtest` under launchd's PATH, 21/21; fixed optiq install without Homebrew SDL (pygame omitted, `--no-deps`, wheels-only) and app engines unable to start outside a developer's shell (`runtimes.ENGINE_BUNDLE_EXECUTABLES`) | `743ada3`, `369f180`, `f7c22e0` |

Tests 1164 → 1329. Every plan had an enterprise audit before APPLY and a Standards + Spec code review before
UNIFY. Live evidence lives with each plan (`045-03-evidence/` for the smoke).

## What the phase taught

- **The account you develop in hides the defects a user meets first.** Both 045-03 defects (optiq needs SDL;
  app engines need a shell PATH) passed every test and every live check on Jason's account. Only a fresh
  account under launchd's PATH showed them. Phase 5's install smoke should reuse `scripts/smoke_clean_account.sh`.
- **An approved exception can be wrong for the user it was approved for.** The 2026-11-10 pygame source-build
  exception was reasonable on the evidence then; the clean account showed it could never work without Homebrew.
  It was replaced the same day by omitting pygame entirely, which also removed the only unhashed fetch.
- **A live check's premise can be false.** 045-02b AC-5 assumed the host ledger held a real download; it held
  scratch residue. The code met the AC; the plan's picture of the host was wrong (residue removed in 045-03).
- **Workers need a pace rule and a map.** One dispatch read for 30 minutes and wrote nothing. PREAMBLE now
  carries "Code graph — use it first" and "Pace", and every dispatch has a 5-minute progress monitor.

## Carried forward (to Phase 5 or later)

- §10 checklist P5-1..P5-12 binds Phase 5 packaging (P5-3/P5-4 verified against Homebrew Python only; the
  bundled interpreter must re-verify them).
- `/engines` reports vMLX installed for an account that cannot execute its bundle (multi-user Macs only).
- Accepted risks in threat-model §9 (lock stale-reclaim race; global pip config under `--isolated`).
- The four remaining atomic-write copies (`osaurus_settings`, `runtimes`, `measure`, `quickbench`).
- `/etc/sudoers.d/oymlxtest` stays until Jason removes it (`sudo rm`); Phase 5's install smoke could reuse it.

## Next

Phase 5 — SwiftUI app and packaging. Process gate: `prototype` (screen flows) before planning. No Apple
Developer account yet (Jason, 2026-11-13), so T5.6 plans for an unsigned / ad-hoc-signed build and leaves
notarization as a gated step.
