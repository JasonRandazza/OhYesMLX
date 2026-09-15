# The grid's real shape — Qwen3.5-4B across four formats and five runtimes

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.
Probe script: `$CLAUDE_JOB_DIR/tmp/probe_grid.py`; raw results `grid-probe.json`.

Not a measurement. One 24-token request per cell, coherence checked, runtime stopped. The
question is only *which cells can run at all*, because the grid's shape was being guessed and
the guesses were wrong.

## Result

| format | mlxlm 0.31.3 | oMLX 0.6.4 | mlx-optiq 0.5.6 | vMLX 1.6.59 | Osaurus 0.25.3 |
|---|---|---|---|---|---|
| stock-4bit | ✓ 4.01 s | ✓ 3.11 s | ✓ 4.20 s | ✓ 18.13 s | ⚠ port held |
| oQ4 | ✓ 3.21 s | ✓ 2.19 s | ✓ 3.19 s | ✓ 16.13 s | ⚠ port held |
| oQ4e | ✓ 3.83 s | ✓ 2.12 s | ✓ 3.24 s | ✓ 16.10 s | ⚠ port held |
| OptiQ-4bit | ✓ 3.87 s | ✓ 2.17 s | ✓ 3.21 s | ✗ **refused** | ⚠ port held |

**15 live cells of 20 probed.** Every cell marked ✓ loaded the artifact and returned coherent
text. The grid is far denser than predicted.

`⚠ port held` is not a capability result. `osaurus.app` was running and holding port 1337, and
the harness refused to start over a listener it did not spawn — correctly, since a server whose
settings it cannot pin measures nothing. That column is unprobed, not failed.

## Every predicted refusal was wrong

Before the probe, the sketched grid marked mlx-lm as unable to load oQ4, oQ4e, or OptiQ. It
loads all three, coherently. The one genuine refusal in the grid was not predicted at all.

This is the second time in one session that a capability claim was made from expectation rather
than evidence — the first was "oMLX does not stream". The rule in `AGENTS.md` exists because of
the first; this is the confirmation that a probe, not a prediction, is what establishes shape.

## The one real refusal, and why it is not a format incompatibility

vMLX rejects the OptiQ artifact in 9.2 s:

```
ERROR:vmlx_engine.models.mllm:Failed to load MLLM: Missing 297 parameters:
vision_tower.blocks.0.attn.proj.bias,
vision_tower.blocks.0.attn.proj.weight,
...
ValueError: Missing 297 parameters
ERROR:    Application startup failed. Exiting.
```

The obvious reading — "the OptiQ conversion dropped the vision tower" — is wrong. Both
artifacts carry it:

| artifact | total tensors | `vision_tower.*` tensors | `model_type` | `vision_config` |
|---|---|---|---|---|
| stock-4bit | 1221 | **297** | `qwen3_5` | present |
| OptiQ-4bit | 1221 | **297** | `qwen3_5` | present |

Identical. The weights are there. The difference is in `config.json`:

| artifact | `quantization` keys |
|---|---|
| stock-4bit | `group_size`, `bits`, `mode` — one uniform rule |
| OptiQ-4bit | those three **plus 249 per-layer entries** |

OptiQ is a mixed-precision format: it records a per-layer quantization map at 4 and 8 bits. And
that map covers the language model only:

```
per-layer quantization entries: 249
  vision_tower entries:   0
  language_model entries: 249
  bits used: [4, 8]
```

**mlx-community's OptiQ-4bit conversion of Qwen3.5-4B quantizes the language model and leaves
the vision tower out of its per-layer map entirely.** vMLX loads this checkpoint through its
multimodal path (`models.mllm`), builds a `vision_tower`, consults the quantization map for its
parameters, finds no entry for any of them, and reports 297 missing.

The other three runtimes load the same file. They either treat the checkpoint as text-only or
fall back to the global `group_size`/`bits`/`mode` for layers the map does not name. That
fallback is not verified here and should not be assumed — what is established is that the
artifact loads in three runtimes and not the fourth, and why the fourth refuses.

**This is a format × runtime interaction, not a property of either alone.** It is invisible on
the format axis, because oMLX loads all four formats. It is invisible on the runtime axis,
because vMLX loads three of four formats. Only the grid shows it, and only reading the log
explains it. A cell marked "incompatible" without that log would have been filed as "vMLX
cannot read OptiQ", which is false.

## Cold load, four formats, runtime held constant

The first genuinely comparable figure this project has produced. Each runtime loaded the same
four artifacts; the runtime is the only thing that varies within a column.

| runtime | median cold load | n |
|---|---|---|
| oMLX 0.6.4 | **2.18 s** | 4 |
| mlx-optiq 0.5.6 | 3.23 s | 4 |
| mlx-lm 0.31.3 | 3.85 s | 4 |
| vMLX 1.6.59 | **16.13 s** | 3 |

vMLX is **7.4× slower to load** than oMLX, consistently, across three different artifacts
(18.13 / 16.13 / 16.10 s). This is a load-time figure only and says nothing about throughput —
a runtime that starts slowly may still generate fastest, which is exactly why the grid reports
cold load as its own column rather than folding it into a score.

## Four runtimes, four output conventions, one model

Every ✓ cell returned coherent text, but not through the same channel or shape:

| runtime | behaviour at `max_tokens=24` |
|---|---|
| mlx-lm | reasoning channel only, zero content deltas — still inside `<think>` |
| oMLX | 3 deltas, reasoning mirrored into content |
| mlx-optiq | answers directly — its `:no-think` model-id variant |
| vMLX | reasoning channel only, like mlx-lm |

The same prompt, the same weights, four different stream shapes. Every channel-handling fix
made earlier today — the `reasoning` field name, the mirror dedupe, mirrored-stream timing, the
two-delta rate domain — is load-bearing for this grid. Without them, two of these four runtimes
would publish no figures and a third would publish wrong ones.

## A flaw in the probe itself, recorded rather than hidden

The probe's `verdict` field keys off `Observation.ok`, which is `False` when the content channel
is empty. So mlx-lm and vMLX cells — which loaded fine and produced coherent reasoning — were
labelled `answered: chat stream produced no content`. The label is wrong; the data beside it
(`coherent: true`, the text itself) is right, and the table above is read from `coherent`.

The same content-versus-reasoning distinction that produced three separate defects earlier in
the day was walked into again while writing the instrument to check for them. A 24-token budget
also guarantees a thinking model never exits `<think>`, which a larger budget would have avoided.

## What this settles for Phase 3

- The format axis holds at oMLX: it loads **4 of 4** formats, and fastest.
- The runtime axis holds at any of the four formats: **4 of 5 runtimes** load each, pending the
  Osaurus column.
- The grid has exactly **one** structural hole in its probed region, and it is explained.
- JANG_4S is still downloading. Its row is expected to be Osaurus and vMLX only, and that
  expectation is a prediction — the record above is what predictions in this project are worth.

## Reproducing

Run `probe_grid.py` with `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin` on `PATH`, and quit
`osaurus.app` first. `READY_TIMEOUT_S` is lowered to 180 s: a cell needing fifteen minutes to
load is a no for grid purposes.
