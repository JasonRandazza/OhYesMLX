# Order: Plan 02-03 engines.install -- consent-gated installer (v5.0 Phase 2, seam S3)
Read first: .paul/phases/v5-onboarding/02-03-PLAN.md (AC-1..AC-12 and boundaries BIND; audit: 02-03-AUDIT.md), ohyesmlx/engines.py (detect_all, install_plan, Plan, Step; match its injected-seam style),
ohyesmlx/hardware.py (scan for free disk), docs/interfaces.md "v5.0 -- Onboarding shapes" (job event shape: {"seq","type":"progress|log|result|error|done","message","fraction","payload"}).
Files you may touch: ohyesmlx/engines.py, tests/test_engines.py. Touch nothing else (no git, no docs, no pyproject, no real subprocess, no network, no installs, no deleting anything outside a pytest tmp_path).
Skip the plan's human-verify checkpoint: the coordinator already ran the pip smoke by hand.
Interface: `install(engine: str, confirmed: bool, *, macos_major, run, open_url, emit, detect=detect_all, hardware=..., sleep=time.sleep, log_path, lock, python, engines_dir, timeout_s=900, poll_s=..., poll_timeout_s=...) -> bool`.
Everything with a side effect is injected (tests use fakes; the defaults wrap the real thing). The Plan is DERIVED inside from `install_plan(engine, macos_major)` (AC-6): a non-engine name raises ValueError before anything else.
Order of checks, each emitting an `error` event with a code and logging it: consent_required (confirmed False) -> unknown engine raises -> already_installed (detect says installed) -> busy (lock held for this engine) -> low_disk (free < 2x size_bytes_estimate, 2 GiB floor if None).
Then run steps: substitute the literal "{python}" token with the injected `python`; `run(argv, timeout, env)` returns (exit_code, output_tail<=4 KB); env is hermetic: copy of os.environ minus PYTHONPATH and every PIP_* key (AC-12). Emit progress with fraction after each step, `done` last.
Failure: stop, emit `error` with step id + output tail, remove ONLY paths this call created (track the venv root you created; it must resolve inside `engines_dir`, never follow a symlink out; refuse otherwise), log it.
Guided download: `open_url(source_url)` only if https and host in the allowlist {github.com, pypi.org}; then poll `detect` until installed or poll_timeout_s; timeout ends in a `result` event with installed False, not an error (AC-8).
Install log (AC-10): append one JSON line per event to `log_path`: engine, UTC time, consent flag, step id, exit code, event type. Local only.
TDD, vertical slices, one AC at a time, red before green, WATCH EACH FAIL FIRST, literal expected values, fakes only. After the happy path, red-check each guard by removing it and confirming its test fails (consent, name check, already_installed, timeout, allowlist, lock, rollback scope), then restore it.
No sudo anywhere; argv lists only; no shell strings.
Acceptance: all 12 ACs have tests, suite green (/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q). Report DONE or BLOCKED and list which guards you red-checked.
