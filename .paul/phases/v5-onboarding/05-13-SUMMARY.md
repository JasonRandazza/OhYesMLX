---
phase: v5-onboarding
plan: 05-13
completed: 2026-11-18
duration: ~1.5h (two parallel Command Code workers, DeepSeek v4.1 flash: W1 107 turns $0.15, W2 182 turns $0.28)
description: "Fable plan G closed: sealed bundle with a fresh interpreter tree, check_bundle gates that can fail, an honest SBOM plus a .sha256, moved-app repair, and a clean-account smoke that runs the bundle"
type: Summary
about: "OhYesMLX"
---

# Plan 05-13 (Fable fix plan G): Packaging and release — Summary

All 11 S6 findings are closed. With plan G, all seven Fable fix plans (A to G, 05-07 to 05-13, plus 05-10b) are done.

## Acceptance Criteria

| AC | Status | Evidence |
|---|---|---|
| AC-1 Sealed bundle (F1, F2) | Pass | Each build unpacks the verified tarball into a fresh temp directory, runs with `-B`, and compiles with `compileall -f` in unchecked-hash mode. A walk fails the build on any other pyc. A real build passed the walk. |
| AC-2 check_bundle can fail for P5-6 (F3) | Pass | New writable-copy half: a venv plus a stdlib import, then the signature is checked again. 5 new tests, red-checked. Live: 2 new PASS lines. |
| AC-3 P5-9 and P5-4 report honestly (F7, F11) | Pass | P5-9 matches PATH as a whole token, checks `PYTHON[A-Z]*=`, and reports SKIP when the environment is unreadable. P5-4 checks the certificate file before any network call. The threat-model cell is corrected. |
| AC-4 SBOM and sha256 (F6, F8) | Pass | A dirty tree is refused. The bundled interpreter computes the source digest. `data_files_sha256` is added. `OhYesMLX-0.3.0.zip.sha256` is written. The signature wording in gatekeeper.md is corrected. The SBOM's `git_commit` is the clean HEAD it was built from. |
| AC-5 Moved-app repair and clean uninstall (F4, F10) | Pass | A venv whose `bin/python` is dead reads as not installed and is repaired through 05-11's process-checked path. pip gets `--no-cache-dir`. The doc lists the Preferences plist. |
| AC-6 Smoke runs the bundle; quarantine step written down (F5, F9) | Pass | The smoke takes `--python` and `--artifact`, and its driver copies `dist/OhYesMLX.app`. gatekeeper.md has a "quarantined download" release check. Jason runs both; they are not gates of this plan. |
| AC-7 Gates | Pass | pytest **1646 passed** (3 skips are worktree-only). Swift 122/122 against a venv built from the branch. `scripts/build_app.sh` exits 0. `check_bundle.sh dist/OhYesMLX.app` reports **all checks PASS**. |

## Deviations

1. **Red tests rewritten because they asserted the defect, not the fix:**
   - `f5`: five tests pinned the old spawn.
   - `f10`: asserted `--no-cache-dir` was absent.
   - `f11`: all three asserted the bug.
   - `f6`: test 3 asked for a tree it was never given, so it gained a `package=` argument.

   Each rewrite was red-checked against main by the worker.
2. **Existing tests adjusted minimally:**
   - `test_engines.py`: three exact pip argv assertions now include `--no-cache-dir`.
   - `test_engines.py`: two fixtures gain `bin/python`.
   - `test_fable_s6_f9.py`: the coordinator replaced the smoke's old `uv build --wheel` line with its new `ditto` of the bundle (W2's F5 change).
3. **The smoke driver now runs its client with the bundle's own interpreter.** Once the test venv is gone, that is the only Python the test account has. This goes slightly beyond the literal AC-6 wording.
4. **Leftover cache directory.** An old unpacked tree is still in `~/Library/Caches/OhYesMLX/build/`. Nothing reads it now; remove it whenever convenient.

## Still Jason's (Phase 5 close)

- **Quarantined download check** (gatekeeper.md): the `xattr`, Archive Utility, the move screen, approval, and a served `/hardware`.
- **Clean-account smoke**, now against the bundle: `scripts/smoke_clean_account.sh` as `oymlxtest`.
- **Live Phase 5 checks:** app-UI download, Stop now, and canaries for Osaurus 0.25.33 and vMLX 1.6.84.
- **The S5-F2 constant**, still unmeasured.
- **UAT** (`/paul:verify`), then `PHASE-5-SUMMARY.md`.
