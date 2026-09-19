GOAL: Update scripts/analyze_accuracy_moe.py to robustly handle incomplete/missing task scores (NoneType) without raising TypeError.

FILES TO TOUCH:
- scripts/analyze_accuracy_moe.py

SPECIFICATION:
1. In `scripts/analyze_accuracy_moe.py`:
   - Line 237-245: When calculating replicate stats, `score_base` and `score_repl` can be None if a cell or task failed before recording a score. Guard `score_repl - score_base`: if either is None, record `delta_pp = None`.
   - Line 311-314: In console output for replicates, format `primary` and `repl` safely (e.g. `f"{score:.4f}" if score is not None else "N/A"`).
   - Line 316-331: In console output for primary scores, handle None scores safely: `score * 100 if score is not None else 0.0` or format as `"N/A"`.
   - In paired difference calculations: if either task sample set is empty or has 0 common items, return safe default dict with `n: 0` without dividing by zero.
   - In `self_test()`: Add a test case with None scores to ensure `run_full_analysis` never crashes when a manifest task has `score: null`.
2. Run verification:
   - `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/analyze_accuracy_moe.py --self-test`
   - `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/analyze_accuracy_moe.py`
   - `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
3. Touch nothing else.
