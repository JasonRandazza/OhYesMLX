---
phase: 04-server
plan: 01b
completed: 2026-11-02
duration: ~15min
description: "hardware.scan reads gpu_cores from ioreg's gpu-core-count (30 on this M2 Max)"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 01b: gpu_cores from ioreg Summary

**`Hardware.gpu_cores` now comes from `ioreg -rc AGXAccelerator -d1`; `None` only when macOS does not report it.**

## AC Result

| Criterion | Status |
|-----------|--------|
| AC-1: GPU cores from ioreg, honest absence | Pass (995 tests; live scan prints 30; worker red-check failed both 30 tests with the parser forced to None) |

## Files Changed

| File | Change |
|------|--------|
| ohyesmlx/hardware.py | Modified: `_gpu_cores` regex parse; `scan` runs ioreg, catching only OSError/CalledProcessError; docstring updated |
| tests/test_hardware.py | Modified: three gpu_cores tests; ioreg argv added to the full fake answer sets |

---
*Completed: 2026-11-02*
