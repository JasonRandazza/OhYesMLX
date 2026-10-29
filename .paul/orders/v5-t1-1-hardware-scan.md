# Order: T1.1 hardware.scan -- chip, RAM, macOS, supported (v5.0, seam S1)
Why: onboarding must tell a user what their Mac is. Shapes are pinned in docs/interfaces.md ("v5.0 -- Onboarding shapes", `Hardware`); plan in .paul/phases/v5-onboarding/PLAN.md. Read both first.
Files you may touch: NEW ohyesmlx/hardware.py, NEW tests/test_hardware.py. Touch nothing else (no pyproject, no cli.py, no docs, no git).
Interface: `Hardware` frozen dataclass with the pinned fields; `scan(run=_run) -> Hardware`. `run(argv: list[str]) -> str` is the only
side-effect seam (default wraps subprocess, stdout stripped); tests inject a fake that maps argv -> canned text. stdlib only.
Commands used: `sysctl -n machdep.cpu.brand_string` ("Apple M2 Max"), `sysctl -n hw.memsize`, `sysctl -n hw.ncpu`, `sw_vers -productVersion`.
Derive: family ("M2") and tier (base|pro|max|ultra) from the brand string. Unknown "Apple <X>" chip (e.g. a future M7) -> supported stays
true, family from the string, tier "base". Non-"Apple" brand (Intel) or ram < 8 GiB -> supported false with a plain unsupported_reason.
Disk fields (disk_free_bytes, volumes) and model_budget_bytes default to 0 / [] / 0 here: T1.2 and T1.3 fill them. gpu_cores None.
TDD, vertical slices, one at a time, red before green, run each new test and watch it FAIL before writing code:
 1. M2 Max / 64 GiB fixture -> chip "Apple M2 Max", family "M2", tier "max", ram_bytes 68719476736, cpu_cores, macos, supported True.
 2. M1 base 16 GiB -> tier "base". 3. M3 Pro and M4 Ultra-style strings -> pro / ultra. 4. Intel brand -> unsupported with reason.
 5. 4 GiB Apple chip -> unsupported (RAM). 6. Unknown future chip -> supported, tier base.
Expected values are literals, never recomputed from the code. No mocking of internals; only `run`.
Acceptance: all six tests pass and each was seen failing first; full suite green
(/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q). No git, no server starts. Report DONE or BLOCKED.
