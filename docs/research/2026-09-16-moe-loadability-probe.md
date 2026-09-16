# MoE loadability probe — LFM2.5-8B-A1B across five runtimes

Date: 2026-09-16, 07:00–07:20Z. One short request per cell, coherence checked, then stop.
Not a measurement: no figure here is published, and the probe exists so that the MoE grid's
holes are evidence rather than absence.

Subject: `LFM2.5-8B-A1B`, `model_type: lfm2_moe`, **32 experts, top-4**, 8 B total / 1 B
active. Five artifacts, 21.9 GB, all newly downloaded.

| format | repo |
|---|---|
| stock4bit | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` |
| oq4 | `stamsam/LFM2.5-8B-A1B-oQ4` |
| oq4e | `brainworkup/LFM2.5-8B-A1B-oQ4e` |
| optiq | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` |
| jang2l | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` |

## Result

| format | mlx-lm | oMLX | mlx-optiq | vMLX | Osaurus |
|---|---|---|---|---|---|
| stock4bit | LOADS | LOADS | LOADS | LOADS | LOADS |
| oq4 | LOADS | LOADS | LOADS | LOADS | LOADS |
| oq4e | LOADS | LOADS | LOADS | LOADS | LOADS |
| optiq | LOADS | LOADS | LOADS | LOADS | LOADS |
| jang2l | refuses | HTTP 409 | **hangs** | LOADS | LOADS |

Every cell marked LOADS answered coherently. Cold loads: Osaurus 1.3 s, mlx-lm 1.9–2.5 s,
oMLX 1.7–2.2 s, mlx-optiq 3.1–3.3 s, vMLX 18–19 s.

The MoE grid therefore has the same shape as the dense one: four portable formats across four
runtimes, plus a JANG format that only its two runtimes can load. That is what makes the two
grids readable the same way.

## Stock mlx-lm serves a 32-expert MoE coherently

This is the result the Phase 3 caveat predicted and the one Phase 4 needed corroborating.

Phase 1 found stock `mlx_lm.server` loading `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` — a **256**-expert
MoE — in four seconds, returning HTTP 200 at full throughput, and emitting mixed-script token
salad with nothing raised. Phase 4 established that the failure is runtime-specific rather
than format-specific: oMLX answers coherently from the same bytes.

Here stock mlx-lm 0.31.3 loads all four portable formats of a **32**-expert MoE and answers
coherently from every one. That is independent evidence for the working hypothesis that the
defect tracks expert count rather than MoE architecture in general — and it is exactly the
outcome the standing caveat said to expect, which is why it proves nothing on its own about
the 256-expert case. A clean result at 32 experts validates the machinery. It exonerates
nothing at 256.

## mlx-optiq hangs on JANG rather than refusing it

Three runtimes decline `jang2l` and each declines differently:

- **mlx-lm** refuses at load with a shape mismatch it names:
  `ValueError: Expected shape (128000, 128) but received shape (128000, 384) for parameter
  model.embed_tokens...`. A refusal that says what was wrong.
- **oMLX** starts, serves, and answers the request with `HTTP 409`. A refusal at request time
  rather than load time, which is the behaviour Phase 3 already recorded as "every runtime
  advertises models it cannot serve".
- **mlx-optiq** starts in 2.18 s, reports ready, accepts the request — and then **never
  answers**. The probe's 600-second timeout is what ended it, and the probe had set
  `READY_TIMEOUT_S` to 180 s precisely so a slow cell could not eat the clock; that budget
  governs readiness, not the request.

The third is the one worth keeping. A runtime that refuses is a cell the grid can record as
`N/A` with a reason in milliseconds. A runtime that hangs costs ten minutes per occurrence and
produces the same information. In a grid of twelve cells with three workloads and two visits,
a hanging cell of that kind would add hours and the harness would have no way to tell it from
a very slow model.

**Not fixed here**, and recorded rather than acted on: the transport's per-request timeout is
what bounded this, and it did its job. Whether a cell that has hung once should be abandoned
rather than retried on the next visit is a measurement-design question, not a worker's.
`jang2l__optiq` is simply not in the MoE cell selection, exactly as `jang4s__optiq` is not in
the dense one.

## A coordinator error worth recording

The first run of this probe reported mlx-lm failing to start on **all five** formats, which
looked like `lfm2_moe` being unsupported the way `gemma4_unified` was — the finding that
dropped gemma-4 as hero model back in Phase 1.

It was not. `mlx_lm.server` lives in its own venv at
`~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`, which `scripts/run_grid.sh` puts on `PATH` and
which the probe was launched without. Asking mlx-lm directly — `from mlx_lm import load` in
that venv — returned exit 0 on the same artifact, which is what turned a "finding" back into
an environment mistake in about a minute.

The lesson is the one this project keeps relearning from the other direction: a runtime that
will not start is a result, and a result has to be checked against the thing itself before it
is written down. `scripts/probe_grid_moe.py` should be run through `run_grid_moe.sh`'s
environment, not a bare venv.
