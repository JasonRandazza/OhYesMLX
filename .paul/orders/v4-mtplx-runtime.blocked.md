BLOCKED: requirement 6 cannot be implemented inside the allowed file list. The gate it specifies is a
post-measurement verdict read from the measured responses — the final-chunk `mtplx_stats` receipt,
which requirement 8 puts on the `Observation` — and no caller reachable from `ohyesmlx/runtimes.py`
or `ohyesmlx/transport.py` ever sees those observations. The measurement loop's only post-measurement
hook is `Runtime.mtp_depth_missing(mtp_depth, log_path)` (`ohyesmlx/measure.py:869`), handed the log
path and nothing else; `ohyesmlx/measure.py` is excluded ("Touch nothing else"). Every other runtime
hook runs before the start (`cache_state_refusal`/`kv_quant_refusal`/`mtp_depth_refusal`,
`measure.py:782-794`) or before the first request (`stream_experts_missing`, `:850`). None receives
`CellResult.observations`.

Evidence assembled for this report:

- The hook inventory above is the whole of it: `measure.py:782, 788, 794, 814, 840, 850, 869`. No
  hook takes observations, and a new field on `Observation` does not change that.
- The receipt exists only in the SSE stream. The 2026-10-09 probe outputs:
  `probe-oq4e.json` `last_chunk.mtplx_stats` = `{mode: "ar", draft_head_installed: false,
  drafted_tokens: 0}` (uingei/Qwen3.5-4B-oQ4e, the silent degrade); `probe-optiq4b.json` =
  `{mode: "mtpk", draft_head_installed: true, drafted_tokens: 67, accepted_drafts: 60}`
  (mlx-community/Qwen3.5-4B-OptiQ-4bit).
- The log cannot stand in for the receipt. Every request logs
  `{"event": "mtplx_openai_generation", "prompt_tokens": …, "tok_s": …, "seed": …}` with no
  mode/drafted fields (`probe-optiq4b.log`, last line; same shape in `probe-oq4e.log`), and the only
  log-side degrade evidence is the one-way marker `mtp_heads not found -> mtp_off: serving
  autoregressive` (`probe-oq4e.log:26-27`) — it can prove AR, never `drafted_tokens > 0`. So
  `mtp_depth_missing(mtp_depth, log_path)` cannot carry requirement 6 either.
- `/health` does discriminate the two probe states (`generation_mode` `"ar"`/`runtime_mode`
  `"Sustained AR"` vs `"mtp"`/`"Sustained MTP"`) and is reachable from `Mtplx` through its own port,
  but it is not the receipt and cannot show `drafted_tokens > 0`; substituting it would be an
  approximation.

Why I stopped rather than shipping a best effort: the only implementable-in-allowlist pieces of
requirement 6 are an uncalled `mtplx_mtp_refusal` — the predecessor project's defect ("a token path
no caller used"), here leaving the N>0 path ungated — or a policy the order does not specify (allow
every depth ungated, or refuse every depth outright). Shipping either silently is a guess.

What I need decided (any one of these unblocks the whole order):

1. **Add `ohyesmlx/measure.py` to the allowlist (my recommendation).** At `measure.py:869`, hand the
   visit's observations to the depth check — e.g.
   `runtime.mtp_depth_missing(mtp_depth, handle.log_path, observations=[o for r in results for o in r.observations])`,
   or a `mtplx_mtp_refusal(mtp_depth, observations, artifact_dir)` asked beside it — and the gate is
   exactly requirement 6's three fields, with the reason naming the artifact. Also decide the
   absent-receipt semantics (I propose FAIL with the artifact named, mirroring
   `stream_experts_missing`'s no-log branch) and whether the verdict is per-cell or per-observation.
2. **Keep the allowlist; re-scope requirement 6 to the log half.** `Mtplx.mtp_depth_missing` reads
   `mtp_heads not found -> mtp_off` from the log and FAILs N>0 on it; the positive receipt stays
   recorded in the raw row but ungated. Catches the uingei oQ4e case; blind to a silent degrade that
   logs nothing.
3. **Keep the allowlist and defer depth cells.** `Mtplx.mtp_depth_refusal` returns N/A for every
   N>0 ("the receipt this pin is gated on cannot be handed to any hook until the loop passes
   observations"), so the runtime ships now for `off`/AR cells with no ungated depth path.

Secondary notes for whichever branch is taken:

- Requirement 8's field flows through `measure._record`'s `asdict`, so every raw observation gains
  `"mtplx_stats": null` (other runtimes included) and
  `tests/test_measure.py::test_load_run_round_trips_every_record_of_a_real_run` needs one expectation
  line, exactly as it already patches `cached_tokens` (that test file is in the allowlist).
  `Observation(**raw)` reads old records leniently through the field default.
- Everything else is implementable as written inside the allowlist: the `Mtplx` class
  (`~/.mtplx/bin/mtplx`, port 8200, `--model-id` pinned to a served name readiness resolves,
  `--no-stats-footer --ssd-session-cache off`), the `on` cache scratch via a `build_command`
  override (removed by the existing `Handle.scratch` path in `stop()`), the `off` cache refusal with
  the RAM-session-bank reason, the depth command flags (`--no-mtp --generation-mode ar` /
  `--depth N --generation-mode mtp`), the `kv_quant` refusals, the base `stream_experts`, and the
  readiness override (`/health` ok + `/v1/models` id, nonzero exit before bind included). `cli.py`
  needs no change — it does not enumerate runtimes (it imports only the pin constants).
- Baseline: 658 passed (`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`,
  37.4 s). Nothing was changed on this dispatch, so there is no red-check to report — the suite is
  still at its baseline.
