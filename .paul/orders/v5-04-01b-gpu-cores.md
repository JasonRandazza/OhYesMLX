# Order: plan 04-01b, Hardware.gpu_cores from ioreg (one deliverable, no tangents)
Spec: `.paul/phases/v5-onboarding/04-01b-PLAN.md` — read it in full; AC-1 is the acceptance criterion and its one task is the work. Jason approved it 2026-11-02.
Files you may touch: ohyesmlx/hardware.py, tests/test_hardware.py. Touch nothing else. If another test file builds a full `hardware.scan` fake and breaks, stop and report BLOCKED naming it rather than editing it.
Must hold:
- `scan` runs `["ioreg", "-rc", "AGXAccelerator", "-d1"]` through its injected `run`; a regex finds `"gpu-core-count" = (\d+)`; first match wins.
- Only `OSError` and `subprocess.CalledProcessError` are caught around that call, never `KeyError`.
- The module docstring's `gpu_cores` sentence says where the number now comes from and when it is `None`.
Tests: the three cases in the plan's task, using a realistic multi-line `ioreg` block that contains `"gpu-core-count" = 30`; every existing full fake answer set gains the ioreg argv. Red-check: make the parser return None and watch the 30 test fail, then restore it.
Run `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q`; must be green (992 before). Do not commit.
Report: file:line of the parse, the test names, the red-check result, the final pytest line.
