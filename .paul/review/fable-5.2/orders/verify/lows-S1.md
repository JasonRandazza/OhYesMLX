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
 (BATCH) S1-F5 S1-F6 S1-F7 S1-F8

BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing
one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test
file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more
than about 40 lines. Do not spawn subagents.

=== FINDING-ID: S1-F5 ===
### F5 — `done` frees the job slot before the download's ledger write and lock release
- Severity: Low
- Where: `ohyesmlx/fetch.py:711-718` with `:772`, `:887`, `:1177`; `ohyesmlx/server.py:198-202`
- Failure scenario: `_download` emits `done`; `_Job.append` marks the job finished and frees the slot at once; only then does `download`'s `finally` run `_record` (ledger read + fsynced atomic write) and `_release_lock`. A client that reacts to `done` with the next download or an evict gets a spurious `busy` — the lock still names this live pid — and an evict that wins the lock race before `_record` would not see what was just created. `done` is documented as last; here it is not.
- Evidence: `try: return _download(...) finally: if any(created.values()): _record(...); _release_lock(lock_path)`; `if terminal: self._registry.finished(self)`.
- Confidence: 65. Raised by timing `_record` (fsync) against a loopback POST round trip.
- Fix direction: emit the terminal `done` from `download` after the `finally` work (the pattern `quickbench.py:943-1019` already follows), or have the server free the slot when the job thread returns rather than on the `done` event.
- Test idea: `emit` callback that, on `done`, asserts the lock file is absent and the ledger already lists the repo. Fails today.


