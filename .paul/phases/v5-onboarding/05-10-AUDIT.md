# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/05-10-PLAN.md
**Audited:** 2026-11-16
**Verdict:** Conditionally acceptable (upgrades applied; ready for APPLY)

---

## 1. Executive Verdict

Conditionally acceptable. As written, the plan would not have passed its own red tests: AC-2 adopted the finding's
"reset `attempts` on progress", but the S1-F4 test that fails today pins a cumulative budget (4 passes, 3 sleeps, code
`size_mismatch`) and asserts only that the prefix survives. Two more defects would have shipped quietly. AC-6 pointed
`missing_bytes` at `_download`'s computation, which hashes every present blob, so `GET /recommendations` would have
hashed gigabytes on each call. AC-9 put the integrity check "before stage A", which still runs after the Osaurus pin.
With the upgrades below applied, I would approve it.

## 2. What Is Solid

- **One definition per concept** (free bytes at a path, bytes still to fetch, evict-or-record). This matches AGENTS.md
  and removes the exact divergence the findings describe: the guard asks `/` while recommend asks the same number.
- **Red-test-first with the four-way correction rule** and a recorded pre-check on `d6cfa4f` (12 red, 2 valid controls).
  The evidence is reproducible.
- **Hashing kept out of `GET /quickbench/plan`**, with the S4-F14 test correction justified by the finding's own words
  ("once per run").
- **Ownership rule for eviction** (run-owned versus the user's own bytes). This is the right invariant for a tool that
  deletes multi-GB files on the user's disk.
- Boundaries protect 05-07..05-09 surfaces and forbid live downloads.

## 3. Enterprise Gaps Identified

1. AC-2 contradicted the failing red test. "Reset on progress" also makes the pass count unbounded: a server sending
   1 byte per connection loops for size/1 passes.
2. S1-F3's catch was specified around "the read/write". A disk-full `OSError` from `handle.write` would then be
   retried four times with backoff and reported as a network error.
3. `missing_bytes` was ambiguous between a stat-based and a hash-based count. The hash-based one runs on GET request
   threads.
4. The `free_bytes_at` default argument `disk_usage=shutil.disk_usage` binds at import time. The S4-F3 test
   monkeypatches `shutil.disk_usage`, so it would have ignored the patch.
5. The plan let `hardware.py` re-resolve `HF_HUB_CACHE`/`HF_HOME`, which would be a second definition of the cache dir.
6. The integrity check in `run` was placed "before stage A". That is after the Osaurus pin, so a refusal would pin and
   restore Osaurus for nothing, and it adds host-mutation risk on a path that should mutate nothing.
7. The refusal for a corrupt chosen row named no working remedy. `downloaded()` stays True for it, so the app shows
   no Download button. Only Remove → Download works.
8. A sibling already on disk before the run had the same corrupt-blob exposure as the chosen row and was unchecked.
9. On macOS, `fsync` does not flush the drive's write cache, so the S4-F14 durability fix needs `F_FULLFSYNC`.
10. "The summary says it was kept" named no field and no contract.
11. Tasks 2 and 3 both edit `quickbench.py`, yet were planned as overlapping/parallel, and Task 3 depended on
    `missing_bytes` from Task 2.
12. An unreadable `refs/main` was unspecified for evict.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | AC-2 contradicted the S1-F4 red test; unbounded pass count | AC-2, context facts, boundaries, Task 1 | Budget stays cumulative; exhaustion = `size_mismatch` without removing the partial; MAX_ATTEMPTS semantics protected |
| 2 | Disk write errors would have been retried as network errors | AC-1, Task 1, verification | Catch wraps only `response.read`; new ENOSPC-not-retried test |
| 3 | `missing_bytes` could have hashed on GET threads | AC-6, Task 1, Task 2 | Stat-only by default, `present=` override for `_download`; extracted in Task 1 |
| 4 | Monkeypatched `shutil.disk_usage` would have been ignored | AC-5, Task 2 | Looked up at call time |
| 5 | Integrity check ran after the Osaurus pin | AC-9, Task 3, verification | Check runs first in `run`; a test proves the pin is never called |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Second HF cache-dir resolution | AC-5, Task 2 | `fetch.default_cache_dir()` imported inside `scan` |
| 2 | macOS fsync is not durable | AC-4, Task 1, verification | One `_flush` helper: F_FULLFSYNC, fallback os.fsync |
| 3 | Refusal named no working remedy | AC-9, Task 3 | Message says "remove it on the Models screen, then download it again" |
| 4 | Siblings already on disk were unverified | AC-9, Task 3 | Verified before their cell; failure skips that cell |
| 5 | "Kept" had no contract | AC-8, verification | `summary["kept"]`, documented; app's default decoder ignores it (checked) |
| 6 | Task overlap on quickbench.py | Tasks 2–3 | Strictly sequential T1 → T2 → T3 |
| 7 | Unreadable refs/main | AC-3 | Kept, never removed blind |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Your Mac / Models label "Free disk" now means the cache volume | Identical for every default setup (the cache is on `/`); copy change touches ModelsView, which is out of scope; revisit in plan E |
| 2 | `_verify` of a 20 GB file is not cancellable mid-file (~10 s at SSD speed) | Cancel is honoured between files; per-chunk cancel needs a `_verify` signature change for seconds of latency |
| 3 | The two hero models' re-serialised safetensors would fail `_verify` | `downloaded()` already reports them absent, so `plan` refuses them first; no new refusal (STATE blocker, resolved 2026-11-03) |
| 4 | `missing_bytes` read during an in-flight download races its growing partial | An estimate on a read-only GET; the download's own guard re-decides under the lock |

## 5. Audit & Compliance Readiness

- **Evidence:** the red tests are copied by name from a pinned commit (`6fb323c`). Corrections are listed in the
  SUMMARY. Greps in the verification section give the reviewer mechanical checks.
- **Silent failures:** closed in the four places they lived: a network error escaping, a leftover not recorded, an
  unverified blob measured, and a free-disk figure that is never re-read.
- **Reconstruction:** every partial stays on the ledger, and every leftover lands in `not_evicted` or `kept`, so a
  run's disk effects can be read from its summary plus the fetch ledger.
- **Ownership:** the coordinator observes every diff and the green run, per AGENTS.md.

## 6. Final Release Bar

Must be true before it ships: all 10 findings' tests green, the 2 controls green, full pytest and swift green, the
greps clean, the interface doc updated, and the two-axis review run. Remaining risk if shipped: the deferred items
above, none of which loses data or produces a wrong number. I would sign it with the applied upgrades.

---

**Summary:** Applied 5 must-have + 7 strongly-recommended upgrades. Deferred 4 items.
**Plan status:** Updated and ready for APPLY

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
