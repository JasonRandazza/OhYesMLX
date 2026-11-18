# Audit — 05-13 (Fable plan G)

**Audited:** 2026-11-18 by the coordinator. Kept short.
**Verdict:** conditionally acceptable; upgrades applied.

## Must-have (applied)
1. **F4 reuses 05-11's unfinished-root repair.** The plan routes it through that path, including its `install_in_progress` and engines_dir checks. A second removal path would bypass the live-pip guard. (AC-5)
2. **Two workers, one doc file.** W1 and W2 edit different sections of `docs/release/gatekeeper.md`; the coordinator resolves the merge. (Boundaries)
3. **No downloads.** The CPython tarball is already cached, so the build must not fetch anything. (Boundaries)

## Strongly recommended (applied)
1. F9, F10 and F11 red tests pass on main. Each worker checks whether its test covers the whole finding, and extends it if not. (Objective)
2. The quarantine step and the clean-account smoke are recorded as Jason's later checkpoints, not as gates of this plan. (AC-6)

## Deferred
1. Notarization, which needs an Apple Developer account. There is none.
