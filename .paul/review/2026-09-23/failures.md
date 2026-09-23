Scope: Failure-path review of runtimes.py, measure.py, transport.py, sample.py, osaurus_settings.py, and cli.py; no runtime/server/model execution.

### F1 [critical] An interrupt immediately after start can bypass runtime cleanup.
Where: ohyesmlx/measure.py:651-682
Evidence:
>         handle = runtime.start(
>             cell.artifact_dir, cell.artifact_dir, cache_state=cache_state
>         )
>     except Exception as error:  # noqa: BLE001 - a runtime that will not load is a result
>         reason = f"runtime {cell.runtime!r} did not start: {type(error).__name__}: {error}"
>         for result in results:
>             if result.observations:
>                 result.status, result.reason = "FAIL", reason
>             else:
>                 _na(result, reason)
>         return "retry"
>
>     # The same rule decides the cold visit for the first request: it is the one whose load has
>     # not been recorded yet. Read before the rows take their cold load, because by then every
>     # one of them carries it.
>     cold_visit = all(result.cold_load_s is None for result in results)
>
>     for result in results:
>         if result.cold_load_s is None:
>             # The first visit's load is the cold one; a later visit starts from a warm page
>             # cache. One load is shared by the cell's workloads, so it is recorded on every
>             # one of their rows rather than on whichever shape happened to run first.
>             result.cold_load_s = handle.cold_load_s
>             result.runtime_version = handle.version
>
>     try:
>         for result, workload in zip(results, workloads):
>             memory = _workload_visit(handle, result, workload, warmup=warmup, quota=quota,
>                                      concurrency=concurrency, counter=counter)
>             result.memory = _highest_peak(result.memory, memory)
>     finally:
>         handle.stop()
Failure: KeyboardInterrupt between `runtime.start()` returning and entry into the `try` skips `handle.stop()`. The process can retain weights and its port while the run exits or advances through outer handling.
Fix: Begin the `try/finally` immediately after `runtime.start()` returns, covering visit setup too.

### F2 [high] Start cleanup failure is swallowed and the run can continue with a live runtime.
Where: ohyesmlx/runtimes.py:753-762; ohyesmlx/measure.py:654-661
Evidence:
>         except BaseException:
>             # A start that failed still owns a process, and that process may hold the
>             # port. Its own error is the one worth reporting, so cleanup is silent.
>             if pid is not None:
>                 try:
>                     _shutdown(pid, self.port, self.stop_command())
>                 except RuntimeLifecycleError:
>                     pass
>             _remove_scratch(scratch)
>             raise

>     except Exception as error:  # noqa: BLE001 - a runtime that will not load is a result
>         reason = f"runtime {cell.runtime!r} did not start: {type(error).__name__}: {error}"
>         for result in results:
>             if result.observations:
>                 result.status, result.reason = "FAIL", reason
>             else:
>                 _na(result, reason)
>         return "retry"
Failure: If `_shutdown` raises because signalling or port release failed, that failure is discarded and only the original start error reaches `_visit`. The visit is reported as retry/N/A and the run continues without establishing that the first process stopped; this can leave a model resident while another cell starts.
Fix: Preserve and propagate cleanup failure (with the start failure chained), and do not continue the run until runtime/port cleanup is verified.

