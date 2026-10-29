## Order: vMLX depth cells must prove their configured depth ran (Phase 4, study 03-06)

Jason approved 2026-09-25. Last night's MTP sweep published vMLX `mtp_depth=2` and `3` cells as PASS,
but vMLX's own log shows depth 3 never drafted: every `accept_by_depth[...]` line reads `d3=0/0`,
and depth 2/3 runs log `start rung D1 ... promotion probe to D2 after 8 cycles` and
`finish=fallback_to_ar` despite `policy=fixed configured=D3`. Evidence:
`results/logs/vmlx-20260925T06{2149,2516,2816,3150,3452,3819}-*.log` (depth 1,1,2,2,3,3).
OptiQ already has the equivalent check: `Optiq.mtp_depth_missing` (runtimes.py ~2075), called from
measure.py ~817. vMLX has only the default (returns None).

Files you may touch: `ohyesmlx/runtimes.py`, `ohyesmlx/measure.py`, `docs/runtimes/vmlx.md`,
`tests/test_runtimes.py`, `tests/test_measure.py`. Touch nothing else.

Step 1 — read vMLX's installed source (find `vmlx_engine/mllm_batch_generator.py` under the vMLX
app/venv; `docs/runtimes/vmlx.md` names the install) and cite file:line for:
- what `--native-mtp-depth-policy fixed` does, and why it still starts at rung D1 and probes;
- whether any flag/env truly fixes depth N from the first cycle. If one exists, report it — do NOT
  add it (that is a new pin; Jason decides);
- what exactly the `accept_by_depth[d1=a/b,d2=..,d3=..]` and `finish=` fields mean.

Build `Vmlx.mtp_depth_missing(mtp_depth, log_path)`: for depth N, FAIL (log quoted, the same message
shape as OptiQ's) unless the server log shows the configured depth actually drafted — at least one
`accept_by_depth` line with a non-zero denominator at `d<N>`. If the log is read before any request
has run, the check must be asked after the measured requests instead; change measure.py only as
much as that needs, and keep one definition of the log-reading window (`_banner_evidence` /
`LOG_HEAD_BYTES` or a documented tail read — the evidence is per-request, so a 1 MiB head may miss it;
decide from the real log sizes above and say which). `off`/absent: unchanged, no evidence required.
Rationale written once, at the method. Update `docs/runtimes/vmlx.md` with the Step 1 findings.

Tests: depth-3 log with `d3=0/0` → FAIL; depth-2 log with `d2=7/12` → None; off → None; the check is
asked at the point measure.py now asks it. Build fixtures from excerpts of the real logs above.
Red-check one. Suite green: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
Do not commit. Do not run any runtime or measurement. Report the diff summary and Step 1 findings
with citations.
