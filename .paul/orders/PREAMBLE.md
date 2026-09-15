# Standing context for every OhYesMLX work order

This block is byte-identical across every dispatch. It is the cached prefix: DeepSeek
V4.1 Flash bills a cache read at $0.003/M against $0.15/M for fresh input, so everything
invariant belongs here and only the task-specific part is ever re-read at full price.
Do not reorder, reword, or "improve" it — an edit costs a full re-read on every order
that follows.

## The project

OhYesMLX measures local LLM serving on Apple Silicon and answers one question: is your
serving runtime or your quantization costing you speed and memory? Two single-variable
studies. Every run declares which axis it varies; nothing varies both.

Eight modules in `ohyesmlx/`: `transport.py` (SSE measurement client), `runtimes.py`
(uniform lifecycle over four heterogeneous servers), `measure.py` (the measurement loop),
`coherence.py` (the gate), `report.py` (join and leaderboard), `sample.py` (macOS unified
memory sampling), `token_counter.py`, `cli.py`. Tests mirror them in `tests/`.

## The rules that outrank convenience

- **A fast cell that emits garbage is a failed cell.** Stock mlx-lm loaded a 256-expert
  oQ4 MoE in 4s, returned HTTP 200, hit full throughput, and produced token salad. Nothing
  raised. A speed-only harness records that as its healthiest row. Never publish a number
  from a cell that did not produce language.
- **Vary one thing at a time.** A number that changed two things is not a result.
- **Raw observations are never discarded or truncated.** The record keeps what was sent,
  including the sample that failed.
- **Never report an unreconciled number.** The predecessor project shipped a token path no
  caller used and reported `None` in 100% of runs on disk. Refusing to publish beats
  publishing something approximate.
- **A server's self-report is not a measurement.** oMLX reports 15,286 tok/s from a
  generation_duration of 0.0.
- **No new dependency without naming what it replaces.** No speculative abstraction, no
  interface with one implementation, no config for a value that never changes.
- `docs/interfaces.md` pins the shapes modules compose on. Read it before changing one.

## How to work

- Edit **only** the files the order names. If the job genuinely cannot be done inside them,
  stop and report BLOCKED with the specific contradiction — a BLOCKED report that finds a
  real problem in the order is a good outcome, not a failure.
- Do not start a server, load a model, or analyze tensors. Ever. Those are the
  coordinator's to run.
- Leave one runnable check behind for non-trivial logic. No frameworks, no fixtures.
- Run the suite and report the count. State the baseline you started from.
- Red-check anything you claim to fix: revert your change, watch the new test fail with
  the reported symptom, restore. Report that you did it.
- A green suite is not acceptance. Say plainly what you did not verify.
- If the order asks a question, answer it in your report rather than guessing silently.

## The task

Everything below this line is specific to this dispatch.

---
