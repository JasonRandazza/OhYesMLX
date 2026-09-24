## Order: extend the `--mtp-depth` pin to OptiQ (Phase 4, study 03-06)

Jason approved 2026-09-24. Today `mtp_depth` is vMLX-only (`runtimes.py` ~153-210,
`vmlx_mtp_refusal`). OptiQ also has native MTP: `optiq serve --mtp --mtp-depth N`
(`optiq/cli.py:2554-2563`, `:3027-3060`; `optiq/serve.py:418-466`, `:531-534`). Its heads live in
a sidecar, `<model>/optiq/mtp.safetensors` (present for `mlx-community/Qwen3.5-4B-OptiQ-4bit` and
`mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` in the HF cache).

Files you may touch: `ohyesmlx/runtimes.py`, `ohyesmlx/measure.py`, `ohyesmlx/cli.py`,
`ohyesmlx/report.py`, `docs/interfaces.md`, `docs/runtimes/optiq.md`, the matching
`tests/test_*.py`. Touch nothing else.

Step 1 — verify against installed source (`/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq/`),
cite file:line. Stop with BLOCKED + evidence if any of these fails:
- the harness's OptiQ start command satisfies `--mtp`'s `--model <path>` requirement (cli.py:3029-3043);
- `--mtp-depth N` is a fixed depth (no adaptive change mid-request) — if adaptive, find the pin that fixes it;
- the harness's streaming chat requests actually go through the MTP generate path (check `serve.py`
  and `--max-concurrent` batching; if batched requests bypass MTP, report it);
- what OptiQ does when the artifact has no head (serve.py:459-463): error or silent fallback.

Build:
- OptiQ: absent and `off` → start command byte-identical to today (no `--mtp`). Depth N ∈ 1,2,3 →
  `--mtp --mtp-depth N`.
- `optiq_mtp_refusal(artifact_dir)`: N/A with reason unless `optiq/mtp.safetensors` exists (and any
  other static condition Step 1 shows is required). Mirror `vmlx_mtp_refusal`'s shape.
- Post-start banner check, same pattern as `stream_experts_missing()`: a depth cell FAILs with the log
  quoted unless the log head shows OptiQ's MTP-ready line (take the exact string from serve.py:465).
- Update the `MTP_DEPTHS` rationale comment: it currently says vMLX is the only runtime with MTP.
  That is false. Say which runtimes the pin drives (vMLX, OptiQ) and, citing source, why the others
  refuse depth values: oMLX `mtp_enabled` is a per-model settings boolean with no depth
  (`/Applications/oMLX.app/Contents/Resources/omlx/model_settings.py:170`); Osaurus `mtp.mode`/
  `mtp.explicitDepth` is host config and requires `vmlx_mtp_tuning.json` (`docs/runtimes/osaurus.md`
  §3.3, §8.4); mlx-lm drops `mtp.*` weights at load (`mlx_lm/models/qwen3_5.py:313` in
  `~/.local/share/ohyesmlx/mlx-lm-0.31.3`). Write it once, at the constant.
- `docs/runtimes/optiq.md`: the MTP rows and a short section on how the pin maps.
- Tests: mapping, refusal (sidecar present/absent), banner FAIL, byte-identity when absent for all
  five runtimes, join/sweep. Red-check one. Suite green (baseline 618):
  `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
Do not commit. Report the diff summary and the Step 1 findings with citations.
