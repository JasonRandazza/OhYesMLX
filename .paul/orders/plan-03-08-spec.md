# Work Order: Plan 03-08 — Distributable Package & Clean CLI

## Objective
Package OhYesMLX for public distribution as a self-contained, standard Python package (`pip`/`uv` installable) with zero hardcoded host paths, standard PEP 621 packaging metadata, hardened CLI ergonomics and error handling, and comprehensive regression test coverage.

## Background & Standing Boundaries
- **Stdlib First:** The base OhYesMLX harness operates with zero third-party dependencies. Adding a dependency requires naming, in the commit message, what it replaces.
- **Single Cell Selector:** `--cells <cell>,<cell>` remains the only cell selector.
- **Zero Governance:** No plan hashing, no sealed evidence bundles, no doctor commands.
- **Host Path Isolation:** No user-specific host paths (`/Users/...`) in code or package configuration.

## Requirements & Acceptance Criteria

### 1. PEP 621 Packaging Metadata (`pyproject.toml`)
- Set package version to `0.3.0` (matching Milestone v3).
- Complete standard metadata:
  - `description`: "Honest benchmarks for local LLM serving on Apple Silicon. One variable at a time."
  - `readme = "README.md"`
  - `license = { text = "MIT" }`
  - `requires-python = ">=3.11"`
  - `authors = [{ name = "Jason Randazza" }]`
  - `keywords = ["apple-silicon", "mlx", "llm", "benchmark", "serving", "quantization"]`
  - `classifiers`: MacOS X, Python 3.11+, Topic :: System :: Benchmark, Topic :: Scientific/Engineering :: Artificial Intelligence.
  - `urls`: Project repository and issues.
- Build system: Hatchling configuration ensuring `ohyesmlx/longtext.md` is included in wheel and sdist builds.
- Preserved entry point: `ohyesmlx = "ohyesmlx.cli:main"`.

### 2. Module & CLI Versioning (`ohyesmlx/__init__.py`, `ohyesmlx/cli.py`)
- Expose `__version__ = "0.3.0"` in `ohyesmlx/__init__.py`.
- Add `--version` / `-V` flag to the top-level `ohyesmlx` CLI parser, printing `ohyesmlx 0.3.0` and exiting with code 0.

### 3. CLI Hardening & Error Handling (`ohyesmlx/cli.py`)
- Standardized exit codes:
  - Exit `0`: Successful execution, `--help`, `--version`.
  - Exit `2`: Argument parsing errors, syntax errors, invalid `--cells` formats, axis violations.
  - Exit `1`: Runtime execution errors or refused joins.
- Graceful error reporting to `sys.stderr` without raw Python tracebacks for user argument/input errors.
- Ensure all subcommands (`run`, `grid`, `sweep`) render clear `--help` text.

### 4. Test Suite Expansion & Packaging Verification (`tests/test_cli.py`)
- Expand `tests/test_cli.py` to cover:
  - `ohyesmlx --version` and `-V`.
  - `ohyesmlx --help` and `--help` on subcommands (`run`, `grid`, `sweep`).
  - Invalid arguments and unrecognized commands exiting with code 2.
  - Package metadata and `__version__` integrity check.
  - Verified loading of package data (`longtext.md`) via package-relative path.
- Verify `uv build` builds clean sdist and wheel artifacts without warnings.
- Maintain 100% pass rate across the test suite (expanding from 496 to 500+ green tests).

## Deliverables
- `pyproject.toml`
- `ohyesmlx/__init__.py`
- `ohyesmlx/cli.py`
- `tests/test_cli.py`
- `.paul/orders/plan-03-08-spec.md`
