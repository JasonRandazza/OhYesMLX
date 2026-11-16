# S4 findings — onboarding backend (engines, fetch, quickbench, catalog, recommend, hardware)

Reviewer: Fable 5.2, 2026-11-15. Source read only at the dossier's ranges plus four named leads:
`runtimes.py:471-531` and `:154-172` (does a detected engine's start resolve under the app's PATH),
`catalog.py:51-60` (`disk_needed`), `recommend.py` constants, `catalog.json` `size_bytes` (smallest row).
Nothing was run. Items already in the dossier's "Already known" list or in S1/S2/S3 findings are not
re-filed; Coverage cites them.

### F1 — Stage B starts the winner engine without re-running the occupied-port / Osaurus-app check
- Severity: High
- Where: ohyesmlx/quickbench.py:844-901 (no `_skip_reason`), against :431-447 and the stage-A call at :776
- Failure scenario: Stage A finishes with oMLX (or Osaurus) as winner. Stage B downloads a sibling for several minutes. Meanwhile the user opens the Osaurus app, or starts their own server on the winner's port. Stage B calls `measured(top["engine"], …)` with no check, so the harness's start/stop path and stale-instance sweep run against the user's process — the exact outcome `_skip_reason` exists to prevent.
- Evidence: `_skip_reason` docstring: "Nothing on a skipped engine's port is stopped: the process there may be the user's own server, and the harness's stop path would end it." Stage B: `record = measured(top["engine"], sibling.format, sibling_snapshot, sibling.repo, root / "B" / cell_id)` — the only guards before it are `cancel()` and the download.
- Confidence: 70. Rises to ~90 by confirming in `measure.run_cells`/`runtimes` that a start on an occupied port stops the occupant (S2 territory; `_skip_reason`'s own docstring says it does).
- Fix direction: Call `_skip_reason(top["engine"], …)` immediately before each stage-B cell (after the download) and record a SKIPPED cell with its reason; evict the fetched sibling as usual.
- Test idea: Fake `port_in_use` returning False during stage A and True afterwards; assert no stage-B `measured` call and a SKIPPED stage-B cell reading "quit <engine> first".

### F2 — A pip engine can be "installed" for `detect_all`/`install` yet unstartable by the app, with no repair path
- Severity: Medium
- Where: ohyesmlx/engines.py:1242-1245 (refusal), :526-563 (detection), :987-996 (`start_new_session=True`), :1294-1295 (record is the last act); ohyesmlx/runtimes.py:163-172, :527-531
- Failure scenario: (a) The backend is hard-killed (force quit / launcher SIGKILL / crash) during the pip step. pip runs in its own session, so it survives and finishes; `record_lab_path` never runs. (b) The user already has `~/.local/bin/optiq` (uv/pipx) or a dev checkout. In both, `detect_all` reports `installed: true` (and for (a) `tested: true`), `install` answers `already_installed` forever, and every start fails ENOENT: the app's PATH is `/usr/bin:/bin:/usr/sbin:/sbin`, `_engine_env` prefixes only recorded lab paths, and `ENGINE_BUNDLE_EXECUTABLES` has no entry for `mlx_lm.server` or `optiq`. A partial closure (console script written, later wheels not) gives the same state with a broken import instead of ENOENT. S1 F7 (record refusing after a good install) is a third route to the same dead end.
- Evidence: `if _installed(detect(), engine): return refuse("already_installed", …)`; `_detect_mlxlm` → `_first_existing(… _app_engine_scripts(env, "mlxlm", "mlx_lm.server") + (~/.local/share/ohyesmlx/mlx-lm-…,))`; `ENGINE_BUNDLE_EXECUTABLES = {"omlx": …, "vmlx": …, "osaurus": …}`; `_engine_env`: `if prefixes: env["PATH"] = …` only.
- Confidence: 80. Rises by a clean-account check: create `engines/mlxlm-<ver>/bin/mlx_lm.server` with no `lab-paths.json` and call `/engines` then install.
- Fix direction: Make "installed" for a LAB_ENGINE mean "startable from here": for an app-managed venv with no lab record, either record it (after `check_lab_dir`) or treat it as an incomplete install that `install` may remove and redo; write the record/marker as the completion signal. For a global install, either offer the app-managed install anyway or resolve the detected path at start.
- Test idea: Fixture env with the app venv script present and no lab-paths file: assert `install` does not refuse `already_installed` (or that `_engine_env` PATH reaches the script).

### F3 — The disk guard measures `/`, not the volume the cache is on
- Severity: Medium
- Where: ohyesmlx/fetch.py:819, :1146; ohyesmlx/hardware.py:151-152; ohyesmlx/server.py:594-603 (same number feeds `recommend`)
- Failure scenario: `~/.cache/huggingface` is a symlink to an external SSD (the usual setup on a small internal disk), or the CLI runs with `HF_HUB_CACHE` elsewhere. Internal has 200 GB free, external 3 GB: a 4.8 GB download passes the guard and dies on ENOSPC mid-body. Reversed (internal 4 GB free, external 500 GB): every download is refused `low_disk` and every row is excluded "this Mac has 4.0 GB free". The per-volume data is already scanned (`Hardware.volumes`) and unused here.
- Evidence: `if path == "/": disk_free_bytes = free_bytes`; `free = hardware().disk_free_bytes` then `if free < disk_needed(missing_bytes)`; `cache_dir` is never consulted for free space.
- Confidence: 85. Rises with a test passing a `cache_dir` on a different fake volume.
- Fix direction: One helper, `free_bytes_at(path)` = `shutil.disk_usage(realpath(nearest existing parent of cache_dir)).free`, used by both fetch guards and by the server's `free_disk` for recommend.
- Test idea: `download(..., cache_dir=<dir>, hardware=fake with disk_free_bytes huge)` with `disk_usage` for the cache dir's volume patched to 1 MB; assert `low_disk`.

### F4 — Cancel and "Stop now" are not observed during a stage-B sibling download, and its progress is discarded
- Severity: Medium
- Where: ohyesmlx/quickbench.py:864-866 (also :845, :891 — the only probes)
- Failure scenario: The user presses Stop while stage B is fetching a multi-GB sibling they never chose. `download` is called without `cancel=`, so the run keeps downloading to the end (minutes on a slow link, with the lock held and disk filling) before `cancel()` is read at :891. The UI gets one "downloading" progress event and nothing after, because `emit=_discard`. On server shutdown the wait bound can expire with the thread still in the download.
- Evidence: `fetched = download(sibling.repo, True, cache_dir=cache_dir, emit=_discard) is True`; `fetch.download` takes `cancel=_never_cancelled`; `run` has both `cancel` and `abort` in scope.
- Confidence: 85. Rises by reading how the server maps Stop/Stop-now onto `cancel`/`abort` (S1).
- Fix direction: Pass `cancel=lambda: cancel() or abort()` to the sibling download and forward its `progress` events (re-sequenced) instead of discarding them; then evict the partial (see F9).
- Test idea: Fake `download` that records its kwargs; assert a `cancel` callable is passed and returns True once the run's cancel flag is set.

### F5 — Stage B names a "best" by raw max with no noise band, and that label is persisted as `measured_here`
- Severity: Medium
- Where: ohyesmlx/quickbench.py:398-428 (`_best`), against :374-395 (`_winner` applies `TIE`), :836 (reused stage-A row)
- Failure scenario: Winner oMLX measures stock at 71.0 tok/s in stage A; the sibling measures 72.1 tok/s twenty minutes later. `_best` returns the sibling as this Mac's best format on a 1.5% gap — inside the 5% band stage A treats as a tie — and `latest` hands it to recommendations as `measured_here`. The baseline row was also measured earlier, in a different thermal state, than every sibling it is compared with, so cell order is aliased onto format.
- Evidence: `_winner` computes `tied` with `TIE`; `_best` takes `max(…, key=decode_tps)` over `stage_b.cells` and `summary["stage_b"]` has no tie field; `summary["stage_b"]["cells"].append(dict(top, reused=True))`.
- Confidence: 80. Rises by reading the Results screen's use of `best` (S3 F9 already notes the stage-A tie list is dropped).
- Fix direction: Apply the one `TIE` rule in `_best` too: within the band, keep the baseline (or report a tie list) rather than naming a winner; carry the caveat that the baseline row was measured earlier.
- Test idea: Summary with stage-B PASS cells at 71.0 and 72.1: assert `best` is not the 72.1 row alone.

### F6 — The memory sentences state numbers the fit rule does not use
- Severity: Medium
- Where: ohyesmlx/recommend.py:108-112 (`_reason`), :135-137 (`exclusion_reason`), against :87-93 (`_fit`), :36/:43 (2.0 / 1.25)
- Failure scenario: 16 GiB Mac (budget 9.3 GB), 4.78 GB row: `_fit` says tight (needs 2× = 9.6 GB to be comfortable), the label reads "Tight fit, about 4.5 GB of memory to spare". 8 GiB Mac (budget 3.6 GB): a 3.06 GB row is excluded with "Needs about 6.1 GB of memory at peak; this Mac's budget is 3.6 GB", while a 1.82 GB row — which by that same 2× sentence needs 3.6 GB against a 3.58 GB budget — is offered as "Tight fit, about 1.8 GB of memory to spare". The exclusion line is drawn at 1.25×, but the sentence quotes 2×; "to spare" subtracts 1×. Three definitions of the memory need in one module.
- Evidence: `spare = _gb(budget_bytes - model.size_bytes)`; `f"Needs about {_gb(model.size_bytes * COMFORTABLE_FACTOR)} GB of memory at peak"` on the branch reached only when `size * TIGHT_FACTOR > budget`.
- Confidence: 85. Rises by confirming D5's wording decision does not bless the 1× subtraction.
- Fix direction: Derive every sentence from the factor that decided the row: exclusion quotes `size * TIGHT_FACTOR` (the line actually missed); "to spare" is `budget - size * <factor for that fit>`, or drop the spare figure for tight rows.
- Test idea: Assert the number in the exclusion sentence, parsed back, is ≤ budget exactly when the row is offerable (fails today for the 1.82 GB row on 8 GiB).

### F7 — A partly-downloaded row is excluded on its full size, so it cannot be resumed from the screen that owns it
- Severity: Medium
- Where: ohyesmlx/recommend.py:139-146; ohyesmlx/server.py:594-603; against ohyesmlx/fetch.py:816-827 (`missing_bytes`)
- Failure scenario: 6.0 GB free. The user starts the 4.78 GB row (needs 5.74 GB: passes). At 4.0 GB the network drops or they quit. Free is now 2.0 GB. Recommendations exclude the row: "Needs about 5.7 GB of free disk to download; this Mac has 2.0 GB free" — though 0.78 GB remains and `fetch.download` itself would accept (needs 0.94 GB). The row leaves `pick`'s list while 4 GB of its partial sits on disk.
- Evidence: `if model.repo in downloaded: return None` / `needed = disk_needed(model.size_bytes)` — `downloaded` is all-or-nothing; fetch uses `disk_needed(missing_bytes)`.
- Confidence: 75. Rises by confirming the app offers neither Download nor Remove on an excluded row (S3).
- Fix direction: One definition of bytes-still-to-fetch (fetch's plan already computes it); the server passes it so `exclusion_reason` applies the margin to the remainder.
- Test idea: `exclusion_reason` for a row whose plan shows 80% present and free disk = 1.5× the remainder: assert None.

### F8 — Stage B runs the winner engine on every sibling, whether or not the sibling's row lists that engine
- Severity: Medium
- Where: ohyesmlx/quickbench.py:292 (stage A filters on `model.engines`), :294-302 (stage B unfiltered), :848-901
- Failure scenario: The chosen row lists mlx-lm; its sibling format lists only oMLX. mlx-lm wins stage A; stage B downloads the sibling (GBs, counted in the estimate and the consent sentence) and runs it on an engine the catalog says cannot serve it. Best case the coherence gate FAILs it and the Results screen shows the format as failed rather than unsupported; worst case a format the engine half-loads passes the floor and is ranked.
- Evidence: stage A: `if status.installed and status.name in model.engines`; stage B plan is `catalog.siblings(model, models)` (`other.base == model.base and other.repo != model.repo`); run: `measured(top["engine"], sibling.format, …)` with no `top["engine"] in sibling.engines` test.
- Confidence: 70. Rises by finding one `base` in `catalog.json` whose rows carry different `engines` lists.
- Fix direction: In the run, skip (before downloading) any sibling whose `engines` does not contain the winner, with reason "<format> is not listed for <engine>"; show that in `plan` as conditional.
- Test idea: Two-row base where the sibling lists only engine B; stage A winner A: assert no `download` call for the sibling and a SKIPPED stage-B cell.

### F9 — A failed or refused sibling download leaves its partial on disk, unreported, and hides why it failed
- Severity: Medium
- Where: ohyesmlx/quickbench.py:862-890
- Failure scenario: The sibling download fails at 2.5 of 3 GB (network, retry exhaustion, cancel once F4 is fixed). `fetched` is False, so the repo is never added to `outstanding`, never evicted, and never listed in `not_evicted`; the run reports "finished" with 2.5 GB of a model the user did not choose left in the HF cache. A refusal (`low_disk`, `busy`, `integrity_failed`) returns False through `emit=_discard`, so the cell says only "<repo> could not be downloaded".
- Evidence: `reason = f"{sibling.repo} could not be downloaded"` … `if not fetched: … continue` precedes `outstanding.add(sibling.repo)`; the inner `finally` evicts only `if fetched`.
- Confidence: 80. Rises by confirming `download` ledgers the `.incomplete` on a False return (it does via the `fetch_file` wrapper, fetch.py:1124-1135; S1 F3 is the case where it does not).
- Fix direction: Add the repo to `outstanding` before calling `download` when the sibling had nothing on disk at plan time; capture the last `error` event's code/message for the cell's reason.
- Test idea: Fake `download` that writes a ledgered partial and returns False: assert `evict` is called for the sibling or the repo is in `summary["not_evicted"]`.

### F10 — An exception on the install failure path skips rollback
- Severity: Low
- Where: ohyesmlx/engines.py:1199-1213 (`send` appends the log, then emits), :1232-1237, :1266-1280
- Failure scenario: pip fails because the disk filled. `send("error", …)` first appends to `install-log.jsonl`; that append raises `OSError` (ENOSPC), so `_rollback(created, …)` on the next line never runs. The half venv stays, and if the engine's console script was already written it is the F2 state. Same shape if `emit` raises, or if `Popen` for the pip step raises (`run` is not guarded): no rollback, no `error`/`done`.
- Evidence: step failure: `send("error", …); _rollback(created, engines_dir, send); send("done", …)`; `cancelled`: `send("error", …)` then `_rollback`; `send` → `_append_install_log(…)` → `open(log_path, "a")` unguarded.
- Confidence: 70. Rises with a test whose `emit` raises on the `error` event.
- Fix direction: Roll back first (or in a `try/finally` around `run_steps`), and make the log append best-effort so it can never abort the path that cleans up.
- Test idea: `install` with `run` failing step 2 and `emit` raising on type `error`: assert the venv root is gone.

### F11 — Quick-bench deletes the user's own partial download of a sibling
- Severity: Low
- Where: ohyesmlx/quickbench.py:852-866, :915-921; ohyesmlx/fetch.py:1250-1277
- Failure scenario: The user started downloading format B from the Models screen and stopped at 80%. Later they benchmark format A. Stage B sees `downloaded: false`, resumes B to 100% (`fetched` True), measures, then `evict` removes every path in B's ledger entry — including the 80% the user fetched deliberately. The consent sentence promised to delete what the run downloaded.
- Evidence: `if not sibling_plan.downloaded: … fetched = download(…) is True`; `finally: if fetched: evict(sibling.repo, True, …)`; evict walks the whole per-repo `created_links`/`created_blobs`.
- Confidence: 65. Rises by confirming the ledger entry is per repo and merged across downloads (it is in the ranges read).
- Fix direction: Evict only when the repo had no ledger entry / no bytes on disk at plan time; otherwise keep it and say so in the summary.
- Test idea: Pre-seed a ledger entry and a partial for the sibling; run with fakes; assert no `evict` call for it.

### F12 — The final sweep's evict failure is logged but not recorded in `not_evicted`
- Severity: Low
- Where: ohyesmlx/quickbench.py:944-953, against :922-928
- Failure scenario: A cancel lands right after a sibling download (`break` at :893); in the `finally` sweep `evict` raises (ledger unreadable, lock error). The inner path appends the repo to `summary["not_evicted"]`; the sweep only sends a `log`. The summary and Results screen then say nothing was left behind while a multi-GB sibling is on disk.
- Evidence: sweep: `except Exception as error: send("log", f"could not evict {leftover}: {error}", …)` — no `summary["not_evicted"].append(leftover)`, unlike :928.
- Confidence: 90.
- Fix direction: One helper for "evict or record", used at both sites.
- Test idea: `evict` fake that raises, with a cancel after the sibling download: assert the repo is in `summary["not_evicted"]`.

### F13 — The download lock can be stolen in the gap between its creation and its pid being written
- Severity: Low
- Where: ohyesmlx/fetch.py:371-389
- Failure scenario: Process A creates `download.lock` with `O_EXCL` and has not yet written its pid. Process B (CLI beside the app) hits `FileExistsError`, reads an empty file, gets `pid = None`, removes the lock, loops, and creates its own. Both now download: two writers on one `.incomplete`, two read-modify-writes of `fetched.json`. Distinct from the accepted both-find-a-dead-owner race: here the owner is alive.
- Evidence: `except (OSError, ValueError): pid = None`; `if pid is not None and _pid_alive(pid): return False`; otherwise `os.remove(path)`; `continue`.
- Confidence: 75 on the logic; the window is microseconds, so it needs two starts at once.
- Fix direction: Write the pid to a temp file and `os.link` it into place (atomic create-with-content), or treat an empty/unparseable lock younger than a second as held.
- Test idea: Create an empty `download.lock`, call `_acquire_lock`: assert it returns False (today it removes the file and returns True).

### F14 — A verified partial is renamed into place without fsync, and nothing downstream re-checks bytes
- Severity: Low
- Where: ohyesmlx/fetch.py:891-904 (`finish`), :272-298 (`downloaded`), :780-809; ohyesmlx/quickbench.py:283
- Failure scenario: Power loss or kernel panic seconds after a download "finished". The rename is journaled, the data blocks are not flushed: the blob has the right length and wrong contents. `downloaded` (size + link, UAT-001) says ready; quick-bench measures it and files the FAIL — or a plausible number — under the catalog row; a later `download` answers `integrity_failed … nothing was overwritten`, so the app cannot repair it either. This makes dossier Q1 reachable from our own writer, not only from another tool.
- Evidence: `_verify(…)` then `os.replace(incomplete, planned_file.blob)` with no `os.fsync` on the file or directory; quickbench gates on `downloaded(model, cache_dir)` only.
- Confidence: 55. Rises by checking whether `_fetch_file` fsyncs before returning (not seen in :906-1122).
- Fix direction: `os.fsync` the partial before `_verify`/replace; let quick-bench run `_verify` on the chosen row's LFS blobs once per run (it is a hash of files about to be loaded anyway), and let `download` replace a non-verifying blob it ledgered.
- Test idea: Truncate-and-pad a ledgered blob to its exact size, call quick-bench `plan`/`run` with fakes: assert the run refuses before starting an engine.

Coverage:

Hotspots
1. fetch.py:1222-1300 `evict` — covered. S1 F8 (`refs/main`); F11 here. Noted, not filed: `removed.append(residue)` follows an error-swallowing `_remove` (:1263-1265).
2. fetch.py:605-621 `_verify` — covered, no finding.
3. fetch.py:906-1122 `_fetch_file` — covered. S1 F3, S1 F4; F14 here.
4. fetch.py:780-809 present-blob pass — covered. F14 (no repair path).
5. fetch.py:816-827 + 1144-1155 disk guards — covered. F3, F7.
6. fetch.py:366-405 lock — covered. S1 F2; F13 here; stale-reclaim race is accepted.
7. fetch.py:272-298 `downloaded` — covered. UAT-001 accepted; F14.
8. engines.py:1098-1123 `_rollback` — covered, containment holds; F10 is about reaching it.
9. engines.py:1250-1297 `run_steps` — covered. F2, F10; S1 F7.
10. engines.py:779-831 `_command_plan` + 722-746 — covered, no finding.
11. engines.py:977-1008 `_real_run` + 955-974 — covered. F2 (own session outlives a killed backend).
12. engines.py:387-496 lab dir/paths/record — covered, no new finding (S1 F7).
13. engines.py:1239-1248 consent → installed → lock — covered. F2.
14. quickbench.py:646-751 `measure_cell` — covered, nothing beyond S2 F1, S2 F10.
15. quickbench.py:844-936 stage B + sweep — covered. F1, F4, F8, F9, F11, F12.
16. quickbench.py:374-428 `_winner`/`_best` — covered. F5.
17. quickbench.py:943-1002 `finally` — covered. F12.
18. quickbench.py:1023-1059 `latest` — covered. S2 F11; F5 compounds it.
19. recommend.py:87-154 + hardware.py:100-108 — covered. F6, F7.
20. catalog.py:138-265 — covered, no finding.

Open questions
- Q1 cached-but-wrong artifact measured — covered. F14.
- Q2 crash mid-pip → `already_installed` forever — covered. F2 (confirmed, plus two more routes).
- Q3 disk guard volume — covered. F3 (confirmed).
- Q4 evict scan misses links outside `snapshots` — covered, refuted: evict removes only ledgered paths this tool created, on the user's own request; a hard link elsewhere survives the unlink.
- Q5 `record_lab_path` raising after pip success — covered. S1 F7, not re-filed.
- Q6 fit/reason arithmetic — covered. (a) F6; (b) the 36 GiB step is as documented, no finding; (c) an 8 GiB Mac still gets rows (smallest is 0.35 GB), no finding.
- Q7 finished run with fruitless stage B has no `best` — covered, refuted: stage B always holds the reused PASS winner row (:836), so `_best` returns at least that.
- Q8 retry exhaustion deletes the partial — covered. S1 F4, not re-filed.
