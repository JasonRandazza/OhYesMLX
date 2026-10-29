# Order: runtime concurrency caps follow the run's concurrency (approved by Jason 2026-09-27)
Why: the start commands hard-code a cap of one in-flight request -- oMLX `--max-concurrent-requests 1`
(runtimes.py ~2220), OptiQ `--max-concurrent 1` (~2411), vMLX `--max-num-seqs 1` (~2697) -- so the
2026-09-27 concurrency sweep (results/sweep-conc-seedless) measured our cap, not their batching, at N>1.
Files you may touch: ohyesmlx/runtimes.py, ohyesmlx/measure.py, docs/interfaces.md, docs/runtimes/{omlx,optiq,vmlx}.md,
tests/test_runtimes.py, tests/test_measure.py. Touch nothing else (not AGENTS.md, not .paul/, not scripts/).
1. One definition: `start_command`, `build_command` and `start` take `concurrency: int = 1`; each of the three
   runtimes puts `str(concurrency)` where the literal "1" cap sits now. mlx-lm and Osaurus ignore it (mlx-lm
   has no cap passed; Osaurus takes no flags). The rationale is written once, near the first cap. `measure._visit`
   passes the run's `concurrency` to `runtime.start`.
2. At concurrency 1 every runtime's command is byte-identical to today's (the TODAY table in
   tests/test_runtimes.py must not change). Add a test that N=8 puts "8" in each of the three caps, and fails if reverted.
3. Read the shipped source (paths in docs/runtimes/*.md) and report with file:line: for oMLX, is
   `--max-concurrent-requests` the only thing keeping it from batching (any other scheduler/batch setting whose
   default is 1)? For OptiQ, confirm `--max-concurrent N` sets decode-concurrency N and prompt-concurrency
   max(1, N//4) (cli.py:2937-2949). For vMLX, anything besides `--max-num-seqs` limiting concurrent decode.
   Report only; change no code for item 3 unless it's the same one-literal fix, and say which.
4. docs: record in each runtime doc's flag table that the cap now follows the run's concurrency; docs/interfaces.md
   likewise if it lists start commands.
Acceptance: red-check item 2's new test; suite green (/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q).
No git, no server starts. Report DONE or BLOCKED.
