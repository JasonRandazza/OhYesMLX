# Order: add MTPLX as the sixth runtime (v4.0 phase 2)
Goal: an `Mtplx` Runtime class so `--cells` can start/measure/stop `mtplx serve`, with a refusal gate and the stats receipt kept in the raw row.
Read first: docs/research/2026-10-09-mtplx-load-probes.md, docs/research/2026-10-06-mtplx-surface.md (§2, §10, §11), docs/research/2026-10-06-mtplx-integration-plan.md (§4 Phase 2), docs/interfaces.md, and the Optiq / Vmlx classes plus optiq_mtp_refusal / vmlx_mtp_refusal in ohyesmlx/runtimes.py.
Files you may touch: ohyesmlx/runtimes.py, ohyesmlx/transport.py (receipt field only), ohyesmlx/cli.py (only if runtimes are enumerated there), tests/ for these, docs/interfaces.md (only if a shape changes). Touch nothing else. No servers, no models, no git.
Requirements:
1. `Mtplx(Runtime)`: binary `~/.mtplx/bin/mtplx`; port 8200; `start_command` = `mtplx serve --model <artifact> --host 127.0.0.1 --port <port> --model-id <the id readiness looks for> --no-stats-footer --ssd-session-cache off` plus pins. cache_state `on` -> `--ssd-session-cache on --ssd-session-cache-dir <per-run scratch>` so stop() removes it; the RAM session bank has no flag, so `cache_state=off` must be REFUSED for now with that reason (open item in the probes doc), not claimed.
2. Version from `mtplx --version` (`mtplx 2.12.2` -> `2.12.2`), recorded like the other runtimes.
3. No request seed (greedy-inert at temp 0); document in `request_seed` rationale by pointing at the probes doc, not restating.
4. Readiness: `/health` ok + `/v1/models` id match; a nonzero process exit before bind is a load failure (JANG_4S probe exits 1 at load).
5. Depth pin: `mtp_depth` off -> `--no-mtp --generation-mode ar`; N -> `--depth N --generation-mode mtp` (family max 3).
6. `mtplx_mtp_refusal`, mirroring optiq_mtp_refusal/vmlx_mtp_refusal: a depth pin N>0 FAILS the cell unless the final-chunk `mtplx_stats` shows `mode` != "ar", `draft_head_installed` true and `drafted_tokens` > 0 (the uingei oQ4e probe returns HTTP 200 in mode "ar" with drafted 0). Reason text names the artifact.
7. `kv_quant`: refuse existing affine values with a reason (MTPLX q8/q4 is a different codec); `stream_experts`: base default.
8. Transport keeps the final chunk's `mtplx_stats` object verbatim in the raw observation (new optional field; absent for other runtimes). Raw rows are never truncated.
9. Tests mirroring the Optiq/Vmlx tests: command construction, refusal gate on a receipt with drafted 0 vs drafted 67, version parse, port. Run the suite with /Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q; baseline 658 passed.
Acceptance: suite green with new tests; red-check the refusal test by reverting the gate. Report DONE or BLOCKED, with the diff summary and the count.

## Amendment 2026-10-09 (coordinator decision on your BLOCKED report: option 1)
Your report is in .paul/orders/v4-mtplx-runtime.blocked.md. Do NOT write BLOCKED.md at the repo root or edit .paul/STATE.md (a previous run did both; they were reverted).
- Allowlist now also: ohyesmlx/measure.py, tests/test_measure.py.
- At measure.py:869 hand the visit's observations to the depth check, as you proposed
  (`mtp_depth_missing(mtp_depth, log_path, observations=...)` or an equivalent beside it). Keep other runtimes' behaviour byte-identical.
- Absent receipt with N>0 = FAIL, reason names the artifact (mirror stream_experts_missing's no-log branch). Verdict is per cell: any observation in the visit with mode "ar" or drafted_tokens == 0 fails the cell; all must show draft_head_installed true and drafted_tokens > 0.
- Add the one expectation line to test_load_run_round_trips_every_record_of_a_real_run for the new `mtplx_stats` field, as `cached_tokens` is handled.
- Everything else as in the order and your "implementable as written" list.
