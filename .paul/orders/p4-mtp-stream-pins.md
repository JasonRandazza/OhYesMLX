## Order: `--mtp-depth` and `--stream-experts` header pins (Phase 4, studies 03-06, 03-03)

Jason approved both 2026-09-24. Build each exactly like `kv_quant` (commit eec6480): header
field, `Runtime.<pin>_refusal()` asked before start, `PIN_FIELDS`/`ABSENT_PINS`/`SWEEP_PINS`/
`SWEEP_VALUES`, CLI flag with `choices`, `docs/interfaces.md`. Absent pin (`None`) must leave every
start command byte-identical to today (test all five runtimes).

Files you may touch: `ohyesmlx/runtimes.py`, `ohyesmlx/measure.py`, `ohyesmlx/cli.py`,
`ohyesmlx/report.py`, `docs/interfaces.md`, `docs/runtimes/vmlx.md`, `docs/runtimes/optiq.md`,
the matching `tests/test_*.py`, and any `scripts/*.py` whose `start_command` override breaks.
Touch nothing else.

Step 1 — verify before coding, against installed source (vMLX:
`/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/`; OptiQ:
`/Users/jrazz/Dev/tools/mlx-optiq/`). Cite file:line in the docstrings. If a fact below is
wrong, stop and report BLOCKED with the evidence.

`mtp_depth` ∈ `off`, `1`, `2`, `3`:
- vMLX only. Today it passes `--disable-native-mtp` (`runtimes.py` ~1446); that stays for absent
  and `off`. Depth N → drop the disable, `--native-mtp-depth N --native-mtp-depth-policy fixed`
  (adaptive changes depth mid-run: `docs/runtimes/vmlx.md` §7.4). Confirm what vMLX does when the
  bundle has no MTP tensors; if it silently falls back, the depth cell must not be measured as
  MTP — refuse up front if it can be decided from the artifact on disk, else say how it can be
  detected and stop there (BLOCKED question, not a guess).
- Every other runtime: `off` accepted when evidenced as its only state, depth values refused.

`stream_experts` ∈ `off`, `on`:
- OptiQ: today pins `--no-stream-experts`; that stays for absent and `off`; `on` →
  `--stream-experts`. OptiQ silently falls back to a resident load (`docs/runtimes/optiq.md`
  ~955-970), so `on` is only true when its log shows `SSD expert streaming: on`. Find whether the
  harness keeps the server's output; if it does, make an `on` cell without that banner fail with
  the log line quoted; if it does not, report that as BLOCKED.
- vMLX: `on` → `--flash-moe` (default off, `flash_moe_config.py:29`); confirm it has a fallback
  signal too and treat it the same way.
- mlx-lm, oMLX, Osaurus: `off` only where evidenced; `on` refused (Osaurus `smeltMode` is host
  state; oMLX burst decode is not the same mechanism — say so with citations).

Rationale once, at each pin's value constant. Tests for each mapping, refusal, byte-identity,
join and sweep order. Red-check. Suite green; baseline 572.
