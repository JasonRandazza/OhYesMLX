## Order: multi-turn as fixed workloads (Phase 4, study 03-04)

Jason's decision 2026-09-24: re-run the multi-turn study through the harness as N fixed
workloads in `cli.py`, with **no new header pin**. Workloads are already recorded in the header
with their messages and max_tokens (`measure.py` header docstring), so a run's workload set is
provenance already.

Files you may touch: `ohyesmlx/cli.py`, `tests/test_cli.py`, `docs/interfaces.md`, `README.md`
(only the lines that list workloads/flags). Touch nothing else. If the run path in
`measure.py`/`report.py` cannot carry ten workloads unchanged, stop and report BLOCKED with why.

Acceptance criteria:
1. A literal 10-turn conversation in `cli.py`: the ten user questions of
   `scripts/probe_multiturn_sweep.py` (`DIALOGUE_TURNS`), and **fixed literal assistant replies**
   between them (write short, neutral, factual replies, about 60–120 words each). The probe fed
   each runtime's own replies back in, so every runtime saw a different history. That varies two
   things at once, and fixed replies are what make turn N the same prompt on every runtime. Put
   that rationale once, at the constant.
2. `multiturn_workloads(measure)` returns ten `Workload`s, `turn-01`…`turn-10`. Turn N's messages
   are the first N user questions and the N−1 fixed replies, ending on user question N. One
   `max_tokens` for all ten (use `chat`'s 128).
3. Selection mirrors how `--prompt-tokens` swaps the workload set: `run --workloads
   {pinned,multiturn}`, default `pinned`, which is today's three shapes, byte-identical. It is
   mutually exclusive with `--prompt-tokens` (argparse error). It is not a header pin: the header's
   existing workload list records it.
4. Tests: default path unchanged (same three workloads, same messages); multiturn builds ten with
   strictly growing message lists, each ending on a user turn and sharing a prefix with the
   previous; the mutual-exclusion error; the CLI help lists the flag (help tests pin `NO_COLOR`,
   see commit 9210931). Red-check.
5. Suite green; baseline 611.
