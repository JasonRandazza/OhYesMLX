---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-02: v5.0 Phase 4 built (server, jobs, quickbench); one quickbench gap open"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-02

> Read this, then `.paul/STATE.md` (Decisions 138-141 and the audit rows), `.paul/phases/v5-onboarding/PLAN.md`
> (Phase 4 notes, Phase 4.5), then `AGENTS.md`. STATE wins on conflict.
> Previous handoff (Phases 0-3 built): `.paul/archive/2026-11-01-handoff-phases-0-3-built.md`.
> Jason calls the project **OYMLX**.

## Where things stand

v5.0 turns OYMLX from a CLI benchmark into a guided Mac app: a stdlib Python backend behind a guarded localhost
JSON API, with a SwiftUI shell to come (Phase 5). **Phase 4 is built on `main`; 1144 tests pass.** One plan,
04-03b, closed with a known gap, and the phase-end code review has not been run.

| Plan | What | Summary |
|---|---|---|
| 04-01 | `ohyesmlx app`: 127.0.0.1 server, per-launch token, Host/Origin/token guard, GET /hardware /engines /recommendations | `04-01-SUMMARY.md` |
| 04-01b | `gpu_cores` from `ioreg` (30 on this M2 Max) | `04-01b-SUMMARY.md` |
| 04-02b | `Pick.downloaded`, tested-release install links, per-byte download progress | `04-02b-SUMMARY.md` |
| 04-02 | Jobs: install/download/evict, SSE stream, cancel, one job at a time | `04-02-SUMMARY.md` |
| 04-03a | catalog `base`/`siblings`, `quick: true` header pin, Python Osaurus pin/restore/recover | `04-03a-SUMMARY.md` |
| 04-03b | `quickbench` (module approved): stages A/B, light cells, job kind, `measured_here` | `04-03b-SUMMARY.md` |

Every plan has a PLAN, an AUDIT (except quick fixes) and a SUMMARY in `.paul/phases/v5-onboarding/`. Earlier the
same day: the Phase 2.5-3 review gate (9 findings fixed), T2.5.5 (pip constraints freezes), Osaurus 0.25.29 and
oMLX 0.7.3 adopted (Decision 139), `paul.toml` deleted.

## Do next, in this order

1. **Fix the quickbench Osaurus gap** (`04-03b-SUMMARY.md`, "Known gap"). Quickbench pins Osaurus against a
   baseline under Application Support; the runtime's drift guard reads the repo's
   `config/osaurus-settings-baseline.json`, so the pinned host reads as drift and the Osaurus cell is N/A. Fix:
   pin against the baseline the guard reads and back it up/restore it with the two config files. Then re-run
   quickbench with Jason's go (recipe below) and show the Osaurus cell PASS and the restore byte-exact. A small
   plan (quick-fix track) is enough.
2. **Phase 4 code-review gate** (the process gate in PLAN.md): `cc-agent review` Standards + Spec workers, as for
   Phases 2.5-3 (`.paul/orders/v5-review-25-3-*.md` are the pattern). Review the change since `1c157b0^`, the
   commit before 04-01's code. Verify each finding against the code, fix in one
   worker pass, commit.
3. **Plan Phase 4.5, security hardening** (PLAN.md has its scope). Carried items: clean-account smoke (a throwaway
   user driven with `sudo -u`, Jason's call when), a pip step outliving a server shutdown, per-job stream-reader
   cap, the Osaurus app rewriting its config mid-run, fetch's post-transfer snapshot-conflict check, where the
   Osaurus baseline lives in a packaged app, the token never logged by the Swift client.

## Decisions waiting on Jason

- **Hero-model safetensors on disk differ from the pinned bytes** (STATE Blockers): the Qwen3.5-4B and
  LFM2.5-8B-A1B `model.safetensors` in `~/.cache/huggingface/hub` are regular files, 873 / 139 bytes larger than
  the revision lists, dated 2026-09-15/16. Every published table measured them. Compare against a fresh pinned
  download (3.0 + 4.8 GB, scratch cache) or record the caveat.
- vMLX 1.6.82 stays untested (same-build canary read -5.5%, session variance; 1.6.59 has no baseline).
- Older, unchanged: Decision 136 (OptiQ 0.5.x vs 0.7.8 tables), `mtplx-wip`, the 0.3.1 bump, README rewrite,
  the v5.0 vault decision note, Apple Developer account, `scripts/lab-copies-wizard.sh`.

## Recipes and traps learned this session

- **Quickbench checkpoint run** (needs Jason's go, quiet machine, Osaurus app closed):
  `/private/tmp/.../scratchpad/qb-run.sh` is gone with the session; its shape: export PATH with the mlx-lm venv
  (`~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`), `HF_HUB_CACHE=<scratch>`, unload the control hub
  (`launchctl bootout gui/$UID/com.dualnode.controlhub.{dashboard,agent}`; reload with `bootstrap` and the plist
  in `~/Library/LaunchAgents`), `fetch.download('mlx-community/Qwen3.5-2B-4bit', True)`, then
  `ohyesmlx quickbench --repo mlx-community/Qwen3.5-2B-4bit --osaurus` (plan) and `--yes` (run, ~9 min). Copy
  `~/.osaurus/config/server{,-runtime}.json` first and `cmp` after.
- **Quiet machine**: check `uptime`, `ps -r`, engine ports, `pgrep -f '^/Applications/[oO]saurus.app/...'`.
  Jason chose to stop only orphans (an orphaned `mcp-server-cloudflare` ran at 100% CPU) and the control hub;
  everything else stays.
- **Workers** (`cc-agent`, DeepSeek v4.1 flash, `CC_AGENT_MAX_TURNS=300`): every BLOCKED this session was right
  (twice a test pinned the subcommand set). Pre-authorise that file in the order when a new subcommand lands.
  Workers do not write SUMMARY files when the order's file list excludes them; the coordinator writes them.
- **Live checks find what tests do not**: this session's live runs found `Pick.downloaded` false on the hero
  models (the bytes differ), the quickbench Osaurus baseline mismatch, and quickbench ignoring its `cache_dir`.
  Keep a live check in every plan's verification.
- The Osaurus pin now lives in `ohyesmlx/osaurus_settings.py`; `scripts/osaurus-pin.sh` calls it and keeps its
  trap and cmp. Its backup is `~/.osaurus/config.phase4-orig/`; `pin` refuses while a backup exists, so run
  `recover` first after a crash.
- Pytest: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q`. A post-commit hook rebuilds
  graphify.
