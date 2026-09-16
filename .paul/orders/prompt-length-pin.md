GOAL: Phase 6's prompt-length sweep (128/1k/4k/16k/32k tokens) cannot be run: every prompt is a
literal. Add prompt length as a run pin, and close join guard 1's missing sweep pins.

FILES YOU MAY EDIT: ohyesmlx/cli.py, ohyesmlx/measure.py, ohyesmlx/report.py (PIN_FIELDS and
_check_pins ONLY), tests/test_measure.py, tests/test_report.py, and a NEW tests/test_cli.py if
you want one. Touch nothing else. `ohyesmlx/longtext.md` is a frozen fixture: read it, never
edit, regenerate or reformat it.

READ FIRST: `docs/interfaces.md`, section "Phase 6 plan 06-01c — the prompt-length pin". It
pins the signature, the text construction, the single workload, the header shape, and the guard
change. Do not deviate; report BLOCKED if one is wrong.

REQUIRED:

1. `cli.sized_prompt(counter, target) -> (text, achieved)`. Source = the MS-7 excerpt body of
   `PREFILL_PROMPT` (between its BEGIN/END marker lines) + "\n\n" + `longtext.md`. Text =
   head + cut + tail; cut = longest source prefix ending at a whitespace boundary whose whole
   prompt counts <= target, found by bisection with `counter.count` only. `achieved ==
   counter.count(text)`. ValueError when the target cannot fit head+tail, or needs more source
   than exists. Never repeat text.

2. `--prompt-tokens N` on `run`. With it: one workload, `prefill`, max_tokens 64, message =
   `sized_prompt`. Counter = `token_counter.TokenCounter(cell.artifact_dir)` per distinct
   artifact; if any two disagree on `achieved`, exit 2 before `run_cells` is called. Without the
   flag, the three existing workloads, byte-identical to today.

3. `run_cells(..., prompt_tokens: dict | None = None)` writes header
   `"prompt_tokens": {"target": N, "achieved": M}` or `None`, verbatim.

4. report.py: `PIN_FIELDS` gains `concurrency` and `prompt_tokens`. An absent `concurrency` is
   compared as `1`; an absent `prompt_tokens` as `None`. Nothing else in report.py changes.

WHAT MUST NOT CHANGE: `PROMPT`, `PREFILL_PROMPT`, the three workloads' shapes, every metric,
the coherence gate, warmup, and every run header field that exists today.

ACCEPTANCE: pytest -q green from a 413 baseline. Tests must cover: `achieved <= target` and
`achieved == count(text)` across several targets with a word-count counter; the cut ends at a
whitespace boundary; the prompt at a larger target extends (starts with the same cut as) a
smaller one; a too-large and a too-small target raise; no paragraph of the source appears twice
in any prompt; `--prompt-tokens` yields exactly one `prefill` workload with cap 64; no flag
yields the three workloads unchanged; disagreeing counters exit 2 without calling run_cells;
the header carries the pin and `None` without it; guard 1 refuses joining an N=8 header with an
N=1 header, refuses differing `prompt_tokens`, and ACCEPTS a header lacking `concurrency`
joined with one pinning `1`.

Red-check the guard test (revert the PIN_FIELDS change, watch it fail) and report that you did.

Do not start a server or load a model. The live probe and the sweep are the coordinator's.

ANSWER IN YOUR REPORT: with a real BPE tokenizer, how far below target can `achieved` land, and
does anything in your bisection assume `count` is monotonic in prefix length? If it does, say
what happens when it is not.
