# Dossier S5 — Runtime lifecycle and host safety (Fable 5.2 review)

Scope: `ohyesmlx/runtimes.py` (whole), `ohyesmlx/osaurus_settings.py` (whole), `scripts/osaurus-pin.sh` (whole).
Compiled 2026-11-15 from `graphify-out/graph.json`, per-range `grep -n`/`sed -n` reads, and the contract/record
sources named in §2 and §3. All line numbers confirmed against the working tree at `main` (HEAD `714e8f6`).
Nothing was changed except this file. No server, engine or app was started; no test suite was run (per order).

## 1. Map

### ohyesmlx/runtimes.py (3,811 lines)

Module head and constants:

- `ohyesmlx/runtimes.py:1-93` — module docstring (usage, the six runtimes, the mlx-lm "binds 8081 after a dead load" trap, the incoherent-output hazard) + imports; `osaurus_settings` names imported at :83-90.
- `ohyesmlx/runtimes.py:94-101` — timing constants: READY_TIMEOUT_S 900 s (a 35B gets the full budget), READY_POLL_S 1 s, MODELS_TIMEOUT_S 5 s, VERSION_TIMEOUT_S 30 s, STOP_TIMEOUT_S 30 s, STOP_POLL_S 0.25 s, TERM_GRACE_S 10 s, KILL_GRACE_S 5 s.
- `ohyesmlx/runtimes.py:103-123` — LOG_TAIL_BYTES / LOG_HEAD_BYTES: the two log windows readiness checks read (tail for failure lines, head for startup banners), each 1 MiB with its measured rationale.
- `ohyesmlx/runtimes.py:125-130` — tool paths: `LSOF = shutil.which("lsof") or "/usr/sbin/lsof"` (ambient PATH at import), `PS = "/bin/ps"` (absolute, per threat-model T-09), `LOGS_DIR = writable_root()/results/logs`.
- `ohyesmlx/runtimes.py:135-143` — running-engines ledger names: RUNNING_ENGINES_DIRNAME, LEDGER_ERROR_CODE, ABORT_STOP_ERROR_CODE.
- `ohyesmlx/runtimes.py:145-172` — the never-by-name tables: OSAURUS_APP_BUNDLES (`/Applications/osaurus.app`, `/Applications/Osaurus.app`), OSAURUS_APP_EXECUTABLES (`Contents/MacOS/osaurus`, the app process), ENGINE_BUNDLE_EXECUTABLES (`Contents/Helpers/osaurus` CLI, oMLX/vMLX bundle tools; P5-9).
- `ohyesmlx/runtimes.py:173` — `_RUN_STARTED_PIDS`: pids this run spawned, excluded from the stale-Osaurus match.
- `ohyesmlx/runtimes.py:176-211` — cache-state and KV-quant vocabularies with rationale (CACHE_STATE_OFF/ON, KV_QUANT_OFF/AFFINE8/AFFINE4; `fp8`/`int4` are deliberately not values).
- `ohyesmlx/runtimes.py:213-302` — MTP-depth vocabulary and its long per-runtime rationale (why mlx-lm/oMLX/Osaurus refuse depth, what OptiQ/vMLX/MTPLX accept; values MTP_DEPTH_OFF/"1"/"2"/"3" at :268-269).
- `ohyesmlx/runtimes.py:303-379` — vMLX MTP machinery constants: VMLX_MTP_FIXED_ENV (:303), `_VMLX_START_RUNG`/`_VMLX_ACCEPT_BY_DEPTH` log regexes (:314-315), OPTIQ_MTP_HEAD_RELS (:323), VMLX_MTP_FAMILIES / VMLX_MTP_FAMILY_ALIASES (:343-351), and the `--stream-experts auto` 0.70×RAM rationale (:361-379).
- `ohyesmlx/runtimes.py:380-429` — STREAM_EXPERTS_OFF/ON, TEMPERATURE 0.0, SEED 0, OSAURUS_SMELT_DISABLED, OMLX_API_KEY / OMLX_CATALOG_TOKEN / catalog dir names / SAFE_CATALOG_NAME, MTPLX_BINARY (`~/.mtplx/bin/mtplx`), MTPLX_SSD_CACHE_TOKEN, VMLX_ENGINE_INIT, VMLX_VERSION_SED.
- `ohyesmlx/runtimes.py:451-452` — `RuntimeLifecycleError(RuntimeError)` — base class for unclean start/stop.
- `ohyesmlx/runtimes.py:455-456` — `RuntimeStartError(RuntimeLifecycleError)` — never-ready or refused before spawn.
- `ohyesmlx/runtimes.py:459-460` — `RuntimeStopError(RuntimeLifecycleError)` — port not released / process survived SIGKILL.

Environment, process and port helpers:

