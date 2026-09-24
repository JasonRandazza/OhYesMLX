## Order: correct the runtime docs on MTP support (research + docs only)

The docs and handoff claimed vMLX is the only runtime here with MTP. That was inferred from flags
and is false. Verify each claim below against the shipped source, then correct the docs.

Files you may touch: `docs/runtimes/omlx.md`, `docs/runtimes/osaurus.md`, `docs/runtimes/vmlx.md`,
`docs/runtimes/mlx-lm.md` if it exists. Touch nothing else (another worker owns `optiq.md` and all
`.py` files — do not edit them).

Claims to verify (cite file:line, correct any that are wrong):
- oMLX: native MTP via per-model setting `mtp_enabled` (no CLI flag), qwen3_5*/qwen3_6*/deepseek_v4*,
  mutually exclusive with dflash, no depth knob; singleton decode + aligned batches only.
  `/Applications/oMLX.app/Contents/Resources/omlx/model_settings.py:170-175`. Find where it is
  read and where the settings file lives; whether it detects a bundle without heads.
- Osaurus: `mtp.mode` (auto/force_on/force_off/speculative/blocked), `mtp.explicitDepth` 1-3,
  refuses force-on without `vmlx_mtp_tuning.json` (`docs/runtimes/osaurus.md` §3.2-3.3, §8.4).
  What does `auto` do on a bundle with heads? Osaurus ships a vMLX engine — say whether it is the same MTP path.
- mlx-lm 0.31.3 (`~/.local/share/ohyesmlx/mlx-lm-0.31.3`): `models/qwen3_5.py:308-313` strips `mtp.*` on load; confirm no MTP decode path exists in server/generate.
- vMLX: reads heads only from `model.safetensors.index.json` `mtp.*` tensors; confirm it cannot read OptiQ's `optiq/mtp.safetensors` sidecar.

In each doc add or fix an MTP subsection: control surface (flag / settings key / per-request), depth
range, what happens without heads, citations. Where evidence is only "no flag", write exactly that.
Do not commit. Report each verdict with its citation.
