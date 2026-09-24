## Order: the `--kv-quant` header pin (Phase 4, study 03-05)

Jason approved a KV-quant pin 2026-09-24. Evidence: `docs/research/2026-09-24-kv-quant-surface.md`
(read §1, §2.3, §9, §11). Values are **`off`, `affine8`, `affine4`** — `fp8` is false for every
runtime here. Build it exactly like the existing `cache_state` pin: follow every place
`cache_state` / `CACHE_STATES` / `cache_state_refusal` appears and mirror it.

Files you may touch: `ohyesmlx/runtimes.py`, `ohyesmlx/measure.py`, `ohyesmlx/cli.py`,
`ohyesmlx/report.py`, `docs/interfaces.md`, `tests/test_runtimes.py`, `tests/test_measure.py`,
`tests/test_report.py`, `tests/test_cli.py`. Touch nothing else.

Acceptance criteria:
1. `run --kv-quant {off,affine8,affine4}`; absent = `None` = "not pinned", recorded in the header
   as `kv_quant`. An absent pin changes no start command: every command recorded before this
   pin exists stays byte-identical (test it for all five runtimes).
2. `Runtime.kv_quant_refusal(kv_quant) -> str | None`, asked before anything starts, exactly
   where `cache_state_refusal` is asked. A refused cell is N/A with the reason, never measured.
   - OptiQ: drives all three. `affine8` → `--kv-bits 8 --kv-group-size 64`, `affine4` →
     `--kv-bits 4 --kv-group-size 64`; `off` → neither flag (no explicit off exists; say so at
     the method). Leave OptiQ's fused-KV auto path alone — it is the runtime as shipped — and
     name it in one comment with the citation.
   - vMLX: `off` → `--kv-cache-quantization none` (only when the pin is `off`, never when
     absent). `affine8`/`affine4` → refused: the codec quantizes only the prefix-cache storage
     copy, generation stays full precision, and it is a no-op under `--disable-prefix-cache`;
     cite `scheduler.py:1393-1404` / `:2444-2458`.
   - mlx-lm and oMLX: `off` accepted with no flag change; codec values refused with the
     evidenced reason from §11 (no server surface / oMLX's codec is TurboQuant, not affine).
   - Osaurus: `off` accepted only when the host's `cache.liveKVCodec` is `engine_selected`
     (read it the way `cache_state_refusal` reads its key; add the key to the captured set if
     it is not there); codec values refused.
3. `report`: `kv_quant` joins `PIN_FIELDS`, `ABSENT_PINS` (`None`), `SWEEP_PINS`, and
   `SWEEP_VALUES` (`off`, `affine8`, `affine4`), so `sweep --varying kv_quant` joins runs that
   differ only in it, and a join refuses runs that differ in it otherwise.
4. `docs/interfaces.md` documents the header field and the refusal method next to cache_state.
5. Rationale once, at the definition (the value names and why `fp8` is not one). Callers point.
6. Tests for each runtime's mapping and refusal, the join, the sweep ordering, the CLI flag.
   Red-check them. Suite green; baseline 550.
