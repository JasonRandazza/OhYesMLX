# Standing context for every OhYesMLX work order

This block is byte-identical across every dispatch. It is the cached prefix: the worker model
bills a cache read at a fraction of fresh input, so everything
invariant belongs here and only the task-specific part is ever re-read at full price.
Do not reorder, reword, or "improve" it — an edit costs a full re-read on every order
that follows.

## The project

OhYesMLX measures local LLM serving on Apple Silicon and answers one question: is your
serving runtime or your quantization costing you speed and memory? Two single-variable
studies. Every run declares which axis it varies; nothing varies both.

Eighteen modules in `ohyesmlx/`. Measurement: `transport.py` (SSE client), `runtimes.py`
(lifecycle over the serving engines), `osaurus_settings.py`, `measure.py`, `coherence.py`,
`report.py`, `sample.py`, `token_counter.py`, `canary.py`. v5.0 onboarding app backend:
`hardware.py`, `engines.py` (detect + install), `catalog.py`, `recommend.py`, `fetch.py`
(downloads), `server.py` (localhost API), `quickbench.py`. Entry: `cli.py`. Tests mirror them
in `tests/`. Several files run past 900 lines and `docs/interfaces/` past 1,800.

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
- `docs/interfaces/` pins the shapes modules compose on. Read the file for your subject before changing one.

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

## Code graph — use it first

`graphify-out/graph.json` is a current map of this codebase (every function, its file and line).
Locate code with it instead of reading whole files:

- `graphify query "<question>"` — the functions and files involved, with `src=` and `loc=L<line>`.
- `graphify explain "<function or concept>"` — one symbol and its neighbours.
- `graphify path "<A>" "<B>"` — how two symbols connect.

Then read only those line ranges (offset/limit, or `sed -n 'A,Bp'`). Never read a file over
400 lines whole, and never read a `docs/interfaces/*.md` file whole: grep it for the shape you need.
Do not run `graphify update` yourself; the coordinator refreshes it after every change.

## Pace

Orientation is not the job. Write a first version of every file the order asks for within
your first ~15 turns, then iterate against the tests. A dispatch was once stopped after 30
minutes having read the codebase and written nothing. If the order is unclear enough that you
cannot start writing, report BLOCKED with the question instead of reading further.

## The task

Everything below this line is specific to this dispatch.

---