### F3 [high] Failure to enumerate listeners can leave Osaurus resident after its port is released.
Where: ohyesmlx/runtimes.py:246-267, 505-523, 553-562
Evidence:
>     result = _run((LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"), STOP_TIMEOUT_S)
>     if result is None:
>         # Unverifiable is "no process named", not "nothing is running": the port check every
>         # stop also makes refuses to treat an unanswerable lsof as free.
>         return ()

>     """Kill what a runtime's own stop command left behind, and wait for it to go.
>
>     ``osaurus stop`` frees port 1337 and leaves the app process resident, still holding the
>     weights: a freed port satisfies the one-runtime-holds-weights rule's letter and breaks
>     its substance, and a grid run would leak about one such process per cell into the memory
>     it is trying to measure.

>     listeners = _listener_pids(port)
>     if stop_command:
>         _run(stop_command, STOP_TIMEOUT_S)
>     if _process_alive(pid):
>         _signal_tree(pid, signal.SIGTERM)
>         if not _await_exit(pid, TERM_GRACE_S):
>             _signal_tree(pid, signal.SIGKILL)
>             _await_exit(pid, KILL_GRACE_S)
>     _kill_resident(tuple(other for other in listeners if other != pid))
>     await_port_free(port)
Failure: If the listener lookup transiently fails, `listeners` is empty. `osaurus stop` can still free the port, after which `await_port_free` succeeds, but the handed-off app process was not captured or killed and continues holding model weights.
Fix: Treat an unverifiable listener list as a shutdown failure when the stop command can leave a resident process; do not return based only on port state.

### F4 [high] Exceptions during a visit discard that visit's newly collected observations from results.jsonl.
Where: ohyesmlx/measure.py:512-535, 676-682
Evidence:
>         outcome = _visit(cell_results, cell, workloads, warmup=warmup, quota=quota,
>                          concurrency=concurrency, cache_state=cache_state, counters=counters)
>         if outcome == "measured":
>             reason = lost.pop(cell.id, None)
>             for result in cell_results:
>                 if reason is not None:
>                     # The visit that measured is a later one, and both facts that makes are
>                     # kept: the reason a visit is missing, and that the cold load this row now
>                     # carries is that later start's rather than the cell's first.
>                     result.lost_visit_reason = reason
>                     result.cold_load_after_lost_visit = result.cold_load_s is not None
>                 _set_status(result)
>         elif outcome == "skip":
>             unmeasurable.add(cell.id)
>         elif outcome == "retry":
>             # "retry" keeps the reason the failed visit wrote, and the next visit tries again.
>             lost[cell.id] = cell_results[0].reason
>
>         write_jsonl(results, results_path, run=run)

>     try:
>         for result, workload in zip(results, workloads):
>             memory = _workload_visit(handle, result, workload, warmup=warmup, quota=quota,
>                                      concurrency=concurrency, counter=counter)
>             result.memory = _highest_peak(result.memory, memory)
>     finally:
>         handle.stop()
Failure: An exception or KeyboardInterrupt in `_workload_visit` escapes after the `finally`; control never reaches `write_jsonl`. Observations already appended in this visit remain only in memory and are lost when the process exits, leaving the file at an earlier visit boundary.
Fix: Persist partial raw results on exceptional visit exit after cleanup, without replacing the original exception.

### F5 [high] An unreadable existing Osaurus baseline disables the drift gate.
Where: ohyesmlx/osaurus_settings.py:100-108; ohyesmlx/runtimes.py:908-923
Evidence:
>     try:
>         payload = json.loads(target.read_text())
>     except (OSError, ValueError):
>         return None
>     settings = payload.get("settings") if isinstance(payload, dict) else None
>     return settings if isinstance(settings, dict) else None

>         baseline = load_baseline()
>         if baseline is None:
>             return
>         drift = diff_against_baseline(capture_osaurus_settings(), baseline)
>         if drift:
Failure: If the baseline exists but is malformed, unreadable, or lacks a settings dict, it is treated like no baseline. Osaurus then starts without verifying the host settings, and measurements proceed as though the attestation were not needed.
Fix: Distinguish “no baseline recorded” from “recorded baseline unreadable/invalid” and refuse startup for the latter.

### F6 [medium] An oMLX scratch directory leaks when scratch construction fails before returning.
Where: ohyesmlx/runtimes.py:447-465, 723-745, 968-975
Evidence:
>     root = Path(tempfile.mkdtemp(prefix="ohyesmlx-omlx-"))
>     catalog = root / OMLX_CATALOG_DIRNAME
>     base = root / OMLX_BASE_DIRNAME
>     catalog.mkdir()
>     base.mkdir()
>     link_name = omlx_link_name(artifact_dir, model_id)
>     (catalog / link_name).symlink_to(artifact, target_is_directory=True)
>     return OmlxScratch(root=root, catalog=catalog, base=base, link_name=link_name)

>         self.check_host_state()
>         command, scratch = self.build_command(artifact_dir, model_id, cache_state=cache_state)
>         log_path = _log_path(self.name)
>         started = _now()
>         pid = None
>         try:
>             pid = _spawn(command, log_path)

>         scratch = create_omlx_scratch(artifact_dir, model_id)
>         command = tuple(
>             str(scratch.catalog) if part == OMLX_CATALOG_TOKEN else part
>             for part in self.start_command(artifact_dir, model_id, cache_state=cache_state)
>         )
Failure: After `mkdtemp`, any exception from directory creation, catalog-name validation, or symlink creation occurs before `build_command` returns its scratch path and before `Runtime.start` enters its cleanup `try`; the temporary root is left behind.
Fix: Clean up the newly created root inside `create_omlx_scratch` if construction raises.

### F7 [medium] The shutdown path ignores a failed post-SIGKILL process wait.
Where: ohyesmlx/runtimes.py:553-562
Evidence:
>     if _process_alive(pid):
>         _signal_tree(pid, signal.SIGTERM)
>         if not _await_exit(pid, TERM_GRACE_S):
>             _signal_tree(pid, signal.SIGKILL)
>             _await_exit(pid, KILL_GRACE_S)
>     _kill_resident(tuple(other for other in listeners if other != pid))
>     await_port_free(port)
Failure: If the spawned process remains alive after the kill grace (for example, it cannot yet be reaped), the false result is ignored. A free port then suffices for shutdown to return even though the spawned process was not verified gone and may still retain weights.
Fix: Raise when the second `_await_exit` is false, and verify the spawned process is gone before returning.

### F8 [medium] Sampler stop can return while its worker thread is still alive.
Where: ohyesmlx/sample.py:280-286
Evidence:
>         self._stop.set()
>         if self._thread is not None:
>             self._thread.join(timeout=FOOTPRINT_TIMEOUT_S + 1.0)
>             self._thread = None
Failure: If the footprint poll thread has not exited by the timed join, `stop()` drops its only thread reference and returns a result while the daemon sampler is still running. The caller can proceed with later cells while that thread continues sampling.
Fix: Check `is_alive()` after joining and report/fail to stop rather than clearing the thread reference.

### F9 [low] A failed JSONL rewrite leaves its temporary file behind and loses the latest write.
Where: ohyesmlx/measure.py:1168-1177
Evidence:
>     target = Path(path)
>     target.parent.mkdir(parents=True, exist_ok=True)
>     temporary = target.with_name(target.name + ".tmp")
>     with open(temporary, "w", encoding="utf-8") as handle:
>         handle.write(json.dumps(run, sort_keys=True) + "\n")
>         for result in results:
>             handle.write(json.dumps(_record(result), sort_keys=True) + "\n")
>         handle.flush()
>         os.fsync(handle.fileno())
>     os.replace(temporary, target)
Failure: A write, serialization, flush, fsync, or replace error before `os.replace` leaves `results.jsonl.tmp` behind. The call raises and the latest results are not in `results.jsonl` (or no target exists on the first write).
Fix: Remove the temporary file in an exception-safe cleanup path while preserving the prior target and re-raising the write error.

Unverified suspicions
- `transport._call_before_deadline` starts a daemon worker and closes the connection on timeout but does not join the worker. A socket operation that does not unwind after cross-thread close could leave that helper thread alive; no reproduction was established here.
- `Sampler._loop` has no top-level exception handler around `phys_footprint_mb`; an unexpected exception could terminate the worker without setting `self.error`. The ordinary subprocess and parse failure paths were not shown to raise beyond their local handling.
