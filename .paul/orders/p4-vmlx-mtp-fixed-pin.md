## Order: vMLX depth N really means fixed depth N (Phase 4, study 03-06)

Jason approved 2026-09-25. Your predecessor's BLOCKED finding (verified by the coordinator) stands:
vMLX 1.6.59 `--native-mtp-depth-policy fixed` only disables the economics probe
(`mllm_batch_generator.py:6397-6418`); the sticky start rung (`:17282-17286`, gated by
`VMLX_NATIVE_MTP_AR_REENTRY`, `:6345-6348`) and the AR-safety valve (`native_mtp_ar_safety.py:114`,
`VMLX_NATIVE_MTP_AR_SAFETY`, `cli.py:4327-4328`) still move depth. In last night's logs depth 3
drafted at D3 in 5 of 104 requests. Source: `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/`.

Files you may touch: `ohyesmlx/runtimes.py`, `ohyesmlx/measure.py`, `docs/runtimes/vmlx.md`,
`tests/test_runtimes.py`, `tests/test_measure.py`. Touch nothing else.

Build:
1. vMLX depth N ∈ 1,2,3: the start command also sets `VMLX_NATIVE_MTP_AR_SAFETY=0` and
   `VMLX_NATIVE_MTP_AR_REENTRY=0`, visibly in the recorded command (e.g. an `env K=V ...` prefix) so
   provenance carries it. Absent and `off`: byte-identical to today. Verify first, citing file:line,
   that both vars are read by the process the harness spawns and that `0` disables them; BLOCKED if not.
2. `Vmlx.mtp_depth_missing(mtp_depth, log_path)`: for depth N>1, FAIL with the log quoted (same
   message shape as `Optiq.mtp_depth_missing`) if the log shows either mechanism the pin disables —
   `finish=fallback_to_ar`, or a `start rung D<k>` line with k<N — or if no `accept_by_depth` line has a
   non-zero denominator at `d<N>`. Depth 1: only the last condition. Take exact strings from source and
   from `results/logs/vmlx-20260925T06{2816,3452}-*.log`. The evidence is per request, so the check must
   read after the measured requests and cover the whole log (these logs are ~290 KB); change measure.py
   only as much as that needs, keep one definition of the log window, and say which you used.
3. Rationale once, at the method/constant. `docs/runtimes/vmlx.md`: the fixed-depth mechanics with citations,
   and the residual caveat that `VMLX_NATIVE_MTP_DRAFT_MARGIN` still shortens low-confidence drafts.
Tests: command mapping (depth vs off/absent byte-identity); missing() on real-log excerpts: D3 log with
fallback_to_ar → FAIL, clean D2 excerpt → None, off → None; asked at the new point in measure.py.
Red-check one. Suite green: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
Do not commit. Run no runtime. Report the diff summary and citations.
