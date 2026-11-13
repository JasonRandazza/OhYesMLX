---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-03: v5.0 Phase 4 complete (reviewed, UAT 8/8); next is planning Phase 4.5 security hardening"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-03

> Read this, then `.paul/STATE.md` (Current Position, Decisions 138-141, Blockers), then
> `.paul/phases/v5-onboarding/PLAN.md` (the Phase 4.5 section and its process gates), then
> `.paul/phases/v5-onboarding/PHASE-4-SUMMARY.md`, then `AGENTS.md`. STATE wins on conflict.
> Previous handoff (Phase 4 built, one gap open): `.paul/archive/2026-11-02-handoff-phase-4-built.md`.
> Jason calls the project **OYMLX**.

## Where things stand

v5.0 turns OYMLX from a CLI benchmark into a guided Mac app: a stdlib Python backend behind a guarded localhost
JSON API, with a SwiftUI shell to come in Phase 5. **Phases 0-4 are complete on `main`; 1164 tests pass; the
working tree is clean** (last commit `244ce57` plus this handoff).

This session (2026-11-03) closed Phase 4:

| Step | Outcome | Commit / record |
|---|---|---|
| 04-03c quick fix | `osaurus_settings.pin` backs up and restores the drift guard's baseline (`config/osaurus-settings-baseline.json`, or a `baseline.absent` marker) with the two Osaurus configs; quickbench pins against that baseline; `scripts/osaurus-pin.sh` lost its `git checkout` lines | `ad73b76`, `04-03c-SUMMARY.md` |
| Live quickbench re-run | All five engines PASS on Qwen3.5-2B-4bit, Osaurus included (131.3 tok/s); oMLX won stage A (175.3), oQ4 on oMLX best (178.6); Osaurus configs and baseline byte-exact under `cmp` | `04-03c-SUMMARY.md` |
| Hero-model bytes question | Closed with proof, no caveat: the Qwen3.5-4B and LFM2.5-8B-A1B safetensors are the pinned tensors, reordered (pinned header fetched by HTTP range, local tensors streamed in pinned order, sha256 equals the revision's LFS oid) | STATE Blockers row "Resolved 2026-11-03" |
| Phase 4 code review | Standards + Spec workers (`cc-agent review`, MiMo pro); 9 findings, each verified against the code, fixed in one worker pass | `6c84f5c`, `.paul/orders/v5-review-4-*` |
| UAT (`/paul:verify`) | Jason drove `ohyesmlx app` with curl: 8 of 8 pass; one known minor issue logged | `04-UAT.md` |
| Phase close | `PHASE-4-SUMMARY.md`; STATE, ROADMAP and the vault project page point at Phase 4.5 | `244ce57` |

The review's most important find: `fetch` and `engines` refusals sent `error` without `done`, and the server
frees its single job slot only on `done`, so any refused job (an unknown repo, an engine already installed)
blocked every later job with 409 until restart. Server tests had used fakes that always sent `done`. Fixed in the
modules, backstopped in `server._run_job`, and covered by a test that drives the real `fetch.evict` through the
job routes. Jason confirmed it live in UAT check 6.

## Do next

1. **Plan Phase 4.5, security hardening** (`/paul:plan`). Scope is in PLAN.md's Phase 4.5 section: review the
   whole backend as an attack surface before the SwiftUI app ships (the localhost API's guard, job args and body
   limits; installer subprocesses and their environment; downloader URL and path handling and the HF cache;
   files written under Application Support, their permissions and symlinks; the ledger and logs; what a bundled
   Python exposes). Output: a threat model, findings fixed with tests, and a checklist Phase 5 packaging must keep.
   Process gates: `/paul:audit` on the plan before APPLY, `code-review` and `/paul:verify` after.
2. Carried items to fold into that plan (all listed in `PHASE-4-SUMMARY.md` "Deviations"):
   - clean-account smoke: a throwaway standard user (`sudo sysadminctl -addUser oymlxtest`) driven with
     `sudo -u oymlxtest -H … app`, then deleted; Jason picks when;
   - a pip step outliving a server shutdown (the 120 s wait cannot interrupt a running step);
   - a per-job cap on SSE stream readers;
   - the Osaurus app rewriting its config mid-run;
   - fetch's post-transfer snapshot-conflict check;
   - where the Osaurus baseline lives in a packaged app (no repo `config/` there);
   - the Swift client never logging the token;
   - **UAT-001**: `fetch.downloaded` reports the two hero models as not downloaded because it compares sizes,
     so the app would offer a 3.1 / 4.8 GB re-download of bytes already present. Options: accept a
     tensor-equivalent file (header splice + hash, as 2026-11-03 did), or leave it, since only files rewritten
     outside the downloader can hit it.

## Decisions waiting on Jason

- vMLX 1.6.82 stays untested (the same-build canary read -5.5%, session variance; 1.6.59 has no baseline).
- Older, unchanged: Decision 136 (OptiQ 0.5.x vs 0.7.8 tables), `mtplx-wip`, the 0.3.1 bump, the README rewrite,
  the v5.0 vault decision note, an Apple Developer account, `scripts/lab-copies-wizard.sh`.
- Whether `ohyesmlx` should be installed as a real dev command (see the trap below); Jason has not asked for it.

## Recipes and traps learned this session

- **`ohyesmlx` is not on PATH.** Run the CLI as
  `~/.local/share/ohyesmlx/test-venv/bin/python -c 'import sys; from ohyesmlx.cli import main; sys.exit(main())' <subcommand> …`
  from the repo root. Jason hit `command not found` during UAT; give him this form, not the bare name.
- **python.org's Python 3.14 has no CA bundle** (`CERTIFICATE_VERIFY_FAILED` on any HTTPS fetch). Use the test
  venv's Python for scripts that touch the network.
- **Quickbench live run** (needs Jason's go, quiet machine, Osaurus app closed, ~10 min plus the sibling download):
  copy `~/.osaurus/config/server{,-runtime}.json` and `config/osaurus-settings-baseline.json` first; a script that
  exports the mlx-lm venv onto PATH (`~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`) and `HF_HUB_CACHE=<scratch>`,
  downloads the chosen model with `fetch.download(repo, True)` *before* the run, then `launchctl bootout
  gui/$UID/com.dualnode.controlhub.{dashboard,agent}`, runs `quickbench --repo … --osaurus --yes`, and
  re-bootstraps both plists from `~/Library/LaunchAgents`. Afterwards `cmp` all three files, check no backup dir
  (`~/.osaurus/config.phase4-orig`, `…/OhYesMLX/quickbench/osaurus-backup`), no Osaurus app, ports free, the real
  HF cache listing unchanged; delete the scratch cache. The 2026-11-03 run took 1956 s against a 630 s estimate:
  the estimate assumes 20 MB/s and the stage-B sibling came down at ~7 MB/s.
- **Wi-Fi drops during a download are survivable**: `fetch` keeps a `.incomplete` and resumes with a Range
  request, but its four retries span ~3.5 s, so a longer outage ends the call; re-run it to resume.
- **A green suite does not test module contracts the fakes assume.** Prefer one test per contract that drives a
  real module through the server (the evict-job test is the pattern).
- **Workers**: the `implement` worker (DeepSeek v4.1 flash, `CC_AGENT_MAX_TURNS=300`) ran 04-03c in 47 turns and
  the 9-fix pass in 109. Its "missing definitions" warnings were renames every time; verify against `git diff`.
  It flags out-of-scope stale docs rather than touching them; the coordinator fixes those.
- **Review orders** that worked: scope by commit range plus an explicit read list (reviewers cannot run git),
  a "do not re-report" list of known deviations and Phase 4.5 items, and "under 600 words". `.paul/orders/
  v5-review-4-{standards,spec}.md` are the pattern.
- Pytest: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q`. A post-commit hook rebuilds
  graphify.
