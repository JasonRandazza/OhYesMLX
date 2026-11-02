---
phase: 04-server
plan: 01b
plan_type: execute
autonomous: true
description: "hardware.scan reports gpu_cores from ioreg's gpu-core-count instead of a hardcoded None"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
`Hardware.gpu_cores` is the integer macOS reports as `gpu-core-count` on the AGX accelerator (30 on this M2 Max),
and `None` only when macOS does not report it.
</objective>

<context>
@ohyesmlx/hardware.py (`scan`, `_run`, the module docstring's `gpu_cores` sentence)
@tests/test_hardware.py (`fake_run` answers by argv tuple; captured-text fixtures)
Found at the 04-01 checkpoint (2026-11-02): `/hardware` returned `gpu_cores: null` on an M2 Max.
Probe on this Mac: `ioreg -rc AGXAccelerator -d1` prints `"gpu-core-count" = 30` (IOClass `AGXAcceleratorG14X`).
</context>

<acceptance_criteria>
## AC-1: GPU cores come from ioreg, and absence stays honest
Given `scan` runs `ioreg -rc AGXAccelerator -d1` through its injected `run`
When the output holds a line `"gpu-core-count" = N`
Then `gpu_cores` is the integer N
And when the line is absent, the output is empty, or the command fails (`OSError`, `CalledProcessError`), `gpu_cores`
 is `None` and `scan` still returns every other field
</acceptance_criteria>

<tasks>
<task type="auto">
  <name>Read gpu-core-count in hardware.scan</name>
  <files>ohyesmlx/hardware.py, tests/test_hardware.py</files>
  <action>
    - One small parse function over the `ioreg` text (a regex for `"gpu-core-count" = (\d+)`), called from `scan` through `run`; first match wins.
    - Catch only `OSError` and `subprocess.CalledProcessError` around that one call. Never catch `KeyError`: the tests' `fake_run` raises it for an argv it was not given, and swallowing it would hide a missing fixture.
    - Replace the docstring sentence that says no command reports `gpu_cores` with where it now comes from and when it is `None`.
    - Tests: the captured line from this Mac (`"gpu-core-count" = 30` inside a realistic `ioreg` block) gives 30; output without the key gives `None`; a `run` that raises `CalledProcessError` for that argv gives `None` with the other fields intact. Add the `ioreg` argv to every existing fixture that builds a full `fake_run` answer set.
  </action>
  <verify>`/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` green; live: `python -c "from ohyesmlx import hardware; print(hardware.scan().gpu_cores)"` prints 30 on this Mac</verify>
  <done>AC-1 satisfied</done>
</task>
</tasks>

<output>
After completion, create compressed `.paul/phases/v5-onboarding/04-01b-SUMMARY.md`
</output>
