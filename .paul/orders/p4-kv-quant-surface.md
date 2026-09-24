## Order: research — how each runtime is driven into a KV-cache quantization state

Jason approved a `--kv-quant off|fp8|int4` header pin (2026-09-24), built like `--cache-state`
(`runtimes.Runtime.cache_state_refusal`, `measure.py`, `report.SWEEP_PINS`). Before code, we
need evidence per runtime. This is research only.

Files you may touch: create `docs/research/2026-09-24-kv-quant-surface.md`. Touch nothing else.
Do not start servers. Reading installed source is allowed and expected.

For each of the five runtimes (mlx-lm, OptiQ, oMLX, Osaurus, vMLX) answer, with a file:line
citation into the installed source/app bundle or into `docs/runtimes/<name>.md`:
1. How is KV-cache quantization turned on (flag, settings key, env var, per-request field)?
   Which bit widths / codecs exist? What is the default when nothing is set — is it truly off,
   or is something automatic (vMLX loader-level TurboQuant, OptiQ fused path, Osaurus
   `cache.liveKVCodec`)?
2. Map `off`, `fp8`, `int4` onto it. Say plainly where the mapping is not exact (e.g. "8-bit
   affine" is not fp8) and propose honest value names if `fp8` is the wrong label for what
   these runtimes actually do. This naming question is the most important output.
3. Can the harness pin `off` explicitly so the default cannot drift?
4. Anything that changes other state as a side effect (quantized-kv-start offset, group size,
   memory path, disabled features).
Existing notes: `docs/runtimes/optiq.md` §7.7 and flag table, `docs/runtimes/vmlx.md` §7.2,
`docs/runtimes/osaurus.md` cache keys. mlx-lm's venv is `~/.local/share/ohyesmlx/mlx-lm-0.31.3`;
oMLX and Osaurus ship readable Python/config in their bundles or `~/.omlx`, `~/.osaurus`.

Rule: absence of a flag is not evidence that a runtime cannot do it. If you only found no flag,
write exactly that, and say where else you looked. End with a table: runtime × value →
how to drive it, or N/A with the evidenced reason.
