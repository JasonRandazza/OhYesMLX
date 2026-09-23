GOAL: Remove duplication in cli.py and runtimes.py with zero behaviour change.
FILES: ohyesmlx/cli.py, ohyesmlx/runtimes.py, tests/test_cli.py, tests/test_runtimes.py. Touch nothing else.
ITEMS:
(a) cli.py: _grid and _sweep are one function with a different renderer and error prefix. Merge them into one _join(args, name, render) that both subcommands call; stderr messages and exit codes unchanged ("ohyesmlx grid: ..." / "ohyesmlx sweep: ..."). Delete the unused PROMPT_TOKEN_TARGETS constant and its comment.
(b) runtimes.py: delete Vmlx.stop_command and Vmlx.api_key (they return the base-class defaults); move their two explanatory comments into the Vmlx class docstring in one sentence each. Make vmlx_served_name reuse hub_repo_name's `models--<org>--<name>` parsing via a small shared helper instead of re-parsing, keeping vmlx's original-case `org/repo` result and hub_repo_name's lowercased repo result exactly.
CONSTRAINTS: Every start command, served name and CLI message stays byte-identical. Do not touch any other runtime class or any docstring you are not removing code for.
ACCEPTANCE: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` green (baseline 504; report new count). `git diff --stat` touches only the four files above. Report net line change per file.
