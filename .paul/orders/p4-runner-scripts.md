## Order: Phase 4 sweep runner scripts (tonight's measurement)

Write four runner scripts and one wrapper, modelled on `scripts/run_sweep_cache.sh` (copy its
port sweep, the stale-Osaurus sweep by FULL executable path, the abort trap, `exec >` runner log,
one log per run, and make `OUT` overridable: `OUT=${OUT:-results/<name>}`). Resolve 35B paths with
`. scripts/gridspec-35b.sh` ($Q4, $S4, $OQ). Read `ohyesmlx/cli.py` for the exact `run` flags
(`--kv-quant`, `--mtp-depth`, `--stream-experts`, `--workloads`, `--prompt-tokens`, `--study`,
`--cells`, `--results-dir`); do not guess flag names.

Files you may create: `scripts/run_sweep_kvquant.sh`, `scripts/run_sweep_mtp.sh`,
`scripts/run_sweep_streaming.sh`, `scripts/run_multiturn.sh`, `scripts/run_phase4_night.sh`.
Touch nothing else. Do not edit `ohyesmlx/`. Another worker is editing `ohyesmlx/*.py` right
now (adding OptiQ to `--mtp-depth`); do not run the test suite and do not run any measurement.

| script | runtimes × artifact | varying | extra |
|---|---|---|---|
| kvquant | all five × `oq4` ($Q4) | `--kv-quant` off/affine8/affine4 | `--prompt-tokens` 16384 and 32768 |
| mtp | vMLX × JANGQ-AI/Qwen3.5-4B-JANG_4S; OptiQ × mlx-community/Qwen3.5-4B-OptiQ-4bit; OptiQ × $OQ | `--mtp-depth` off/1/2/3 | resolve the 4B snapshot dirs under `~/.cache/huggingface/hub/models--*/snapshots/*` like gridspec does |
| streaming | OptiQ, vMLX × `stock4bit` ($S4) | `--stream-experts` off/on | — |
| multiturn | all five × `oq4` ($Q4), runtime axis | — | `--workloads multiturn` |

- One results subdirectory per (runtime, artifact) pairing inside `$OUT` wherever `ohyesmlx sweep
  --varying <pin>` needs runs that differ only in the pin; check `report.py`'s sweep join to decide.
- Pin order: alternate direction per runtime (ascending for the first, descending for the next) so
  thermal drift does not alias onto the pin. Keep existing cooldown behaviour from the harness.
- Osaurus needs no settings toggling in these studies; do not copy the cache runner's
  osaurus_state/restore code. Keep the stale-app sweep.
- Every script honours `DRY=1`: print each `ohyesmlx.cli run` command instead of running it.
- `run_phase4_night.sh` runs the four in order kvquant → mtp → streaming → multiturn, each with
  its own OUT, logging start/end times; it does not run the 35B replicate.

Acceptance: `sh -n` passes on all five; `DRY=1 sh scripts/run_phase4_night.sh` prints the full
command list with resolved (non-empty) artifact paths — paste that output in your report. Do not commit.
