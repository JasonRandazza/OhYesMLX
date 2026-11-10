# Enterprise Plan Audit Report

**Plan:** `.paul/phases/v5-onboarding/045-02b-PLAN.md`
**Audited:** 2026-11-10
**Verdict:** Conditionally acceptable. It is acceptable now that the must-haves below have been applied.

`.paul/config.md` does not exist, so this audit was run manually. It is the project's standing gate before APPLY (see the v5 process gates).

---

## 1. Executive Verdict

The plan was **conditionally acceptable** as first written. It fixes the six triaged findings at the right places, and each fix has one definition. However, its central security claim (T-01) had two gaps that left exactly the attack T-01 names partly open. Its live check could also have written to the real Application Support directory without anyone noticing. With the three must-haves applied, I would approve it for production.

## 2. What Is Solid

- **One function per rule.** `check_lab_dir` is the single place the lab-directory check lives, called both when an engine starts and when a lab path is recorded. `_repo_dir` is shared by `plan` and `evict`. The link-conflict helper is shared by the pre-transfer pass and `link_all`. `atomic_write_text` serves both writers in this plan. Each control lives in one place, so two copies cannot disagree.
- **Each guard sits on the path where the harm happens.** Detection stays read-only, and the code confirms it runs no subprocess. The lab-directory refusal happens at engine start, which is where a hostile `PATH` would actually run code.
- **The pin set is immutable by design.** Hashing adds `--hash` lines and cannot change any `name==version` pair. AC-1 asserts this.
- **The ordering is grounded in the code.** Order B (fetch) depends on `atomic_write_text` from order A, so A must land first. The `-I` regression in `_venv_root` (fixed indices) and the quickbench evict result that is currently thrown away were both found by reading the code before planning.
- **Disclosure follows the fix.** This is the same discipline 045-02a used. Logs are published only after the token scan.

## 3. Enterprise Gaps Identified

1. **Build dependencies are not hash-checked.** pip's `--require-hashes` covers the requirements themselves. It does not cover the PEP 517 build backends pip fetches to build an sdist, and building an sdist runs that package's code. Any pin that resolves to an sdist on the installing interpreter would pull setuptools and other build tools unverified. As written, the plan rejected `--only-binary` on the wrong premise ("hashes already block a newly added sdist").
2. **Hash provenance is taken on trust.** "Every file PyPI lists at freeze time" includes any file that was added to an existing version before the freeze. That is exactly T-01's attack, just earlier. Nothing in the plan would have shown such a file to a reviewer.
3. **The live install could have touched real state.** `install()` takes its default log path, engines directory, detection and lab-paths file from `~` when the module is imported. The plan did not prove the real Application Support directory was left alone, and did not require `HOME` to be set before the interpreter starts.
4. **There was no check that the machine was quiet before network work.** AGENTS.md forbids downloads while a measurement is running. The live check downloads real packages.
5. **A requirements file can carry options.** The file format accepts `--index-url`, `--extra-index-url`, `--trusted-host`, `-f`, `-r`, `-c` and `-e`. A validator that only checks "every line has a hash" would let an index redirect or a nested include through.
6. **The new script had no test and could fail half-way.** `hash_freeze.py` rewrites a security-critical file from network data. A failure part-way through could leave the file partly hashed.
7. **An existing download could become unevictable.** This host's real `fetched.json` has one entry. Nothing showed that the stricter containment rule still accepts it.
8. **`_venv_root` was underspecified.** The plan required a behaviour test but did not say how to fix the parsing (search the argv instead of reading fixed indices).

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Build dependencies of sdists are not hash-checked (gap 1) | AC-1, SCOPE LIMITS, Task 2, verification | Install argv gains `--only-binary :all:`. If a pin has no wheel, that is BLOCKED for Jason and the flag is never silently dropped. The SCOPE LIMITS line rejecting the flag is replaced. |
| 2 | Files added before the freeze are trusted blindly (gap 2) | AC-1, Task 2, verification | `hash_freeze.py` reports every file uploaded more than 7 days after the earliest file of its version. The coordinator reviews the list and records it in the SUMMARY. |
| 3 | The live check could write to real state, and nothing checked the machine was quiet (gaps 3 and 4) | Task 2, verification | `pgrep` quiet check before any network step. A before/after `ls` of the real Application Support directory and `shasum` of its three files. `HOME` set before Python starts, and explicit scratch `engines_dir` and `log_path`. |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Option lines in the requirements file (gap 5) | AC-1 | The validator allows only comments, blank lines, `name==version` and `--hash=sha256:` continuations. |
| 2 | Script with no test that can fail half-way (gap 6) | AC-1, frontmatter, Task 1 | HTTPS to pypi.org only with the default SSL context, one atomic write at the end, an injectable fetcher, and a no-network `tests/test_hash_freeze.py`. |
| 3 | Real ledger could become unevictable (gap 7) | AC-5, verification | Read-only containment check against the real `fetched.json`. |
| 4 | `_venv_root` parsing underspecified (gap 8) | AC-2 | Search the argv for `-m venv`, unit-tested with and without `-I`. |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Four remaining atomic-write copies (`osaurus_settings`, `runtimes`, `measure`, `quickbench`) | `measure.py` is out of bounds for a security plan. The copies are correct, just duplicated. The SUMMARY lists them for a later pass. |
| 2 | Global pip config (`/etc/pip.conf`, `/Library/...`) still loads under `--isolated` | Writing it needs admin, which is outside this threat model's same-user actor. A rerouted index cannot pass the hashes. |
| 3 | `_acquire_lock`'s stale-lock reclaim race | It needs a crash plus two processes racing at the same instant. It is recorded in §9 by AC-7. |
| 4 | SBOM with hashes per release (P5-12) | This is already a Phase 5 checklist item, and it depends on this plan's hashes. |

## 5. Audit & Compliance Readiness

- **Evidence:** red-checks for each acceptance criterion, independent regeneration of the hashes, `curl` + `shasum` checks of three wheels, live install and refusal outputs, before/after hashes of the real directory, and the late-upload review. All of it goes in the SUMMARY.
- **Silent failures prevented:** the `-I` breakage of `_venv_root`, quickbench throwing away evict's result, a half-written hash file, and a quietly removed `--only-binary` are now each tested or gated.
- **Reconstruction after an incident:** install and fetch logs are unchanged, and evict refusals still carry a code. The hash file header records the date and source.
- **Ownership:** the coordinator reviews every diff and hash. Jason owns the BLOCKED decision on wheel availability.

## 6. Final Release Bar

- **Must be true before this ships:** both freezes install cleanly from hashes with `--only-binary :all:` on the target interpreter; any file flagged as a late upload has been reviewed; the real Application Support directory is shown untouched; and the full suite is green with every guard red-checked.
- **Risks that remain:** a dependency file that was already malicious when frozen and is not a late upload; global pip config writable by an admin; the lock reclaim race. All of these are recorded.
- **Sign-off:** yes, with the applied upgrades.

---

**Summary:** Applied 3 must-have + 4 strongly-recommended upgrades. Deferred 4 items.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