- `ohyesmlx/runtimes.py:463-464` — `_now()` — `time.monotonic` (test seam).
- `ohyesmlx/runtimes.py:467-468` — `_sleep(seconds)` — `time.sleep` (test seam).
- `ohyesmlx/runtimes.py:471-531` — `_engine_env(manifest_path=None, lab_paths_path=None)` — ambient env with each pinned engine's lab `bin` prefixed to PATH; refuses a lab path that is absent or not a private dir (`engines.check_lab_dir`); the one place a lab path becomes process-visible (`_spawn`/`_run` only callers).
- `ohyesmlx/runtimes.py:534-566` — `_resolve_program(command, env)` — replaces the program token with its app-bundle executable when PATH cannot name it (skips `env`/`K=V` prefixes; resolves against the env's PATH); recorded commands stay byte-identical either way.
- `ohyesmlx/runtimes.py:569-585` — `_run(command, timeout_s)` — short-lived helper command under `_engine_env`; `None` if it could not run; DEVNULL stdin.
- `ohyesmlx/runtimes.py:588-609` — `_spawn(command, log_path) -> pid` — Popen detached (`start_new_session=True`), stdout/stderr to a log file, env from `_engine_env`; raises RuntimeStartError on OSError.
- `ohyesmlx/runtimes.py:612-631` — `_process_alive(pid)` — reaps own children first (`waitpid WNOHANG`) then `kill(pid, 0)`; zombies would otherwise read alive forever.
- `ohyesmlx/runtimes.py:634-648` — `_resident_osaurus_pids()` — pids whose `ps` argv0 is exactly OSAURUS_APP_EXECUTABLES (full path, never the name `osaurus`), minus `_RUN_STARTED_PIDS`; raises when `ps` cannot run.
- `ohyesmlx/runtimes.py:651-659` — `_signal_tree(pid, sig)` — `os.killpg(os.getpgid(pid), sig)` for a pid this run spawned in its own session; ProcessLookupError ignored, PermissionError → RuntimeStopError.
- `ohyesmlx/runtimes.py:662-675` — `_signal_process(pid, sig)` — `os.kill(pid, sig)` on one pid only; deliberately not the group for a port-recovered pid whose grouping the harness never established.
- `ohyesmlx/runtimes.py:678-688` — `_port_is_free(port)` — `lsof -iTCP:port -sTCP:LISTEN`; "cannot verify" reads as busy (fail-safe).
- `ohyesmlx/runtimes.py:691-710` — `_listener_pids(port)` — `lsof -t` pids on the port, deduped; `None` when unverifiable; the only way to name a process a launcher handed the port to.
- `ohyesmlx/runtimes.py:713-729` — `_serving_pid(spawned, port)` — the pid actually holding weights: the single listener when it is not the spawned pid, else spawned (never an ambiguous port's stranger).

Log reading and evidence:

- `ohyesmlx/runtimes.py:732-741` — `_read_log(path)` — log tail (LOG_TAIL_BYTES), `""` when unreadable.
- `ohyesmlx/runtimes.py:744-753` — `_read_log_head(path)` — log head (LOG_HEAD_BYTES).
- `ohyesmlx/runtimes.py:756-782` — `_read_log_all(path)` — whole log (depth evidence must not window).
- `ohyesmlx/runtimes.py:785-816` — `_traceback_cause(text)` — innermost frame + final exception line of the last traceback.
- `ohyesmlx/runtimes.py:819-891` — `_banner_evidence(name, log_path, *, claim, required, fallback, ...)` — why the runtime's own log does not show a claimed pin state, or None when it does (banner in head window, markers in tail).
- `ohyesmlx/runtimes.py:894-933` — `_stream_evidence(name, log_path, *, required, fallback)` — the streaming-pin reading of `_banner_evidence` (a banner is the evidence; a flag is not).
- `ohyesmlx/runtimes.py:936-942` — `_read_json_object(path)` — one JSON object or None.
- `ohyesmlx/runtimes.py:945-948` — `_log_path(name)` — stamped log path under LOGS_DIR.

Refusals and model-name resolution:

- `ohyesmlx/runtimes.py:951-969` — `osaurus_smelt_mode()` — the host's `concurrency.smeltMode` read ad hoc (not a TRACKED_KEY); sentinels for missing/unreadable.
- `ohyesmlx/runtimes.py:972-1110` — `vmlx_mtp_refusal(artifact_dir)` — whether vMLX can be measured at a depth on this artifact, from config/safetensors evidence.
- `ohyesmlx/runtimes.py:1113-1144` — `_safetensors_shapes(path)` — tensor shapes from a safetensors header, None if unreadable.
- `ohyesmlx/runtimes.py:1147-1298` — `_optiq_head_packing_refusal(config, head, artifact_dir)` — whether OptiQ can pack this head's weights into its block (shapes, scales, width); nested `in_scope` at :1225.
- `ohyesmlx/runtimes.py:1301-1394` — `optiq_mtp_refusal(artifact_dir)` — depth feasibility for OptiQ from the sidecar + config.
- `ohyesmlx/runtimes.py:1397-1408` — `log_load_error(text)` — the load failure a log reports, or None.
- `ohyesmlx/runtimes.py:1411-1423` — `_raise_on_log_error(name, log_path)` — raise RuntimeStartError only on a real load failure.
- `ohyesmlx/runtimes.py:1426-1440` — `_inventory(base_url, *, api_key)` — the model ids the runtime offers (GET /v1/models).
- `ohyesmlx/runtimes.py:1443-1458` — `_health(base_url)` — the runtime's own health payload above /v1.
- `ohyesmlx/runtimes.py:1461-1473` — `_hub_repo_parts(name)` — (org, repo) from a `models--<org>--<name>` component.
- `ohyesmlx/runtimes.py:1476-1489` — `hub_repo_name(artifact_dir)` — lowercased repo of an HF-cache artifact.
- `ohyesmlx/runtimes.py:1492-1506` — `name_forms(artifact_dir)` — every spelling one artifact is served under.
- `ohyesmlx/runtimes.py:1509-1516` — `_ordered(*groups)` — priority-ordered, deduped name tuple.
- `ohyesmlx/runtimes.py:1519-1532` — `resolve_model_id(candidates, inventory)` — the runtime's own spelling, None if offered none.

oMLX scratch catalog:

- `ohyesmlx/runtimes.py:1533-1539` — `OmlxScratch` — the per-run removable directories for one oMLX start.
- `ohyesmlx/runtimes.py:1542-1552` — `omlx_link_name(artifact_dir, model_id)` — the catalog entry name (slash-safe).
- `ohyesmlx/runtimes.py:1555-1577` — `create_omlx_scratch(artifact_dir, model_id)` — fresh one-model catalog + base path (removes the root on its own failure).
- `ohyesmlx/runtimes.py:1580-1593` — `remove_omlx_catalog(catalog)` — removes a catalog this process created, nothing else.
- `ohyesmlx/runtimes.py:1596-1605` — `_remove_scratch(scratch)` — drops a failed start's leftovers; never raises.

Stop machinery:

- `ohyesmlx/runtimes.py:1608-1614` — `_await_exit(pid, timeout_s)` — poll `_process_alive` to a deadline.
- `ohyesmlx/runtimes.py:1617-1635` — `_kill_resident(pids)` — SIGKILL-only (these instances ignore TERM) on pids a stop command left behind; raises if one survives KILL_GRACE_S.
- `ohyesmlx/runtimes.py:1638-1653` — `await_port_free(port, timeout_s=STOP_TIMEOUT_S)` — block until nothing listens, else RuntimeStopError with the lsof command to run.
- `ohyesmlx/runtimes.py:1656-1683` — `_shutdown(pid, port, stop_command=())` — read listeners first, run the stop command, TERM→KILL the spawned group, `_kill_resident` the other listeners (by single pid), `await_port_free`; refuses handoff cleanup when the listener probe is unavailable and a stop command exists.

Running-engines ledger (v5-hardening.md contract):

- `ohyesmlx/runtimes.py:1686-1690` — `_ledger_path(pid=None, root=None)` — `<root>/results/running-engines/<owner pid>.json`.
- `ohyesmlx/runtimes.py:1693-1702` — `_ledger_entries(path)` — the entry list; absent/unreadable/non-ledger = none.
- `ohyesmlx/runtimes.py:1705-1725` — `_write_ledger(path, entries)` — atomic (temp + fsync + `os.replace`), removes the file when empty.
- `ohyesmlx/runtimes.py:1728-1744` — `_process_identity(pid)` — `(lstart, argv)` from one `ps -ww` call, None when unreadable.
- `ohyesmlx/runtimes.py:1747-1783` — `_record_running_engine(pid, serving_pid, port, stop_command=())` — one entry per started engine with both pids' identities; called after cold_load_s is taken; raises when unwritable (start survives it).
- `ohyesmlx/runtimes.py:1786-1797` — `_forget_running_engine(pid)` — drop pid's entry; a stop never fails over its ledger line (stderr_json instead).
- `ohyesmlx/runtimes.py:1800-1810` — `_recorded_identity(entry, pid)` — the identity recorded for pid (spawned or serving slot).
- `ohyesmlx/runtimes.py:1813-1824` — `_entry_stop_command(entry)` — the one parse of the recorded stop command (05-01 deviation 2: extracted for one definition).
- `ohyesmlx/runtimes.py:1827-1864` — `_stop_orphan(entry)` — stop a dead owner's engine via `_shutdown` only when every listener is a recorded pid with a matching identity (or nothing listens and the spawned pid matches); anything else dropped and never signalled.
- `ohyesmlx/runtimes.py:1867-1905` — `stop_orphaned_engines(root=None)` — for each `<owner pid>.json` whose owner is dead, stop its entries; remove the file when handled, keep + raise on a stop that did not take effect.
- `ohyesmlx/runtimes.py:1908-1940` — `stop_own_engines(root=None) -> int` — "Stop now": stops this process's recorded entries read-only, per-entry failure = one stderr line, next entry still tried.

Handle and Runtime base:

- `ohyesmlx/runtimes.py:1941-1976` — `Handle` (dataclass) — pid, port, base_url, model_id, version, cold_load_s, first_request_s, serving_pid, stop_command, scratch, api_key, log_path (measurement-core.md shape).
- `ohyesmlx/runtimes.py:1977-1979` — `Handle.memory_pid` — the pid to sample (serving_pid when the launcher is not the server).
- `ohyesmlx/runtimes.py:1981-1991` — `Handle.stop()` — `_shutdown`, drop `_RUN_STARTED_PIDS`, `_forget_running_engine`, `_remove_scratch`; does not return until the port is free.
- `ohyesmlx/runtimes.py:1992-1998` — `Runtime` (frozen dataclass) — one runtime's start command, readiness rule, stop rule, version probe (name, port).
- `ohyesmlx/runtimes.py:1999-2000` — `Runtime.base_url` — `http://127.0.0.1:<port>/v1`.
- `ohyesmlx/runtimes.py:2002-2013` — `Runtime.start_command(...)` — abstract per-engine argv.
- `ohyesmlx/runtimes.py:2015-2016` — `Runtime.stop_command()` — empty by default (signal-based stop).
- `ohyesmlx/runtimes.py:2018-2019` — `Runtime.version_command()` — empty by default.
- `ohyesmlx/runtimes.py:2021-2031` — `Runtime.cache_state_refusal(cache_state)` — why a cache state cannot be driven, or None.
- `ohyesmlx/runtimes.py:2033-2042` — `Runtime.kv_quant_refusal(kv_quant)` — same for the KV codec pin.
- `ohyesmlx/runtimes.py:2044-2067` — `Runtime.mtp_depth_refusal(mtp_depth, artifact_dir)` — same for the depth pin.
- `ohyesmlx/runtimes.py:2069-2083` — `Runtime.stream_experts_refusal(stream_experts)` — same for expert streaming.
- `ohyesmlx/runtimes.py:2085-2094` — `Runtime.stream_experts_missing(...)` — the after-start half: did the runtime really stream (log evidence)?
- `ohyesmlx/runtimes.py:2096-2118` — `Runtime.mtp_depth_missing(...)` — did the runtime really draft at the pinned depth?
- `ohyesmlx/runtimes.py:2120-2130` — `Runtime.version()` — provenance string; never raises, absence says why.
- `ohyesmlx/runtimes.py:2132-2134` — `Runtime.parse_version(output)` — first line by default.
- `ohyesmlx/runtimes.py:2136-2137` — `Runtime.model_id_candidates(...)` — abstract name candidates.
- `ohyesmlx/runtimes.py:2139-2164` — `Runtime.request_seed(mtp_depth)` — None at temperature 0 except OptiQ's MTP-depth path.
- `ohyesmlx/runtimes.py:2166-2167` — `Runtime.api_key()` — None by default (oMLX overrides).
- `ohyesmlx/runtimes.py:2169-2170` — `Runtime.check_host_state()` — no-op by default (Osaurus overrides).
- `ohyesmlx/runtimes.py:2172-2195` — `Runtime.build_command(...)` — (start_command, scratch=None) by default (Omlx/Mtplx override).
- `ohyesmlx/runtimes.py:2197-2251` — `Runtime.await_ready(...)` — poll: log first (the inventory can lie), process-exit check, /v1/models then `resolve_model_id`, log re-read once the id appears, `readiness_complaint`, 401/403 fail fast; timeout → RuntimeStartError with complaint + log path.
- `ohyesmlx/runtimes.py:2253-2265` — `Runtime.readiness_complaint()` — None by default; Mtplx reads /health.
- `ohyesmlx/runtimes.py:2267-2362` — `Runtime.start(...)` — refuse a busy port and a resident Osaurus app, `check_host_state`, build command, spawn, await_ready, version; on any failure `_shutdown` + `_remove_scratch` (cleanup failure chained as RuntimeStopError); then serving_pid, cold_load_s, ledger entry, Handle.
- `ohyesmlx/runtimes.py:2365-2398` — `prompt_cache_flags(cache_state)` — `--prompt-cache-size 10` on / `0` otherwise (absent pin = off; Decision 130).

Per-engine classes:

- `ohyesmlx/runtimes.py:2401-2402` — `MlxLm(Runtime)` — the control: stock mlx_lm.server.
- `ohyesmlx/runtimes.py:2404-2430` — `MlxLm.start_command` — `python -m mlx_lm.server --model … --port …` + prompt-cache flags only; all three pins are refusals, concurrency ignored.
- `ohyesmlx/runtimes.py:2432-2461` — `MlxLm.kv_quant_refusal` — refuse every codec value (no surface).
- `ohyesmlx/runtimes.py:2463-2464` — `MlxLm.version_command` — `python -m mlx_lm --version`.
- `ohyesmlx/runtimes.py:2466-2470` — `MlxLm.model_id_candidates` — resolved --model path first, then name forms (mlx_lm.server lists path + HF cache).
- `ohyesmlx/runtimes.py:2472-2486` — `MlxLm.mtp_depth_refusal` — accept only `off` (mlx-lm drops MTP heads at load), negative claim made from source.
- `ohyesmlx/runtimes.py:2488-2500` — `MlxLm.stream_experts_refusal` — accept only `off`, reason from source.
- `ohyesmlx/runtimes.py:2503-2504` — `Osaurus(Runtime)` — no tuning flags; host settings instead.
- `ohyesmlx/runtimes.py:2506-2523` — `Osaurus.start_command` — `osaurus serve --port N --yes`, model-less and flag-less by design.
- `ohyesmlx/runtimes.py:2525-2554` — `Osaurus.cache_state_refusal` — honour a state only when the host's `cache.prefix.enabled` already holds it; never edited, never faked by restart.
- `ohyesmlx/runtimes.py:2556-2557` — `Osaurus.stop_command` — `("osaurus", "stop")`.
- `ohyesmlx/runtimes.py:2559-2598` — `Osaurus.kv_quant_refusal` — `off` only at `cache.liveKVCodec == engine_selected`; affine values refused (batched-decode/TurboQuant reasons).
- `ohyesmlx/runtimes.py:2600-2601` — `Osaurus.version_command` — `osaurus doctor --json --redact`.
- `ohyesmlx/runtimes.py:2603-2632` — `Osaurus.mtp_depth_refusal` — depths refused; `off` only at `mtp.mode == force_off`.
- `ohyesmlx/runtimes.py:2634-2664` — `Osaurus.stream_experts_refusal` — `on` refused; `off` only at `concurrency.smeltMode == disabled` (read via `osaurus_smelt_mode`, not the drift gate).
- `ohyesmlx/runtimes.py:2666-2683` — `Osaurus.parse_version` — from `osaurus doctor` JSON, prefers the running bundle, says "one of N bundles".
- `ohyesmlx/runtimes.py:2685-2692` — `Osaurus.model_id_candidates` — lowercased hub repo first, then model_id, then name forms.
- `ohyesmlx/runtimes.py:2694-2712` — `Osaurus.check_host_state` — refuse to start on drift from the recorded baseline; no baseline = no gate (deliberate); invalid baseline = RuntimeStartError.
- `ohyesmlx/runtimes.py:2715-2716` — `Omlx(Runtime)` — must be given a model directory it cannot see past.
- `ohyesmlx/runtimes.py:2718-2766` — `Omlx.start_command` — per-run catalog token + base-path token + api key, `--no-cache` unless `on`, batch cap `--max-concurrent-requests N` (the cap rule is written here).
- `ohyesmlx/runtimes.py:2768-2800` — `Omlx.kv_quant_refusal` — every value refused (its codec is TurboQuant, not affine).
- `ohyesmlx/runtimes.py:2802-2803` — `Omlx.version_command` — `omlx --version`.
- `ohyesmlx/runtimes.py:2805-2824` — `Omlx.mtp_depth_refusal` — depths refused, `off` with no flag change.
- `ohyesmlx/runtimes.py:2826-2842` — `Omlx.stream_experts_refusal` — `on` refused; the mistaken-mechanism reason is named.
- `ohyesmlx/runtimes.py:2844-2845` — `Omlx.api_key` — OMLX_API_KEY.
- `ohyesmlx/runtimes.py:2847-2851` — `Omlx.model_id_candidates` — catalog entry names.
- `ohyesmlx/runtimes.py:2853-2882` — `Omlx.build_command` — expands the catalog/base tokens via `create_omlx_scratch`, hands back the scratch a stop removes.
- `ohyesmlx/runtimes.py:2885-2886` — `Optiq(Runtime)` — the fork whose expert-streaming heuristic silently costs 5×.
- `ohyesmlx/runtimes.py:2888-2972` — `Optiq.start_command` — the fully pinned command: `--max-context off` (rotating-cache hazard), explicit `--no-stream-experts`/`--stream-experts`, `--max-concurrent N`, sampler pins, prompt-cache flags, KV pair with pinned group size, MTP pair only at a depth.
- `ohyesmlx/runtimes.py:2974-2975` — `Optiq.version_command` — `optiq --version`.
- `ohyesmlx/runtimes.py:2977-2989` — `Optiq.request_seed` — keeps the seed only at an MTP depth (its MTP engine is sequential-path-only).
- `ohyesmlx/runtimes.py:2991-3003` — `Optiq.mtp_depth_refusal` — decided from the artifact (`optiq_mtp_refusal`).
- `ohyesmlx/runtimes.py:3005-3055` — `Optiq.mtp_depth_missing` — log/marker evidence that the depth ran.
- `ohyesmlx/runtimes.py:3057-3064` — `Optiq.stream_experts_refusal` — both values accepted (this is the runtime the pin exists for).
- `ohyesmlx/runtimes.py:3066-3091` — `Optiq.stream_experts_missing` — requires both engine lines before an `on` cell is believed.
- `ohyesmlx/runtimes.py:3093-3109` — `Optiq.parse_version` — strips the `mlx-optiq, version` sentence.
- `ohyesmlx/runtimes.py:3111-3120` — `Optiq.model_id_candidates` — the absolute path, `:no-think` variant first.
- `ohyesmlx/runtimes.py:3123-3140` — `vmlx_served_name(artifact_dir)` — the name vMLX exposes (path → last two components / org-repo).
- `ohyesmlx/runtimes.py:3143-3163` — `Vmlx(Runtime)` — JANG loader; real settings are env vars no start command mentions.
- `ohyesmlx/runtimes.py:3165-3271` — `Vmlx.start_command` — positional model, cache/KV/stream pins as env + flags, `--stream-interval 1`, batch cap `--max-num-seqs N`, MTP depth pair + VMLX_MTP_FIXED_ENV at a depth.
- `ohyesmlx/runtimes.py:3273-3304` — `Vmlx.kv_quant_refusal` — every value refused (storage-only codec).
- `ohyesmlx/runtimes.py:3306-3311` — `Vmlx.version_command` — no `--version` flag exists; reads the engine constant per VMLX_VERSION_SED.
- `ohyesmlx/runtimes.py:3313-3321` — `Vmlx.mtp_depth_refusal` — artifact-decided (`vmlx_mtp_refusal`).
- `ohyesmlx/runtimes.py:3323-3425` — `Vmlx.mtp_depth_missing` — the depth-rung/accept log evidence, FAILs on a fallback-to-AR or wrong-rung start.
- `ohyesmlx/runtimes.py:3427-3438` — `Vmlx.stream_experts_refusal` — both values accepted (`--flash-moe` is real, default off).
- `ohyesmlx/runtimes.py:3440-3466` — `Vmlx.stream_experts_missing` — requires the patched-layers line.
- `ohyesmlx/runtimes.py:3468-3470` — `Vmlx.model_id_candidates` — served name then name forms.
- `ohyesmlx/runtimes.py:3473-3533` — `mtplx_mtp_refusal(mtp_depth, observations, artifact_dir)` — depth verdict from the final chunk's `mtplx_stats` receipt, never from files.
- `ohyesmlx/runtimes.py:3536-3546` — `mtplx_served_name(artifact_dir)` — the id MTPLX is told to serve and readiness looks for.
- `ohyesmlx/runtimes.py:3549-3576` — `Mtplx(Runtime)` — native-MTP runtime whose head can be absent without anything failing.
- `ohyesmlx/runtimes.py:3578-3631` — `Mtplx.start_command` — `~/.mtplx/bin/mtplx` with pinned id and port 8200 (its own default 8000 would collide with vMLX), depth pair, per-run SSD-cache scratch.
- `ohyesmlx/runtimes.py:3633-3669` — `Mtplx.build_command` — expands the SSD-cache token into the per-run scratch.
- `ohyesmlx/runtimes.py:3671-3695` — `Mtplx.cache_state_refusal` — `off` refused (RAM session bank has no off switch).
- `ohyesmlx/runtimes.py:3697-3720` — `Mtplx.kv_quant_refusal` — affine values refused (different codec).
- `ohyesmlx/runtimes.py:3722-3735` — `Mtplx.mtp_depth_refusal` — every value accepted; receipts decide.
- `ohyesmlx/runtimes.py:3737-3752` — `Mtplx.mtp_depth_missing` — the receipt gate (all-or-nothing).
- `ohyesmlx/runtimes.py:3754-3772` — `Mtplx.readiness_complaint` — /health beside the model list, asked every poll.
- `ohyesmlx/runtimes.py:3774-3775` — `Mtplx.version_command` — `MTPLX_BINARY --version`.
- `ohyesmlx/runtimes.py:3777-3794` — `Mtplx.parse_version` — strips the `mtplx N.N.N` sentence.
- `ohyesmlx/runtimes.py:3796-3800` — `Mtplx.model_id_candidates` — the pinned id first.
- `ohyesmlx/runtimes.py:3803-3811` — `RUNTIMES` registry — name → instance with the six pinned ports (mlxlm 8081, osaurus 1337, omlx 8100, optiq 8080, vmlx 8000, mtplx 8200).

### ohyesmlx/osaurus_settings.py (411 lines)

- `ohyesmlx/osaurus_settings.py:1-30` — module docstring: attestation for the one runtime with no flags; the pin/restore/recover contract; scope is drift, not correctness.
- `ohyesmlx/osaurus_settings.py:31-92` — imports and constants: DEFAULT_CONFIG_DIR `~/.osaurus/config` (:42), BASELINE_PATH under writable_root() (:46), PIN_FILES = server-runtime.json + server.json (:50), BASELINE_BACKUP / BASELINE_ABSENT markers, BACKUP_DIR_MODE 0700, TRACKED_KEYS (:64-88, 23 measurement-relevant keys), MISSING/UNREADABLE sentinels.
- `ohyesmlx/osaurus_settings.py:94-100` — `_dig(payload, dotted)` — dotted-key lookup with MISSING sentinel.
- `ohyesmlx/osaurus_settings.py:103-127` — `capture_osaurus_settings(config_dir=None)` — read every tracked key; never raises; unreadable file = UNREADABLE sentinel per key.
- `ohyesmlx/osaurus_settings.py:130-146` — `load_baseline(path=None)` — the recorded baseline; missing = None; existing-but-invalid raises ValueError (the gate refuses to guess).
- `ohyesmlx/osaurus_settings.py:149-160` — `write_baseline(path=None, config_dir=None)` — record the host's current settings as the baseline, atomically.
- `ohyesmlx/osaurus_settings.py:163-175` — `_read_object(path)` — one config as a JSON object or ValueError naming the file.
- `ohyesmlx/osaurus_settings.py:178-199` — `_write_atomic(target, data)` — temp (`.pin-tmp`) + fsync + mode-preserving `os.replace`; removes the temp on any failure.
- `ohyesmlx/osaurus_settings.py:202-208` — `_backups(backup_dir)` — the backup files present, in the pin's own order.
- `ohyesmlx/osaurus_settings.py:211-224` — `_log(action, outcome, files, backup_dir)` — one JSON stderr line per pin/restore: names and outcome, never contents.
- `ohyesmlx/osaurus_settings.py:227-286` — `pin(config_dir=None, *, backup_dir, baseline_path=None)` — copy both configs + the baseline (or a `baseline.absent` marker) byte-exact into a 0700 backup dir; refuse over an existing backup or a missing config; set caches off + idle residency 900; re-record the baseline. Parses both configs before replacing either.
- `ohyesmlx/osaurus_settings.py:289-336` — `_put_back(root, backups, present, *, baseline, action)` — copy each backup back, verify byte-exact (`filecmp.cmp(shallow=False)`), remove backups only on full match; `baseline.absent` deletes the pin-written baseline and verifies absence.
- `ohyesmlx/osaurus_settings.py:339-361` — `restore(config_dir=None, *, backup_dir, baseline_path=None)` — put everything back; True only when byte-identical; no backup at all raises (the caller said one exists).
- `ohyesmlx/osaurus_settings.py:364-384` — `recover(...)` — the same restore for a crash-left backup; False (not an error) when nothing to recover.
- `ohyesmlx/osaurus_settings.py:387-403` — `diff_against_baseline(settings, baseline)` — (key, expected, actual) per difference; MISSING on the absent side so older baselines surface.
- `ohyesmlx/osaurus_settings.py:406-411` — `describe_drift(drift)` — one human line per drifted key.

### scripts/osaurus-pin.sh (84 lines, sourced not run)

- `scripts/osaurus-pin.sh:1-16` — header: what pin/restore do and why; `# ponytail` naming the remaining copy-pinned runners (run_grid*.sh, run_sweep_cache*.sh, run_accuracy_*, run_jang_*, run_sweep_prompt.sh); needs `$PY` and a caller `sweep()`.
- `scripts/osaurus-pin.sh:17-22` — CONFIG_DIR/BACKUP_DIR (`~/.osaurus/config.phase4-orig`)/the two config paths and their backups.
- `scripts/osaurus-pin.sh:24-29` — `osaurus_restore()` — delegates to `osaurus_settings.restore`; no-op when no backups.
- `scripts/osaurus-pin.sh:31-37` — `osaurus_pin()` — installs the `trap '…; sweep; osaurus_restore; exit 130' INT TERM HUP`, then `osaurus_settings.pin`.
- `scripts/osaurus-pin.sh:39-67` — `osaurus_set_seqs N` — writes `concurrency.maxConcurrentSequences = N` into the live server-runtime.json (non-atomic `json.dump` to the live file), reads it back via `capture_osaurus_settings`, re-records the baseline (`write_baseline`); refuses before `osaurus_pin` has made the backup, and refuses non-integers.
- `scripts/osaurus-pin.sh:69-84` — `osaurus_restore_check()` — restore + byte-exact verdict ("restored byte-exact (cmp)" / "RESTORE FAILED … copies kept"); afterwards resets the trap to sweep-only.

## 2. Contracts

### AGENTS.md — "Runtime hazards, already paid for" (AGENTS.md:88-104), every bullet

- OptiQ auto-expert-streaming (AGENTS.md:90): "OptiQ flips `--stream-experts auto` on when `model_disk_bytes > 0.70 * total_RAM` … Pin the flag explicitly." → `Optiq.start_command` passes `--no-stream-experts`/`--stream-experts` explicitly (runtimes.py:2913-2917); `test_optiq_pins_expert_streaming_off_rather_than_leaving_it_auto`.
- `--max-context` rotates (AGENTS.md:91): "It installs a `RotatingKVCache`, so a longer prompt is silently windowed … The harness pins `off` (2026-09-16)." → `--max-context off` at runtimes.py:2943-2950; `test_optiq_start_command_is_pinned`.
- Osaurus takes no tuning flags (AGENTS.md:92): "Everything that determines what you measure lives in `~/.osaurus/config/*.json` and an app plist. Snapshot it and diff against a checked-in baseline before every run." → `osaurus_settings.py` (TRACKED_KEYS, baseline gate) + `Osaurus.check_host_state` (runtimes.py:2694-2712). **Note the plist half**: the code snapshots only the two config JSONs (see §7 Q4).
- oMLX per-run catalog (AGENTS.md:93) and SSD cache (AGENTS.md:94): "its oMLX command puts the SSD cache under the per-run scratch base path that `stop()` removes, and passes `--no-cache` unless `cache_state=on` (`runtimes.Omlx.start_command`)". → `create_omlx_scratch`/`_remove_scratch`, `Omlx.start_command` (:2718-2766), `Omlx.build_command` (:2853-2882), `Handle.stop` (:1981-1991).
- MTPLX 200-without-head (AGENTS.md:95): "A depth cell is therefore gated on the final chunk's `mtplx_stats` receipt, never on the config's … `cache_state=off` is refused until its RAM session bank has an off switch … the harness uses the binary at `~/.mtplx/bin/mtplx`." → `mtplx_mtp_refusal` (:3473-3533), `Mtplx.cache_state_refusal` (:3671-3695), MTPLX_BINARY (:413), port 8200 (runtimes.py:3810).
- Ports (AGENTS.md:96): "Osaurus 1337, `optiq serve` 8080, `mlx_lm.server` 8081, oMLX 8100, vMLX 8000, MTPLX 8200 … A run that does not release its port has failed, whatever else it reported." → `RUNTIMES` (:3803-3811), `await_port_free` (:1638-1653) as the last thing every stop does.
- One model resident (AGENTS.md:98): "`measure.py` stops the previous runtime and confirms its port is free *before* starting the next … a run that violates it is void." → in-scope pieces: `Runtime.start`'s port + resident-Osaurus refusals (:2279-2304), `_kill_resident` (:1617-1635); sequencing itself lives in measure.py (out of scope, S?).
- Never edit `ohyesmlx/*.py` while a grid runs (AGENTS.md:101); discard only for a stated defect (AGENTS.md:102) — process rules, no code.
- Osaurus runs go through `scripts/osaurus-pin.sh`, always (AGENTS.md:103): "any test, canary or run may pin Osaurus (idle 900, caches off, baseline re-recorded) provided his own settings (idle residency 30) are restored and verified byte-exact with `cmp`, and the report says so." → `scripts/osaurus-pin.sh` + `osaurus_settings.pin/restore` (the `cmp` is `filecmp.cmp(shallow=False)` in `_put_back`).
- Stale Osaurus instances (AGENTS.md:104): "`osaurus stop` frees the port and leaves the app alive at ~900 MB … Sweep them by full executable path — `^/Applications/osaurus.app/Contents/MacOS/osaurus` — **never by the name `osaurus`**, because `osaurus mcp` is Jason's long-running process." → OSAURUS_APP_EXECUTABLES (:149-152) + `_resident_osaurus_pids` (:634-648) + the pre-start refusal (:2300-2304).
- Metric definitions that bind this code (AGENTS.md:37-45): cold load is its own metric (:43) → `cold_load_s` placement in `Runtime.start` (recorded before the ledger's `ps` calls); "peak_mb … `footprint -p <pid>`" (:44) → `Handle.memory_pid`/_serving_pid decide which pid; "At temperature 0 no seed is sent" (AGENTS.md:51-53 area) → `Runtime.request_seed` (:2139-2164).
- Hard boundaries that bind: "One definition of everything" (AGENTS.md:83) and "Each rationale is written once" (AGENTS.md:84) — both directly relevant to the ledger/stop code (see §3, w1 standards HARD finding).

### docs/interfaces/v5-hardening.md (the ledger + recovery contract)

- v5-hardening.md:11-14: "The running-engines ledger (`ohyesmlx/runtimes.py`). `Runtime.start` records one entry per started engine — `{… "serving_argv": str|null, "port": int, "stop_command": [str, ...]}` — in `<writable_root()>/results/running-engines/<owner pid>.json`, one file per owner process so two harness processes [never share a file]."
- v5-hardening.md:27-34: "For each ledger file whose owner pid is dead … it reads the pids listening on the entry's `port` (`lsof -t`) and stops the entry through `_shutdown(pid, port, tuple(stop_command))` only when **every** listener is one of the entry's recorded pids with the identity recorded for it … An unreadable port, a stranger [listening, a mismatched identity] is dropped and never signalled … A stop that does not take effect keeps the file and raises `RuntimeStopError`."
- v5-hardening.md:37-46: launch order — "`stop_orphaned_engines()` runs first; then, only while `quickbench._osaurus_app_running()` is False, `osaurus_settings.recover(...)`" with the four stderr outcomes (`recovered` / `recovery_pending` / `recovery_failed` / `osaurus_recovery_failed`).
- v5-hardening.md:52-54: the quickbench process registry is "a module-level set under the same lock that covers its spawn" and a timed-out job "has its process group killed" (quickbench side, same lifecycle vocabulary).
- v5-hardening.md:92-97: lab paths "called by `runtimes._engine_env` after `expanduser` and after its 'nothing at' refusal", `check_lab_dir` "st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0", failure at start is a `RuntimeStartError`.

### docs/interfaces/measurement-core.md (runtime lifecycle parts)

- measurement-core.md:94-100: `Runtime.start(artifact_dir, model_id, *, cache_state, kv_quant, mtp_depth, stream_experts, concurrency=1) -> Handle` — pins threaded as keywords, `None` = no flag.
- measurement-core.md:126-158: the `Handle` shape: "cold_load_s: float # spawn -> ready. Its own metric, never folded in"; "serving_pid: int | None # pid to sample; None means the spawned pid is the server"; "def stop(self) -> None: ... # must not return until the port is free"; "The lifecycle fields are not measurements, and vice versa"; `log_path` is "the only place a state the runtime can [silently decline a pin is visible]".
- measurement-core.md:180-186: "Readiness is decided by the runtime's log, not by the port. Observed on mlx-lm 0.31.3: on a model-load failure the server still binds its port and logs `Starting httpd` after the [load thread died]".
- measurement-core.md:276-292: "`cold_load_s` alone cannot be compared across runtimes … Any cross-runtime load comparison uses `cold_load_s + first_request_s`."

### docs/runtimes/*.md — the hazard lines this code encodes

- `docs/runtimes/osaurus.md`: §1.2/§1.3 the app-vs-CLI split and the capitalisation hazard ("the CLI searches for *both* `/Applications/Osaurus.app` [and lowercase]", :228); "There is no model selector on `serve`" (:319); `concurrency.smeltMode` enum `engineSelected | disabled | flashMoE | ssdStreaming` (:298, mirrored runtimes.py:394-398); `mtp.explicitDepth` "must be 1, 2, or 3" (:344) and the force-on refusal without a `vmlx_mtp_tuning.json` sidecar (:862-876, mirrored runtimes.py:249-251); `concurrency.maxConcurrentSequences` is the host-side batch cap and "The concurrency runner sets this key to the run's N and restores it (2026-09-27)" (:374); `osaurus serve --help` **starts the server** and `osaurus stop --help` **stops it** (:143-144); `doctor` reports duplicate bundles (:270, mirrored in `parse_version` :2666-2683); §3.6 `~/Library/Preferences/com.dinoki.osaurus.plist` — "the one `ohyesmlx/osaurus_settings.py` cannot see at all" — `model_options_<modelID>` holds `disableThinking`, which "decides whether the measured model emits reasoning tokens at all" (:498-527).
- `docs/runtimes/mtplx.md` / `docs/research/2026-10-09-mtplx-load-probes.md`: `mode: "ar"` with `drafted_tokens: 0` still answers 200; `cache_state=off` refused (RAM session bank); `~/.mtplx` app and Login Items are Jason's — the harness touches only `~/.mtplx/bin/mtplx`.
- `docs/runtimes/optiq.md` + AGENTS.md:90-91: the two silent-decline hazards (stream-experts auto, rotating `--max-context`) — pinned in `Optiq.start_command` with the comment "a start command claiming a cap that is not there contradicts a 32k figure beside it" (runtimes.py:2941-2950).
- `docs/runtimes/omlx.md` + AGENTS.md:93-94: catalog isolation and the SSD cache; `--no-cache` is "Disable oMLX paged SSD cache" (runtimes.py:2758).
- `docs/runtimes/vmlx.md`: no stop subcommand (signal stop, runtimes.py:3158), settings via env vars (VMLX_MTP_FIXED_ENV), `--version` is not a flag (runtimes.py:3307-3308).
- `docs/runtimes/mlx-lm.md` + runtimes.py:16-17: "On a load failure mlx-lm 0.31.3 binds 8081 and logs `Starting httpd at 127.0.0.1 on port 8081...` after the load thread has already raised" — the reason readiness reads the log first.

### docs/threat-model.md rows naming this code

- §4 trust boundaries (:51, :76-77): "lab-paths.json decides which binaries every engine start executes. `runtimes._engine_env` … puts its directories at the front of PATH"; "Servers are spawned in their own session … and stopped by process group, or by the pids listening on their port"; "Byte-exact backup and restore (`osaurus_settings.py:225-330`)".
- §5.3 subprocess table (:114-117): `_run` and `_spawn` rows; "`os.kill` / `os.killpg` on pids this run started or found listening on the engine's port" (:117); `LSOF` "resolved once with `shutil.which` on the ambient PATH" (:116).
- §5.5 written-locations (:141-147): the `.pin-tmp` fixed temp name, the 0700 backup dir, the baseline in the package tree, engine logs in the repo tree, `$TMPDIR/ohyesmlx-omlx-*` scratch.
- §5.6 files read (:153-157): lab-paths.json values "No check of where it points" (since fixed, T-12), Osaurus config "The restore is verified byte-exact", `HF_HUB_CACHE`/`HOME` decide every path.

## 3. Already known — do not re-report

Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`. Shas from `git log -S`/file history.

From `.paul/review/2026-09-23/` (the deep review; its line numbers are stale against today's file):

- F4 [high] A stale port-free Osaurus process can keep another model resident; no code swept by full executable path — invariants.md:96-115 — fixed `ef01396` (harden wave 1: `_resident_osaurus_pids` + pre-start refusal, full-path match). Guards: `test_start_refuses_stale_osaurus_app_by_full_executable_path`, `test_start_does_not_match_osaurus_mcp_or_other_binary`.
- failures F1 [high] cleanup failure after a failed start was discarded, so a surviving first process could hold weights while another cell starts — failures.md:42-63 — fixed `ef01396` (chained `RuntimeStopError("start failed: …; cleanup failed: …")`, runtimes.py:2340-2352). Guard: `test_start_surfaces_cleanup_failure_chained_from_start_error`.
- failures F3 [high] a transiently empty listener list could leave Osaurus resident after its port was released — failures.md:66-93 — fixed `ef01396` (`_shutdown` raises "refusing handoff cleanup" when the probe is unavailable and a stop command exists, runtimes.py:1665-1668). Guard: `test_stop_refuses_handoff_cleanup_when_listener_probe_is_unavailable`.
- invariants row "Sweep stale Osaurus instances by executable path, not by process name" was UNENFORCED — invariants.md:38 — fixed `ef01396` (same as F4).
- invariants row "`top_p`/`repetition_penalty` pinned" UNENFORCED in start commands — invariants.md:15 — resolved at request level, Decision 131 (2026-09-29): sampler defaults "surveyed, not assumed", vMLX pinned `--default-repetition-penalty 1.0`, Osaurus bundle penalties recorded as a confound. status: accepted-with-caveats (STATE Blockers row 2; AGENTS.md:50-53).
- invariants row "Osaurus baseline absent/unreadable silently disables the gate" (Partial) — invariants.md:28, :84 — accepted as designed: `check_host_state` docstring "No recorded baseline means no gate"; invalid baseline now raises instead (`load_baseline` ValueError). Guards: `test_osaurus_starts_when_no_baseline_has_been_recorded`, `test_osaurus_refuses_to_start_when_existing_baseline_is_invalid`.
- invariants row "mlx-lm dedicated venv / `from mlx_lm import load` preflight" UNENFORCED — invariants.md:39 — open (no preflight in this module; the lab-paths mechanism is the partial answer — see §7 Q6).
- invariants row "one model resident … UNENFORCED for stale, unbound Osaurus apps" — invariants.md:33 — fixed `ef01396` (the resident refusal); cross-runtime sequencing stays measure.py's (AGENTS.md:98).
- docs.md F11 [low] runtime docs' stale line citations into runtimes.py — docs.md:111-118 — deferred (docs rot; citations in docs/runtimes/*.md were refreshed piecemeal, no single commit found).
- scripts.md findings on `probe_*.py` (port sweeps that kill listeners, dual-model speculative probe) — scripts.md:18-28 — accepted (research scripts, not harness paths; the speculative probe "is an explicit exception" to one-resident).
- invariants.md:199 `runtimes.py:639-653` version-provenance "partial: unavailable probes become generic `unknown`" — open/accepted (by design `version()` "never raises; absence says why").

From threat-model.md (§7.3/§7.4/§8/§9/§10 rows naming this code):

- T-02 a pip step / engine outliving a shutdown; interrupted-app leaves a pinned Osaurus — §8 row, §7.4 — fixed `9bc9388` (045-02a part B: startup recovery + the running-engines ledger; tests `test_a_dead_owners_matching_engine_is_stopped_through_shutdown`, `test_a_reused_launcher_pid_blocks_the_osaurus_shaped_stop`, …).
- T-05 the Osaurus app rewriting its config mid-run; a user's mid-run edit overwritten by restore — §8 rows — fixed `9bc9388` (drift copy `keep_during_run`); **residual**: "AC-7 runs only when `run_cells` returns … a mid-run user edit in that [raise] path is still overwritten by restore" (045-02a-SUMMARY known gaps; §7.4 T-05 residual) — open.
- T-03 the baseline's location in a packaged app (was written inside the package tree) — §8 row — fixed `9bc9388`/045-02 era (`BASELINE_PATH = writable_root()/config/…`, osaurus_settings.py:46) plus checklist P5-6 (met, §10 status).
- T-09 bare command names (`ps` etc. on ambient PATH) — §7.4 — fixed `4b35ef8` (`PS = "/bin/ps"` etc.); "runtimes.LSOF is still resolved with `shutil.which` … not part of this finding" — the LSOF exclusion is recorded, not fixed — open (§7 Q5). 045-02a-SUMMARY lists it again ("Candidate for 045-02b"; 045-02b did not take it).
- T-12 lab-paths.json values unchecked → front of PATH — §7.4 — fixed `a031ad4` (045-02b part A: `engines.check_lab_dir` called from `_engine_env`; runtimes.py:503-507).
- T-06/T-13/T-16 fetch-ledger races — §7.3/§7.4 — fixed `fb4e61c` (045-02b part B). Only the word "ledger" is shared with the running-engines ledger; different subsystem.
- §9 accepted risk row: `_acquire_lock` check-then-remove stale-reclaim race — accepted (fetch lock, not this scope's ledger).
- §10 P5-9 "The backend's PATH is launchd's default … An app engine whose command-line tool ships inside its `.app` is exec'd from `runtimes.ENGINE_BUNDLE_EXECUTABLES` when its bare name does not resolve" — §10 status "Met" — fixed `369f180` (045-03 F2).
- §10 P5-6 nothing written inside the .app bundle (baseline, logs under App Support) — §10 status "Met" — fixed (`101df7c` precompile fix is the last edit there).
- P5-11 (app cannot offer Re-download) — §10 "Partly met … Open" — deferred (also Fable S4 scope; not this section's code).

From STATE.md (Deferred Issues / Blockers):

- "Osaurus pin copies remain in run_grid.sh / run_grid_moe.sh / run_sweep_cache*.sh / run_accuracy_* / run_jang_* / run_sweep_prompt.sh" — STATE Deferred Issues (v3.1 2026-09-25) — deferred ("Consolidate only where identical"; the list is restated in scripts/osaurus-pin.sh:12-14 `# ponytail`).
- "Osaurus applies the model bundle's `presence_penalty`/`repetition_penalty`, and the harness does not pin them" — STATE Blockers — tested 2026-09-30 (dense arm unchanged); the 35B/LFM OptiQ bundles untested — accepted-with-caveats.
- Disk tightened to 40 GiB free (2026-11-13) — STATE Deferred — deferred (bears on scratch/`results/logs` growth from this module's logs).

From `.paul/phases/v5-onboarding/*SUMMARY.md` "Deviations"/"Known gaps"/"Carried forward":

- 04-03a deviations: the shell pin's backup moved to one `~/.osaurus/config.phase4-orig/` dir; `pin` now refuses while a leftover backup exists (a crashed runner must `recover` first) — 04-03a-SUMMARY:32-38 — fixed `339d7c7`.
- 04-03c deviation: a backup dir holding both `baseline.json` and `baseline.absent` makes `_put_back` raise instead of returning False ("Unhandled by choice; only hand-made") — 04-03c-SUMMARY:58-63 — accepted.
- 045-02a deviation 1: one existing quickbench test edited to inject the drift check (Jason's call, 2026-11-09) — accepted (STATE Decisions).
- 045-02a deviation 2: `recover` writes two stderr lines (its own action line + `_app`'s) — accepted.
- 045-02a known gaps: "AC-7 runs only when `run_cells` returns" (T-05 residual, above); "`during-run/` stays in the backup directory … `restore` can no longer `rmdir`" — open (Phase 5 copy item); "`runtimes.LSOF` is still `shutil.which`" (above); "Startup ordering: `ensure_app_support()` runs before the bind … an unwritable HOME is a traceback" — accepted/minor.
- 045-02b deferred: the other four atomic-write copies (`osaurus_settings`, `runtimes`, `measure`, `quickbench`) not migrated to `ohyesmlx.atomic_write_text` — 045-02b-SUMMARY Deferred — deferred (PHASE-4.5 "Carried forward" lists them too).
- 05-01 deviation 2: `_entry_stop_command` extracted so the ledger's stop-command parse has one definition — 05-01-SUMMARY:49-52 — fixed `93d374c` (introduced there; touched again `ac0de1b`).
- 045-03 (clean-account smoke): app engines exec from bundle under launchd PATH — fixed `369f180`; optiq wheels-only — out of scope.

From `.paul/review/2026-11-14-phase5-w1|w2/` logs:

- HARD "Each rationale is written once" violation: `ABORT_STOP_ERROR_CODE`'s comment (runtimes.py:141-143) vs `stop_own_engines`' docstring (:1908-1940) restate the same rule — w1/standards.log:13 — open (both copies still present).
- w2/spec.log findings (raw-JSON re-encode, AC-2/D8) are app-side, not this section.

## 4. Hotspots

Ranked roughly by blast radius. "Guards" names the test that would fail if the code broke.

1. `ohyesmlx/runtimes.py:651-675` `_signal_tree`/`_signal_process` — the only code that signals processes; a wrong pid or an over-broad group signal reaches Jason's own processes (`osaurus mcp`, the app). The split rule (group only for a pid this run spawned in its own session; single pid for a port-recovered one) is the whole safety story — guards: `test_a_listener_that_is_the_spawned_pid_is_not_signalled_twice`, `test_stop_kills_the_process_the_launcher_left_holding_the_weights`, `test_an_unreadable_port_is_dropped_and_never_signalled`.
2. `ohyesmlx/runtimes.py:634-648` `_resident_osaurus_pids` — the never-by-name match; an argv0 comparison bug here kills `osaurus mcp` or misses stale apps and silently corrupts every memory number after — guards: `test_start_refuses_stale_osaurus_app_by_full_executable_path`, `test_start_does_not_match_osaurus_mcp_or_other_binary`, `test_resident_osaurus_pids_never_runs_a_ps_found_on_path`.
3. `ohyesmlx/runtimes.py:1656-1683` `_shutdown` — the one stop definition: stop command, TERM→KILL on the spawned group, SIGKILL-only on handoff listeners, port-free guarantee. A failure mode here is either a leaked ~20 GB model (two resident) or a signal at the wrong tree — guards: `test_stop_*` family (:2655-2880 in tests), esp. `test_stop_escalates_to_sigkill_when_sigterm_is_ignored`, `test_stop_refuses_handoff_cleanup_when_listener_probe_is_unavailable`, `test_stop_raises_if_spawned_pid_survives_sigkill`.
4. `ohyesmlx/runtimes.py:1617-1635` `_kill_resident` — SIGKILL-only escalation on pids recovered from the port; trusts `_listener_pids`' identity claim entirely — guard: `test_stop_kills_the_process_the_launcher_left_holding_the_weights`, `test_stop_does_not_return_while_that_process_still_lives`.
5. `ohyesmlx/runtimes.py:1827-1864` `_stop_orphan` — stops a dead owner's engine after identity checks; a weak check signals a reused pid's innocent process; too strong and a real orphan keeps 20 GB resident — guards: `test_a_dead_owners_matching_engine_is_stopped_through_shutdown`, `test_a_reused_launcher_pid_blocks_the_osaurus_shaped_stop`, `test_a_reused_pid_is_dropped_and_never_signalled`, `test_a_matching_pid_with_a_different_argv_is_dropped_and_never_signalled`, `test_a_stranger_listening_on_the_recorded_port_is_dropped`.
6. `ohyesmlx/runtimes.py:1867-1905` `stop_orphaned_engines` — reads every dead owner's ledger and acts on it at app launch; the owner-alive check is the only thing protecting a grid running from the CLI — guards: `test_a_live_owners_ledger_is_never_read_or_touched`, `test_a_stop_that_does_not_take_effect_keeps_the_ledger_file`, `test_a_json_file_that_is_not_a_ledger_is_left_alone`.
7. `ohyesmlx/runtimes.py:1908-1940` `stop_own_engines` — "Stop now" from the app UI: stops live engines off the measurement path; per-entry failures swallowed to one stderr line by design — guards: `test_stop_own_engines_stops_only_this_processes_entries_and_never_writes`, `test_stop_own_engines_reports_a_failing_stop_and_still_stops_the_next`, `test_stop_own_engines_without_a_readable_ledger_is_zero`.
8. `ohyesmlx/runtimes.py:2267-2362` `Runtime.start` — the gate that keeps one model resident (port-free + no resident Osaurus + host state) and the failure path that must not leak a process or a scratch tree; also where cold_load_s is taken before the ledger's `ps` calls (metric purity) — guards: `test_start_refuses_a_port_this_run_does_not_own`, `test_start_surfaces_cleanup_failure_chained_from_start_error`, `test_start_reports_the_servers_error_and_still_frees_the_port`, `test_the_running_engine_is_recorded_after_the_cold_load_time_is_taken`, `test_a_ledger_write_failure_does_not_fail_the_start`.
9. `ohyesmlx/runtimes.py:1693-1783` ledger read/write + `_record_running_engine` — a recorded `stop_command` is later executed verbatim by `_stop_orphan`/`stop_own_engines`; the identity fields are what stop it executing against a stranger. The fixed `.tmp` name and per-pid file naming bound the concurrency story — guards: `test_the_ledger_file_is_replaced_atomically`, `test_the_ledger_file_is_removed_once_its_last_entry_is_gone`, `test_an_osaurus_start_records_the_serving_process_when_the_launcher_is_unreadable`.
10. `ohyesmlx/runtimes.py:2197-2251` `await_ready` — readiness by log-before-inventory (the mlx-lm binds-8081-dead trap); a regression here publishes a cold load for a model that never loaded — guards: `test_start_refuses_a_server_whose_load_died_even_though_the_model_is_listed`, `test_a_model_that_failed_to_load_as_the_list_answered_is_not_a_started_runtime`, `test_start_returns_a_handle_only_after_the_model_id_appears`, `test_mtplx_a_nonzero_exit_before_the_port_binds_is_a_load_failure`.
11. `ohyesmlx/runtimes.py:471-531` `_engine_env` — trust boundary: lab-paths.json decides the front of PATH for every spawned server and helper (threat-model §4); refusal of absent/non-private lab dirs is the only guard — guards: `test_a_lab_path_that_does_not_exist_is_refused_naming_the_engine`, `test_a_lab_path_owned_by_another_user_is_refused_at_start`, `test_a_lab_path_nobody_else_can_write_is_still_prefixed`.
12. `ohyesmlx/runtimes.py:534-566` `_resolve_program` — execs bundle internals when PATH cannot name the tool (P5-9); a wrong match runs the wrong binary while the recorded command claims otherwise — guards: `test_spawn_execs_the_bundle_executable_when_the_name_is_not_on_the_engines_path`, `test_the_osaurus_bundle_executable_is_derived_from_the_bundle_spellings`, `test_a_name_that_resolves_on_the_engines_path_is_left_untouched`.
13. `ohyesmlx/runtimes.py:588-609` `_spawn` — detached-session spawn; wrong session semantics break the group-signal contract of `_signal_tree` — guards: `test_spawn_hands_the_engine_env_to_the_process` (and the stop tests' rig).
14. `ohyesmlx/runtimes.py:713-729` `_serving_pid` — decides whose footprint is published as `peak_mb`; an ambiguous port must never sample a stranger — guards: `test_osaurus_samples_the_app_the_launcher_handed_the_port_to`, `test_an_ambiguous_port_samples_the_spawned_pid_rather_than_a_stranger`, `test_a_port_that_names_nothing_leaves_the_sampler_on_the_spawned_pid`.
15. `ohyesmlx/runtimes.py:2694-2712` `Osaurus.check_host_state` + `ohyesmlx/osaurus_settings.py:130-146,387-411` — the drift gate: what an Osaurus cell measures is decided by host files no start command shows; fail-open on no baseline is deliberate, fail-closed on invalid — guards: `test_osaurus_refuses_to_start_when_the_host_drifted_from_the_baseline`, `test_osaurus_refuses_to_start_when_existing_baseline_is_invalid`, `test_osaurus_starts_when_the_settings_match_the_baseline`.
16. `ohyesmlx/osaurus_settings.py:227-286` `pin` — writes Jason's own host files (caches off, idle 900) after a byte-exact backup; a mistake here corrupts the host's Osaurus install; the refuse-over-existing-backup rule is what keeps the only copy of his settings — guards: `test_pin_backs_up_both_configs_byte_exact_and_applies_the_run_settings`, `test_a_second_pin_refuses_rather_than_overwriting_the_users_original`, `test_a_pin_refuses_over_a_leftover_baseline_backup_or_marker`, `test_a_pin_that_killed_the_write_between_temp_and_replace_leaves_the_files_intact`.
17. `ohyesmlx/osaurus_settings.py:289-361` `_put_back`/`restore` — the byte-exact `cmp` is AGENTS.md's standing-authorisation condition; a False that loses backups would strand the host in run settings — guards: `test_restore_puts_every_file_back_byte_exact_and_removes_the_backup`, `test_restore_returns_false_and_keeps_every_backup_when_a_file_is_not_byte_identical`, `test_a_baseline_that_does_not_match_after_restore_returns_false_and_keeps_the_backups`.
18. `scripts/osaurus-pin.sh:31-37,69-84` — the only restore triggers on the shell side (trap INT/TERM/HUP + explicit `osaurus_restore_check`); a runner exit path that fires neither leaves Jason's host pinned (idle 900) — guards: none in-repo (shell; exercised only by live runs, e.g. `scripts/run_canary.sh`).
19. `scripts/osaurus-pin.sh:46-67` `osaurus_set_seqs` — non-atomic rewrite of the live host config (`json.dump` straight to the file) + baseline re-record; crash mid-write leaves a half-written `server-runtime.json` (recoverable only via the pin's backup) — guards: none in-repo.
20. `ohyesmlx/runtimes.py:145-173` the never-by-name tables (OSAURUS_APP_BUNDLES/EXECUTABLES, ENGINE_BUNDLE_EXECUTABLES) — every "never by name" guarantee reduces to these tuples; the two-bundle-capitalisation case is the documented trap — guards: `test_the_osaurus_bundle_executable_is_derived_from_the_bundle_spellings`, `test_osaurus_version_prefers_the_bundle_that_is_serving`.

## 5. Mechanical scan

Grep results, one line each, over the three scope files. "None" means zero hits. Not judged, only located.

### Section-scope patterns

- `SIGKILL`: `runtimes.py:1630` (`_kill_resident` sends it), `runtimes.py:1677` (`_shutdown` escalation), `runtimes.py:1634,1680` (survival error messages), `runtimes.py:3158` (Vmlx class comment).
- `SIGTERM`: `runtimes.py:1623` (comment: ignored by stale Osaurus instances), `runtimes.py:1675` (`_shutdown` sends it), `runtimes.py:3158` (comment).
- `killpg`: `runtimes.py:653` (`os.killpg(os.getpgid(pid), sig)` in `_signal_tree`).
- `pkill`: none.
- `pgrep`: none.
- `lsof`: `runtimes.py:125` (LSOF constant), `runtimes.py:679,692` (docstrings), `runtimes.py:685,703` (the two probes), `runtimes.py:1650` (error message names the command).
- `osaurus`: 60 hits in `runtimes.py`, 12 in `osaurus-settings`-adjacent lines of `runtimes.py`'s imports (:83-90), 20 in `osaurus_settings.py`, 25 in `scripts/osaurus-pin.sh`. The load-bearing ones: `runtimes.py:145-172` (bundle tables + "never by the name `osaurus`"), `:634-648` (`_resident_osaurus_pids`), `:2300-2304` (the pre-start refusal), `:2523` (`osaurus serve --port … --yes`), `:2557` (`("osaurus", "stop")`), `:2601` (`osaurus doctor --json --redact`), `:3806` (registry); `osaurus_settings.py:42-50` (config dir / PIN_FILES), `:227-286` (pin), `:339-384` (restore/recover); `osaurus-pin.sh:17-22` (paths), `:24-37` (restore/pin), `:46-67` (set_seqs), `:69-84` (restore_check). (Full line list available; abbreviated here for the token budget.)
- `1337`: `runtimes.py:695` (docstring), `:1620` (docstring), `:3806` (Osaurus port); `osaurus_settings.py:4` (docstring).
- `8080`: `runtimes.py:3808` (OptiQ port).
- `8081`: `runtimes.py:16-17` (mlx-lm dead-load trap docstring), `:3805` (MlxLm port).
- `8100`: `runtimes.py:3807` (oMLX port).
- `8000`: `runtimes.py:3809` (vMLX port).
- `8200`: `runtimes.py:3810` (Mtplx port).
- `--stream-experts`: `runtimes.py:361,364` (comments: OptiQ's flag + the 0.70×RAM auto), `:2916` (`stream = ("--stream-experts",)`), `:3072` (Optiq docstring).
- `--max-context`: `runtimes.py:2945` (pinned `off` inside Optiq.start_command).
- `--no-cache`: `runtimes.py:2380` (prompt_cache_flags docstring), `:2758,2765` (Omlx passes it unless `on`); `osaurus_settings.py:16` (docstring).
- `plist`: none in scope files (the plist surface exists only in `docs/runtimes/osaurus.md:498-527` — see §7 Q4).

### Python patterns (all three are Python-free here except the two modules)

- `shell=True`: none.
- `os.system`: none.
- `eval(`: none.
- `exec(`: none.
- `pickle`: none as code; the word appears once in a docstring (`runtimes.py:3648`, MTPLX's pickled session bank, a file the harness deletes).
- bare `except:`: none.
- `except Exception: pass`: none (the one `except Exception` at `runtimes.py:2348-2351` reports the ledger failure to stderr_json and lets the start continue; `except BaseException` blocks at `runtimes.py:1721-1723`, `osaurus_settings.py:196-198` clean up a temp file and re-raise).
- `chmod`: `osaurus_settings.py:195` (restore the user's file mode on the temp before replace), `:271` (backup dir 0700).
- `tempfile.mktemp`: none (scratch dirs use `tempfile.mkdtemp` at `runtimes.py:1555-1577`/`3633-3669` region; ledger/settings temps are fixed-name siblings — see hotspots 9, 19).
- `open(` with `w` on a path built from input: `runtimes.py:1717` (`_write_ledger` temp; path derives from `writable_root()` + own pid, not request input), `runtimes.py:596` (`_spawn` log; name is a runtime name from the registry), `osaurus_settings.py:188` (`_write_atomic` temp; target is a config or backup path the caller names), `osaurus-pin.sh:61` (`json.dump(runtime, open(conf, 'w'))` — the fixed `$CONF` host path; non-atomic, hotspot 19).
- `subprocess` without a timeout: `runtimes.py:599-607` (`_spawn`'s Popen — a server, intentionally long-lived, timeout lives in await_ready/stop instead). Every `_run` helper carries `timeout_s` (`:573-584`).
- `json.loads` on unbounded input: `runtimes.py:939` (a config-sized JSON object file), `:1134` (bounded: `handle.read(length)` of a safetensors header), `:1432,1455` (`response.read()` of `/models` and `/health`, urllib timeout 5 s), `:1696` (ledger file), `:2668` (`osaurus doctor --json` output, VERSION_TIMEOUT_S); `osaurus_settings.py:115,140,170` (host config / baseline files). None is network-unbounded without a timeout; the file reads are same-user local files.
- `signal.`: `runtimes.py:1630,1675,1677` (the three send sites).
- `os.kill` family: `runtimes.py:626` (`kill(pid, 0)` liveness), `:653` (`os.killpg`), `:671` (`os.kill`).
- `os.waitpid`: `runtimes.py:619` (WNOHANG reap of own children).
- `Popen`/`start_new_session`: `runtimes.py:599,605`.
- `terminate(`: none.

### Swift patterns

Not applicable: no Swift in scope (the `app/` project is other sections; S5 is the three files above).

## 6. Test inventory

Per hotspot (§4 numbering). All names are in `tests/test_runtimes.py` unless noted. Line numbers are the test's
def line in that file, for orientation only.

| Hotspot | Tests that fail if it breaks |
|---|---|
| 1 signals (`_signal_tree`/`_signal_process`) | `tests/test_runtimes.py::test_stop_escalates_to_sigkill_when_sigterm_is_ignored` (:2691), `::test_stop_raises_if_spawned_pid_survives_sigkill` (:2674), `::test_a_listener_that_is_the_spawned_pid_is_not_signalled_twice` (:2851) |
| 2 `_resident_osaurus_pids` | `::test_start_refuses_stale_osaurus_app_by_full_executable_path` (:2502), `::test_start_does_not_match_osaurus_mcp_or_other_binary` (:2517), `::test_resident_osaurus_pids_never_runs_a_ps_found_on_path` (:2530) |
| 3 `_shutdown` | `::test_stop_does_not_return_while_the_port_is_still_held` (:2655), `::test_stop_refuses_handoff_cleanup_when_listener_probe_is_unavailable` (:2709), `::test_stop_runs_the_runtimes_own_stop_command` (:2720), `::test_stop_raises_when_the_port_never_comes_free` (:2758), `::test_stop_verifies_the_port_even_when_the_process_already_exited` (:2775), `::test_vmlx_stop_is_a_signal_because_there_is_no_stop_subcommand` (:2739) |
| 4 `_kill_resident` | `::test_stop_kills_the_process_the_launcher_left_holding_the_weights` (:2823), `::test_stop_does_not_return_while_that_process_still_lives` (:2838) |
| 5 `_stop_orphan` | `::test_a_dead_owners_matching_engine_is_stopped_through_shutdown` (:3827), `::test_an_osaurus_shaped_entry_with_a_dead_launcher_is_stopped` (:3847), `::test_a_reused_launcher_pid_blocks_the_osaurus_shaped_stop` (:3886), `::test_a_stranger_listening_on_the_recorded_port_is_dropped` (:3925), `::test_an_unreadable_port_is_dropped_and_never_signalled` (:3942), `::test_a_listener_whose_recorded_identity_no_longer_matches_is_dropped` (:3956), `::test_a_reused_pid_is_dropped_and_never_signalled` (:4002), `::test_a_matching_pid_with_a_different_argv_is_dropped_and_never_signalled` (:4023) |
| 6 `stop_orphaned_engines` | `::test_a_live_owners_ledger_is_never_read_or_touched` (:4042), `::test_a_stop_that_does_not_take_effect_keeps_the_ledger_file` (:3981), `::test_a_json_file_that_is_not_a_ledger_is_left_alone` (:4057) |
| 7 `stop_own_engines` | `::test_stop_own_engines_stops_only_this_processes_entries_and_never_writes` (:4103), `::test_stop_own_engines_reports_a_failing_stop_and_still_stops_the_next` (:4133), `::test_stop_own_engines_without_a_readable_ledger_is_zero` (:4161) |
| 8 `Runtime.start` | `::test_start_refuses_a_port_this_run_does_not_own` (:2481), `::test_start_refuses_when_process_inspection_is_unavailable` (:2492), `::test_start_surfaces_cleanup_failure_chained_from_start_error` (:2547), `::test_start_reports_the_servers_error_and_still_frees_the_port` (:2568), `::test_start_fails_when_the_process_exits_before_it_is_ready` (:2464), `::test_the_running_engine_is_recorded_after_the_cold_load_time_is_taken` (:3713), `::test_a_started_engine_is_recorded_with_its_pid_port_and_identity` (:3743), `::test_a_ledger_write_failure_does_not_fail_the_start` (:3808), `::test_start_gives_a_35b_the_full_budget_before_giving_up` (:2454) |
| 9 ledger write/record | `::test_the_ledger_file_is_replaced_atomically` (:4069), `::test_the_ledger_file_is_removed_once_its_last_entry_is_gone` (:4088), `::test_an_osaurus_start_records_the_serving_process_when_the_launcher_is_unreadable` (:3775) |
| 10 `await_ready` | `::test_start_refuses_a_server_whose_load_died_even_though_the_model_is_listed` (:2438), `::test_a_model_that_failed_to_load_as_the_list_answered_is_not_a_started_runtime` (:2581), `::test_start_returns_a_handle_only_after_the_model_id_appears` (:2423), `::test_start_keeps_polling_through_connection_refused` (:2474), `::test_mtplx_a_nonzero_exit_before_the_port_binds_is_a_load_failure` (:2231), `::test_log_parser_*` family (:2372-2421) |
| 11 `_engine_env` | `::test_a_lab_path_is_prefixed_to_path_and_the_rest_of_the_environment_passes_through` (:3349), `::test_a_manifest_with_no_lab_paths_adds_nothing_to_path` (:3364), `::test_a_lab_path_that_does_not_exist_is_refused_naming_the_engine` (:3384), `::test_a_lab_path_nobody_else_can_write_is_still_prefixed` (:3646), `::test_a_lab_path_owned_by_another_user_is_refused_at_start` (:3659), `::test_a_machine_local_lab_path_that_does_not_exist_is_refused_at_start` (:3611), `::test_a_lab_path_nobody_else_can_write_is_still_prefixed` (:3646) |
| 12 `_resolve_program` | `::test_spawn_execs_the_bundle_executable_when_the_name_is_not_on_the_engines_path` (:3433), `::test_run_execs_the_bundle_executable_when_the_name_is_not_on_the_engines_path` (:3451), `::test_a_name_that_resolves_on_the_engines_path_is_left_untouched` (:3470), `::test_an_env_prefixed_command_is_probed_past_the_assignments` (:3478), `::test_the_osaurus_bundle_executable_is_derived_from_the_bundle_spellings` (:3518), `::test_a_name_with_no_resolvable_bundle_still_raises_the_start_error` (:3502) |
| 13 `_spawn` | `::test_spawn_hands_the_engine_env_to_the_process` (:3390) |
| 14 `_serving_pid` | `::test_osaurus_samples_the_app_the_launcher_handed_the_port_to` (:3141), `::test_a_port_that_names_nothing_leaves_the_sampler_on_the_spawned_pid` (:3155), `::test_an_ambiguous_port_samples_the_spawned_pid_rather_than_a_stranger` (:3164), `::test_serving_pid_keeps_spawned_pid_when_listener_probe_is_unavailable` (:2880) |
| 15 drift gate | `::test_osaurus_refuses_to_start_when_the_host_drifted_from_the_baseline` (:3072), `::test_osaurus_refuses_to_start_when_existing_baseline_is_invalid` (:3061), `::test_osaurus_starts_when_the_settings_match_the_baseline` (:3092), `::test_osaurus_starts_when_no_baseline_has_been_recorded` (:3131), `tests/test_osaurus_settings.py::test_baseline_missing_returns_none_but_existing_invalid_data_raises_value_error` (:3027), `::test_capture_reads_every_tracked_measurement_key` (test_runtimes.py :2978) |
| 16 `pin` | `tests/test_osaurus_settings.py::test_pin_backs_up_both_configs_byte_exact_and_applies_the_run_settings` (:85), `::test_pin_writes_the_baseline_the_drift_guard_reads_to_the_given_path` (:108), `::test_pin_never_writes_the_default_baseline_unless_it_is_passed` (:125), `::test_the_backup_directory_is_created_0700` (:136), `::test_a_second_pin_refuses_rather_than_overwriting_the_users_original` (:142), `::test_a_pin_refuses_over_a_leftover_baseline_backup_or_marker` (:161), `::test_a_pin_that_killed_the_write_between_temp_and_replace_leaves_the_files_intact` (:178) |
| 17 `_put_back`/`restore` | `tests/test_osaurus_settings.py::test_restore_puts_every_file_back_byte_exact_and_removes_the_backup` (:227), `::test_restore_puts_the_baseline_back_byte_exact_after_a_later_write` (:246), `::test_a_pin_with_no_baseline_restore_leaves_the_guard_ungated` (:274), `::test_restore_returns_false_and_keeps_every_backup_when_a_file_is_not_byte_identical` (:300), `::test_a_baseline_that_does_not_match_after_restore_returns_false_and_keeps_the_backups` (:321), `::test_restore_without_a_backup_refuses` (:353), `::test_recover_restores_a_backup_a_crash_left_behind` (:392), `::test_recover_restores_the_baseline_with_the_configs` (:415) |
| 18 shell restore triggers | none (shell; the app-side `recover` outcomes are covered in `tests/test_cli.py` :1266-1380, `recovered`/`recovery_pending`/`recovery_failed`/`osaurus_recovery_failed`) |
| 19 `osaurus_set_seqs` | none in-repo (shell; live-run verified per `docs/runtimes/osaurus.md:374`) |
| 20 never-by-name tables | `::test_the_osaurus_bundle_executable_is_derived_from_the_bundle_spellings` (:3518), `::test_osaurus_version_prefers_the_bundle_that_is_serving` (:3174), `::test_osaurus_start_command_is_pinned_and_takes_no_tuning_flags` (:342) |

Cross-cutting pin suites that guard the start commands as a whole: `::test_osaurus_refuses_the_cache_state_the_host_is_not_in` (:740), `::test_osaurus_accepts_the_off_pin_only_while_the_host_is_at_its_default_codec` (:895), `::test_osaurus_accepts_the_off_depth_only_while_the_host_forces_mtp_off` (:1088), `::test_osaurus_accepts_the_off_streaming_state_only_where_the_host_is_not_streaming` (:1160), `::test_osaurus_takes_no_cache_flag_in_either_state` (:699), `::test_the_runtimes_with_no_way_to_reach_a_codec_refuse_it_rather_than_approximating` (:844), `::test_optiq_start_command_is_pinned` (:354), `::test_optiq_pins_expert_streaming_off_rather_than_leaving_it_auto` (:389).

## 7. Open questions for the reviewer

1. **Can any path signal a process by name rather than identity?** (mandated) The signal sites are pid-only
   (`_signal_tree` :651-659 on a spawned pid's group, `_signal_process` :662-675 on one pid, `_kill_resident`
   :1617-1635 on `_listener_pids` output). The residual name-shaped paths: `Osaurus.stop_command` is
   `("osaurus", "stop")` (:2556-2557) — an argv0-by-name invocation of the CLI, run at every Osaurus stop and by
   `_stop_orphan` from a *recorded* entry; and `_signal_tree` signals the whole process *group* of the spawned pid,
   which is only safe while `start_new_session=True` (:605) holds and the pgid is not reused. Is `osaurus stop`'s
   own targeting (it stops "the running server", osaurus.md:144, indistinguishable from Jason's manual instance)
   acceptable given `osaurus mcp` must never be touched — and can `os.getpgid(pid)` at :653 ever return a group
   containing a process this run has no claim on?
2. **Can two models be resident at once?** (mandated) `Runtime.start` refuses only *its own* port and resident
   Osaurus apps (:2279-2304); nothing in this module refuses starting Mtplx on 8200 while an OptiQ on 8080 still
   holds ~20 GB. The one-resident rule (AGENTS.md:98) rests entirely on callers (measure.py's stop-before-start,
   quickbench's sequencing, `stop_own_engines`' manual stop). Is there a caller path — a quickbench "Stop now"
   race, an app relaunch between `stop_orphaned_engines` and the first cell, a failed `_forget_running_engine` —
   where two engines from *different* owners coexist and both are sampled?
3. **Can an Osaurus restore be skipped on any exit path?** (mandated) `scripts/osaurus-pin.sh` restores via the
   `trap … INT TERM HUP` (:32) and `osaurus_restore_check` (:69-84). A runner that `exit`s non-zero without
   calling `osaurus_restore_check`, is SIGKILLed, or hangs past its window fires neither — the host keeps idle-900
   and caches-off until the next app launch's `recover` (v5-hardening.md:37-46), which itself defers with
   `recovery_pending` while the Osaurus app runs. Should the trap also cover EXIT, or is a pinned host state the
   accepted failure mode with `recover` as the safety net? The app-side answer exists; the shell-side answer is
   convention only.
4. **The plist is invisible to the drift gate.** AGENTS.md:92 says everything that determines what you measure
   lives in "`~/.osaurus/config/*.json` **and an app plist**" and demands a snapshot/diff before every run;
   `osaurus_settings.TRACKED_KEYS` (:63-88) covers only the two JSON files, and `docs/runtimes/osaurus.md:498-527`
   shows `~/Library/Preferences/com.dinoki.osaurus.plist` holding `model_options_<modelID>.disableThinking` —
   "decides whether the measured model emits reasoning tokens at all", on for three models on that host. Two cells
   differing only in named model can differ by the entire reasoning-token count with the gate green. Is the plist
   out of scope by decision (it would need `defaults read`, another tool), or an open gap in the attestation?
5. **`LSOF` is still ambient-PATH resolved** (`shutil.which("lsof")`, :125) while `PS` was made absolute under
   T-09 — threat-model §7.4 explicitly excluded it ("not part of this finding") and 045-02a-SUMMARY flagged it as
   a candidate that 045-02b did not take. `_listener_pids` decides which pids get SIGKILLed and `_port_is_free`
   decides whether a start may proceed, so a PATH-shadowed `lsof` chooses both. Same-user-writeable PATH is the
   threat model's own actor for T-12's fix. Should `LSOF` be absolute (`/usr/sbin/lsof`) on the same argument?
6. **mlx-lm venv preflight is still absent.** AGENTS.md ("Runtime hazards") requires that
   `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin` be on PATH and that "`from mlx_lm import load` in that venv" be
   checked before believing a start failure is an unsupported `model_type`; the 2026-09-23 invariants review
   recorded this as UNENFORCED and no code here does it. `_engine_env` only prefixes *lab paths* from
   lab-paths.json; a host without that entry starts `python -m mlx_lm.server` (MlxLm.start_command :2404-2430) from whatever `python`
   resolves to. Is the venv requirement satisfied elsewhere (runner scripts exporting PATH, per AGENTS.md
   "`mlx_lm.server` lives in its own venv … which must be on PATH"), leaving this a documented convention?
7. **A ledger entry's `stop_command` is executed verbatim later.** `_record_running_engine` stores it
   (:1747-1783); `_stop_orphan`/`stop_own_engines` run it through `_run` (:569-585) with no re-validation that the
   argv matches the runtime's current `stop_command`. The identity checks gate the *signals*, but the command runs
   before them (`_shutdown` :1668-1670). A tampered same-user ledger file (`<owner>.json` under the writable root)
   is arbitrary command execution at next app launch. Threat-model treats same-user tamper as mostly out of actor
   ("A same-user writer can already edit `~/.zshrc`", §7.4 T-12) — is that the accepted answer here too, or should
   `_entry_stop_command` validate the recorded argv against the registry's known stop commands?
8. **`osaurus_set_seqs` rewrites the live host config non-atomically** (`scripts/osaurus-pin.sh:54-66`,
   `json.dump(runtime, open(conf, 'w'))`) — the one write in the pin flow that does not go through
   `osaurus_settings._write_atomic`, directly onto Jason's `server-runtime.json`. A crash mid-write leaves it
   half-written; recovery is only via the pin backup + `recover`. Worth routing through the module's atomic write
   (it exists and is the "one definition" the AGENTS.md rule asks for)?
9. **A dropped orphan entry is gone permanently.** `_stop_orphan` drops an entry whose listener set does not
   *exactly* match its records (:1835-1864) — e.g. the recorded engine listener plus one stranger — and
   `stop_orphaned_engines` then removes the file, because a drop raises nothing. The engine keeps its weights with
   nothing tracking it, and the docstring's "a later launch can retry" applies only to stops that raised. Is
   exact-match-and-drop the right asymmetry, or should a partially-matching entry keep its file (and its claim on
   the process) for a later retry?



