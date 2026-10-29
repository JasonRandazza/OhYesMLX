# Order: Plan 025-01 tested-versions manifest + one PATH-prefix definition (v5.0 Phase 2.5)
Read first: .paul/phases/v5-onboarding/025-01-PLAN.md (this order IS that plan; ACs and boundaries bind), ohyesmlx/engines.py (TESTED_VERSIONS and everything that uses it), ohyesmlx/runtimes.py (_spawn, _run, RUNTIMES),
tests/test_runtimes.py (the TODAY command table must not change), docs/interfaces.md "v5.0 -- Onboarding shapes" (EngineStatus). Use `graphify query "<question>"` before grepping blind.
Files you may touch: NEW ohyesmlx/engines-tested.json, ohyesmlx/engines.py, ohyesmlx/runtimes.py, tests/test_engines.py, tests/test_runtimes.py, docs/interfaces.md (only EngineStatus: add "verified": str|null), pyproject.toml (only to include the config file in wheel and sdist).
Touch nothing else (no cli.py, no measure.py, no scripts/, no git, no servers, no installs, no network).
Manifest literals: osaurus 0.25.28, omlx 0.7.2, optiq 0.5.13, mlxlm 0.31.3, vmlx 1.6.59; verified "2026-10-29" for all; canary null for all; lab_path null except mlxlm = "~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin" (expand ~ when used).
Order of work (TDD vertical slices, red before green, watch each fail): AC-2 validation errors via a loader that takes a path; AC-1 TESTED_VERSIONS from the shipped file, no version literal left in engines.py; AC-5 `verified` on EngineStatus;
AC-3 `_engine_env()` in runtimes.py (single definition, used by _spawn and _run; nonexistent lab_path refused with the engine named); AC-4 TODAY table unchanged.
Careful: importing the manifest from runtimes.py must not create an import cycle with engines.py (engines imports runtimes); put the loader where both can use it without a cycle and say where you put it.
Run the suite: /Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q. Report DONE or BLOCKED, and list what you did not verify.
