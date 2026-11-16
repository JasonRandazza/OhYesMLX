# Order: verify one Fable 5.2 finding (V step)

You verify one finding from a senior reviewer. Its report is a claim, not evidence. Your job is to prove it or refute it.

You run inside the `fable-verify` Orca worktree (branch `review/fable-verify`). Write exactly one report file:
`.paul/review/fable-5.2/verify/<FINDING-ID>.md`. If you can write a test, put it in a NEW file named after the finding
(`tests/test_fable_<finding-id>.py`, or `app/Tests/OhYesMLXKitTests/Fable<FindingId>Tests.swift`), so parallel
verifiers never edit the same file. Never fix the code.

Method:
1. Read the cited code (the ranges named) and its dossier entry. The dossiers live in the main checkout (read-only, absolute path):
   `/Users/jrazz/Dev/active/OhYesMLX/.paul/review/fable-5.2/dossier-S<n>.md`. Restate the claim in one line.
2. Try to reproduce it with the smallest failing test (pytest, or a swift test in app/Tests). Run only that test:
   `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q <file>::<name>` or
   `cd app && swift test --filter <name>`. A test that passes on the current code means the claim is not reproduced.
3. If no test is possible (a race needing real timing, a GUI-only path, packaging), give the concrete evidence instead:
   the exact code path with line numbers, or a command and its output.
4. End the file with exactly one verdict line:
   `VERDICT: CONFIRMED (test: <path::name>)` or `VERDICT: CONFIRMED (no test: <why>)` or `VERDICT: REFUTED (<evidence>)`
   and a line `SEVERITY-CHECK: agree | lower to <x> | raise to <x> — <why>`.
Never start a server, engine, model download or the app. Never edit code outside the one test you add.

---
FINDING:
 (BATCH) S4-F10 S4-F11 S4-F12 S4-F13 S4-F14

BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing
one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test
file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more
than about 40 lines. Do not spawn subagents.

=== FINDING-ID: S4-F10 ===
### F10 — An exception on the install failure path skips rollback
- Severity: Low
- Where: ohyesmlx/engines.py:1199-1213 (`send` appends the log, then emits), :1232-1237, :1266-1280
- Failure scenario: pip fails because the disk filled. `send("error", …)` first appends to `install-log.jsonl`; that append raises `OSError` (ENOSPC), so `_rollback(created, …)` on the next line never runs. The half venv stays, and if the engine's console script was already written it is the F2 state. Same shape if `emit` raises, or if `Popen` for the pip step raises (`run` is not guarded): no rollback, no `error`/`done`.
- Evidence: step failure: `send("error", …); _rollback(created, engines_dir, send); send("done", …)`; `cancelled`: `send("error", …)` then `_rollback`; `send` → `_append_install_log(…)` → `open(log_path, "a")` unguarded.
- Confidence: 70. Rises with a test whose `emit` raises on the `error` event.
- Fix direction: Roll back first (or in a `try/finally` around `run_steps`), and make the log append best-effort so it can never abort the path that cleans up.
- Test idea: `install` with `run` failing step 2 and `emit` raising on type `error`: assert the venv root is gone.


=== FINDING-ID: S4-F11 ===
### F11 — Quick-bench deletes the user's own partial download of a sibling
- Severity: Low
- Where: ohyesmlx/quickbench.py:852-866, :915-921; ohyesmlx/fetch.py:1250-1277
- Failure scenario: The user started downloading format B from the Models screen and stopped at 80%. Later they benchmark format A. Stage B sees `downloaded: false`, resumes B to 100% (`fetched` True), measures, then `evict` removes every path in B's ledger entry — including the 80% the user fetched deliberately. The consent sentence promised to delete what the run downloaded.
- Evidence: `if not sibling_plan.downloaded: … fetched = download(…) is True`; `finally: if fetched: evict(sibling.repo, True, …)`; evict walks the whole per-repo `created_links`/`created_blobs`.
- Confidence: 65. Rises by confirming the ledger entry is per repo and merged across downloads (it is in the ranges read).
- Fix direction: Evict only when the repo had no ledger entry / no bytes on disk at plan time; otherwise keep it and say so in the summary.
- Test idea: Pre-seed a ledger entry and a partial for the sibling; run with fakes; assert no `evict` call for it.