=== FINDING-ID: S1-F6 ===
### F6 — The event cap ends the job on paper while its worker keeps running, breaking "one job, one model"
- Severity: Low (no module reaches 10,000 events today; this is the guard's own failure mode)
- Where: `ohyesmlx/server.py:185-202`
- Failure scenario: a job hits the cap mid-cell. The server stores `too_many_events` + `done`, sets only `cancel_requested`, and frees the slot. Quickbench honours cancel between cells, so its engine stays resident for the rest of the cell; a second quickbench accepted in that window starts a second runtime — the exact condition the project voids a run for — and its numbers look normal.
- Evidence: `self.cancel_requested = True ... terminal = True ... self._registry.finished(self)`; no `abort_requested`, no `stop_engines`, no wait for the thread.
- Confidence: 55 (reachability: download progress is gated to ≤ ~200 events, install emits a handful, quickbench siblings emit to `_discard`).
- Fix direction: at the cap, keep the slot held until `_run_job` returns (mark the stream done, not the slot free), and set `abort_requested` for a quickbench.
- Test idea: fake module that appends `MAX_EVENTS` events then blocks on an Event; assert a second job create is refused `busy` while it blocks.


=== FINDING-ID: S1-F7 ===
### F7 — The lab-path record can refuse after the irreversible install, leaving a venv nothing rolls back or records
- Severity: Low
- Where: `ohyesmlx/engines.py:1294-1295`, `:493-496`
- Failure scenario: `record_lab_path` raises `ValueError` after both pip steps succeeded — the new `bin` is group-writable (umask 002), or the existing `lab-paths.json` holds an entry `lab_paths` refuses (hand edit, a name a later version dropped). `run_steps` has no handler: `created` is discarded with no rollback, no `done` is sent by the installer, and the server reports an unexpected error. The venv stays on disk unrecorded, so cells for that engine cannot start, and a retry either reinstalls over a directory it will never roll back (`existed` is now true) or is refused `already_installed`.
- Evidence: `if installed_bin is not None: record_lab_path(engine, installed_bin, ...)` sits after the step loop, outside any `try`; `check_lab_dir(bin_dir); entries = lab_paths(path)` both raise.
- Confidence: 60. Raised by checking whether `detect_all` reports an unrecorded app-engines venv as installed.
- Fix direction: validate the lab-paths file before the first step (it is a pure read), `chmod 0o755`/0700 the venv root after creation rather than trusting the umask, and route a late refusal through the same rollback + `done` path a failed step takes.
- Test idea: seed `lab-paths.json` with `{"bogus": "/x"}`, run `install` with a fake `run` that creates the venv dir; assert the event stream ends with `error` + `done` and the venv dir is gone.


=== FINDING-ID: S1-F8 ===
### F8 — Evict deletes `refs/main` because it once created it, even after another tool rewrote it
- Severity: Low
- Where: `ohyesmlx/fetch.py:871-874` (write + ledger), `:1250-1258` (remove)
- Failure scenario: the app downloads `org/name` and creates `refs/main`. The user later runs `huggingface-cli download org/name`, which rewrites `refs/main` to a newer commit and adds its own snapshot. Evict in the app keeps the shared blobs (reference scan) and the foreign snapshot, but removes `refs/main` unconditionally — a file whose content is no longer what this app wrote. The user's own copy stops resolving by name offline.
- Evidence: `created["links"].append(planned.ref_path)` then `for path in entry["created_links"]: ... os.remove(path)` with no content check. Blobs get a "still referenced" test; the ref does not.
- Confidence: 75.
- Fix direction: remove `refs/main` only when its content still equals the ledger entry's `revision` (the entry already stores it).
- Test idea: download into a temp cache, overwrite `refs/main` with another 40-hex id, evict; assert the file survives.

---

## Considered and not reported

- Shutdown bound expiring mid-quickbench leaves the engine resident: this is T-02 as written (recovery at next launch). Not repeated.
- "Stop now" racing the cell's own stop: benign — it kills this process's engine and the cell records ABORTED.
- Client-supplied job `name` in the stderr job line: JSON-encoded, token holder only.
- `check_lab_dir` checks the directory but not its parents: needs another account with write on a parent and a victim-owned look-alike directory; not actionable on a single-user Mac.
- Token transport on the Swift side is `URLSession.shared` (default disk `URLCache`, system proxy config). Whether `Cache.db` retains the `Authorization` header was not established; the token is per-launch. An ephemeral session with no cache would close the question cheaply.

## Coverage:

Hotspots
1. `_guard` — covered (correct as read: exact Host, any Origin refused, constant-time bearer)
2. `make_server` token custody — covered
3. closed job args — covered
4. `_job_body` — covered
5. cancel / abort — covered
6. shutdown path (server + `kill_running_steps`) — covered (residual is T-02, known)
7. caps (events, streams, threads) — covered (F6)
8. `_command_plan` — covered
9. `_check_hashed_requirements` — covered (grammar refuses option lines, unhashed pins, EOF continuation)
10. rollback / lab-path record — covered (F7)
11. `run_guided` URL gate — covered
12. `check_lab_dir` / `record_lab_path` — covered
13. fetch allowlist / redirect guard — covered
14. `plan` — covered
15. `_verify` — covered
16. `_fetch_file` — covered (F3, F4)
17. `evict` — covered (F8)
18. `_stop_orphan` / `stop_orphaned_engines` — covered (F2)
19. `stop_own_engines` / `_shutdown` — covered (F1)
20. launch seam — covered for `cli.py:1108-1170` and `BackendLauncher.swift:150-275`; `LaunchSession` teardown (`:277-528`) not read

Open questions
- Q1 guard bypass via stdlib dispatch — covered by reading the handler (fail-closed); no adversarial request was sent, per the no-run rule
- Q2 Host edge cases / duplicate headers — covered by reading (tuple match on the first header value); not exercised
- Q3 pid recycling + stale own ledger — covered: confirmed, F1
- Q4 residual PyPI / standalone-Python hash verification — covered: pins validated before the venv exists; `fetch_python_standalone.sh` checks sha256 before `tar` (`:53-73`, read by grep, not whole)
- Q5 malicious HF repo / catalog — covered for code (`plan` refuses every hostile literal; bytes are hash-pinned); the catalog-change review process is not something the code answers
- Q6 `_acquire_lock` race with app + CLI coexisting — covered: disposition unchanged (double-hold fails safe: a corrupted partial fails `_verify`); the new problem is F2, not the race
- Q7 readers of `BackendToken.raw` — covered: one, `HTTPBackend.makeRequest:182`
- Q8 `_real_open` with no timeout — covered: no finding; a hung `/usr/bin/open` would hold the job slot and is not in the kill registry, but nothing shows it hangs
- Q9 TOCTOU / log append-through-symlink — covered: `_append_install_log` is a plain `open("a")`; same-user only, stays under T-14
- Q10 file modes under App Support — covered: root forced 0700 by `ensure_app_support`; `atomic_write_text` files are 0600; lock and running-engines files are umask-default inside the 0700 root (in a checkout they sit under the repo instead)

