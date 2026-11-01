# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/03-03-PLAN.md
**Audited:** 2026-11-01
**Verdict:** conditionally acceptable (acceptable after the upgrades below, which are applied)

---

## 1. Executive Verdict

As written, not approvable: the downloader and, above all, `evict` can destroy a user's own model files. A shared Hugging Face cache stores blobs by content hash across repos, and AC-8 said "remove blobs used only by that repo" without saying how that is known. With the upgrades applied it is conditionally acceptable.

## 2. What Is Solid

- Consent gate before any request, and a catalog id (never a URL or path) as the only input.
- Revision-pinned file lists with sha256 and size: the downloader never asks "what is latest" and can verify every byte.
- Host allowlist on redirects, bounded retries, injected seams (no real network in tests).
- Disk guard before the first byte; one-at-a-time rule; local log with no upload.

## 3. Enterprise Gaps Identified

1. Evict deletes by repo directory and "used only by that repo" is unspecified: shared blobs and foreign files in the same directory can be lost.
2. Catalog-supplied repo ids and file paths go into URLs and filesystem paths unvalidated (path traversal), and become attacker-controlled once the live Hub source exists.
3. A user's own pre-existing download of the same repo would be overwritten or later evicted as "ours".
4. A hostile or buggy server can send more bytes than the catalog size.
5. Credentials: nothing says tokens are never sent; a mirror variable could redirect traffic.
6. No atomicity statement: a crash could leave a half-visible model that engines list and then fail on.
7. Disk guard counts the total, not the missing bytes, and is checked once.
8. No cancel semantics; in-memory lock does not stop two app instances.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Evict can delete user data | AC-8 revised | evict removes exactly ledger-listed created paths, reference-scans every blob across the whole cache, fails closed on a bad ledger |
| 2 | Path traversal | AC-11 | strict repo/path/hash/revision validation; destinations resolved inside the snapshot dir |
| 3 | Pre-existing downloads | AC-12 | reuse matching blobs, write only missing, ledger records only what was created, `already_present` with no network |
| 4 | Unbounded writes | AC-13 | stop at catalog size; `size_mismatch` |
| 5 | Credential/mirror exposure | AC-14 | no Authorization header, HF_TOKEN and HF_ENDPOINT never read, header test |
| 6 | Half-visible models | AC-15 | links only after full verification, refs last |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Disk guard | AC-16 | missing bytes x 1.2, rechecked per file |
| 2 | Cancel | AC-17 | cancel between chunks, keeps resume data |
| 3 | Multi-instance | AC-18 | lock file with stale-pid reclaim |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Show the model's license before download | A Phase 5 UI requirement; the catalog already carries the license string. |
| 2 | Parallel chunk transfer / mirrors | A speed feature; research §3.6 records it as a known, accepted loss. |
| 3 | Bandwidth throttling | No evidence anyone needs it for sub-2 GB models. |

## 5. Audit & Compliance Readiness

The ledger plus the install-style log give a reconstructable record of what was fetched and what was removed. Without the per-path ledger (AC-8) an incident ("my model vanished") could not be traced; with it, every deletion is attributable.

## 6. Final Release Bar

Before shipping: AC-1..AC-18 green with each guard red-checked; the scratch-cache smoke PASS including the foreign-entry-untouched check. Remaining risk: signed CDN URLs and xet behaviour can change; the sha256 check is what keeps that from becoming corruption. I would sign off on the plan as amended.

---

**Summary:** Applied 6 must-have + 3 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY (after 03-01 lands)

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