=== FINDING-ID: S4-F12 ===
### F12 — The final sweep's evict failure is logged but not recorded in `not_evicted`
- Severity: Low
- Where: ohyesmlx/quickbench.py:944-953, against :922-928
- Failure scenario: A cancel lands right after a sibling download (`break` at :893); in the `finally` sweep `evict` raises (ledger unreadable, lock error). The inner path appends the repo to `summary["not_evicted"]`; the sweep only sends a `log`. The summary and Results screen then say nothing was left behind while a multi-GB sibling is on disk.
- Evidence: sweep: `except Exception as error: send("log", f"could not evict {leftover}: {error}", …)` — no `summary["not_evicted"].append(leftover)`, unlike :928.
- Confidence: 90.
- Fix direction: One helper for "evict or record", used at both sites.
- Test idea: `evict` fake that raises, with a cancel after the sibling download: assert the repo is in `summary["not_evicted"]`.


=== FINDING-ID: S4-F13 ===
### F13 — The download lock can be stolen in the gap between its creation and its pid being written
- Severity: Low
- Where: ohyesmlx/fetch.py:371-389
- Failure scenario: Process A creates `download.lock` with `O_EXCL` and has not yet written its pid. Process B (CLI beside the app) hits `FileExistsError`, reads an empty file, gets `pid = None`, removes the lock, loops, and creates its own. Both now download: two writers on one `.incomplete`, two read-modify-writes of `fetched.json`. Distinct from the accepted both-find-a-dead-owner race: here the owner is alive.
- Evidence: `except (OSError, ValueError): pid = None`; `if pid is not None and _pid_alive(pid): return False`; otherwise `os.remove(path)`; `continue`.
- Confidence: 75 on the logic; the window is microseconds, so it needs two starts at once.
- Fix direction: Write the pid to a temp file and `os.link` it into place (atomic create-with-content), or treat an empty/unparseable lock younger than a second as held.
- Test idea: Create an empty `download.lock`, call `_acquire_lock`: assert it returns False (today it removes the file and returns True).


=== FINDING-ID: S4-F14 ===
### F14 — A verified partial is renamed into place without fsync, and nothing downstream re-checks bytes
- Severity: Low
- Where: ohyesmlx/fetch.py:891-904 (`finish`), :272-298 (`downloaded`), :780-809; ohyesmlx/quickbench.py:283
- Failure scenario: Power loss or kernel panic seconds after a download "finished". The rename is journaled, the data blocks are not flushed: the blob has the right length and wrong contents. `downloaded` (size + link, UAT-001) says ready; quick-bench measures it and files the FAIL — or a plausible number — under the catalog row; a later `download` answers `integrity_failed … nothing was overwritten`, so the app cannot repair it either. This makes dossier Q1 reachable from our own writer, not only from another tool.
- Evidence: `_verify(…)` then `os.replace(incomplete, planned_file.blob)` with no `os.fsync` on the file or directory; quickbench gates on `downloaded(model, cache_dir)` only.
- Confidence: 55. Rises by checking whether `_fetch_file` fsyncs before returning (not seen in :906-1122).
- Fix direction: `os.fsync` the partial before `_verify`/replace; let quick-bench run `_verify` on the chosen row's LFS blobs once per run (it is a hash of files about to be loaded anyway), and let `download` replace a non-verifying blob it ledgered.
- Test idea: Truncate-and-pad a ledgered blob to its exact size, call quick-bench `plan`/`run` with fakes: assert the run refuses before starting an engine.

