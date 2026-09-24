## Order: documentation corrections from the KV-quant surface research

Source of truth: `docs/research/2026-09-24-kv-quant-surface.md` §7, §8, §10.5. Documentation only.

Files you may touch: `docs/research/2026-09-20-quantized-kv-caches.md`,
`docs/runtimes/optiq.md`, `docs/runtimes/vmlx.md`, `docs/runtimes/osaurus.md`. Touch nothing else.

Acceptance criteria:
1. `2026-09-20-quantized-kv-caches.md`: add a caveat at the top, beside its existing caveat, in
   the same style: its vMLX `fp8`/`int4` arms passed `--kv-cache-quantization q8|q4` with the
   prefix cache disabled, which makes the codec a logged no-op (cite vMLX `scheduler.py:1393-1404`),
   so those rows are not a KV codec comparison; and every "FP8" arm in the paper was MLX affine
   8-bit, not float8. Do not delete or rewrite the paper's numbers or conclusions — mark them.
2. `optiq.md`: update the flag line citations and version per §8 (0.5.13, `cli.py:2502-2509`,
   `:2593`); keep §7.7's substance; add the batch-vs-sequential fallback note with its citation.
3. `vmlx.md` §7.2: correct per §8 (1.6.59 CLI pre-sets `VMLX_DISABLE_TQ_KV=1`, so the loader's
   auto path is unreachable by default); add that `q4`/`q8` is storage-only and inert without the
   prefix cache, with citations. Mark superseded text as superseded rather than deleting it.
4. `osaurus.md`: note installed 0.25.12, the request-side `kvBits`/`kvMode` cluster and the
   batched-decode fallback (string-table evidence only — say so; unverified live).
5. Every change cites the research doc section it came from. No claim beyond the research doc.
