GOAL: every cell runs three workload shapes instead of one. Today the harness measures a
34-token prompt producing 256 tokens and nothing else, so every figure it has ever published
describes one corner of the space.

FILES YOU MAY EDIT: ohyesmlx/measure.py, ohyesmlx/cli.py, tests/test_measure.py ONLY.

THE CONTRACT IS PINNED in docs/interfaces.md — read the "Workloads — the three shapes" section
and implement exactly it. Summarised:

    @dataclass(frozen=True)
    class Workload:
        id: str                  # "chat" | "prefill" | "decode"
        messages: list[dict]
        max_tokens: int

    run_cells(cells, workloads: list[Workload], *, warmup=3, measured=5, cooldown_s=30.0,
              results_dir) -> list[CellResult]

`max_tokens` MOVES to the Workload and is no longer a run_cells argument. Every cell runs every
workload. A result is per (cell, workload) — `CellResult` gains a `workload_id`, and run_cells
returns one per pair, still in first-visit order.

WHY IT MATTERS, so you get the grouping right: prefill-heavy and decode-heavy work can have
different winners. Figures must NEVER be averaged across workloads — a prefill-bound number
averaged with a decode-bound one describes no workload that was run.

THE THREE, defined in cli.py where the current PROMPT constant lives:
- `chat`    — short prompt, max_tokens 128. Reuse the existing PROMPT verbatim.
- `prefill` — a long prompt, max_tokens 64. Write one long enough to dominate the request; say
  in your report how many characters it is and why you chose that length.
- `decode`  — short prompt, max_tokens 512.
Pin them as literals. No config file, no CLI flag to add workloads — v1 has three and no more.

THE COSTLY PART YOU MUST GET RIGHT: a runtime is started and stopped per visit and exactly one
runtime may hold weights at a time. Do NOT reload the model once per workload per visit if the
existing visit structure can serve all three workloads from one load — read how run_cells plans
its visits and cooldowns before changing anything, and say in your report what you chose and
what it costs in model loads. Getting this wrong triples every run's wall time.

The results.jsonl header line records the run's pins (warmup, measured, cooldown_s, workload).
It must now record all three workloads. Each cell line must name which workload produced it.

ACCEPTANCE: pytest -q green from a 243 baseline. The existing tests pin call counts and
results.jsonl line counts per visit — expect to update them, and state in your report exactly
which assertions you changed and why each change is correct rather than convenient. Tests must
cover: every cell runs every workload; a per-(cell, workload) result carries its workload_id;
max_tokens comes from the workload; the persisted header names all three.

Do not touch report.py, transport.py, runtimes.py, coherence.py, token_counter.py. Do not start
a server or load a model.
