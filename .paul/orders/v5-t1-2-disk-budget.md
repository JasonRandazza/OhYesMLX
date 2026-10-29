# Order: T1.2 + T1.3 disk and model budget in hardware.scan (v5.0, seam S1)
Why: onboarding needs free disk and how much memory a model's weights may use. Shapes pinned in docs/interfaces.md (`Hardware`); read it and ohyesmlx/hardware.py (T1.1, done).
Files you may touch: ohyesmlx/hardware.py, tests/test_hardware.py. Touch nothing else (no git, no docs, no pyproject).
Side-effect seams, injected like `run`: `scan(run=_run, disk_usage=shutil.disk_usage, volume_paths=_volume_paths)`.
`volume_paths() -> list[str]` returns "/" plus each directory directly under /Volumes (default impl lists /Volumes, skips non-dirs and the
startup-disk alias; tolerate a missing /Volumes). `disk_usage(path)` has shutil's `.free`. Failure on one volume skips that volume only.
Fields: `disk_free_bytes` = free bytes on "/"; `volumes` = [{"path": str, "free_bytes": int}] for every path from volume_paths.
`model_budget_bytes`, defined ONCE in hardware.py as a named function `model_budget(ram_bytes)`, integer arithmetic only:
 limit = ram*3//4 if ram >= 36 GiB else ram*2//3   (Apple's default GPU wired-memory ceiling)
 budget = max(0, limit - 2 GiB)                    (KV cache and runtime overhead headroom)
 Rationale comment goes here once; nothing else restates it.
TDD, vertical slices, red before green, watch each test FAIL first. Literal expected values only:
 1. fake disk_usage -> "/" free 123456789012 gives disk_free_bytes 123456789012.
 2. volume_paths ["/", "/Volumes/Ext"] with different free -> volumes list in that order.
 3. a volume whose disk_usage raises OSError is skipped, the rest remain; "/" failing gives disk_free_bytes 0.
 4. model_budget: 16 GiB (17179869184) -> 9305762474; 64 GiB (68719476736) -> 49392123904; 8 GiB (8589934592) -> 3579139413.
 5. scan() sets model_budget_bytes via model_budget for the M2 Max / 64 GiB fixture.
Update the T1.1 fixture asserts that expected disk 0 / volumes [] / budget 0 only as these slices require. Add the default
`_volume_paths` check as a test using a tmp directory if it is injectable cheaply; otherwise leave it for the real-Mac smoke.
Acceptance: suite green (/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q). No git. Report DONE or BLOCKED.
