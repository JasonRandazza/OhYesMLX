# Order: plan 04-01, Tasks 1 and 2 (the guarded localhost server and `ohyesmlx app`); one deliverable, no tangents
Spec: `.paul/phases/v5-onboarding/04-01-PLAN.md` — read it in full, including the audit-added lines. ACs AC-1..AC-8 are the acceptance criteria; Tasks 1 and 2 are the work. The audit's reasons are in `04-01-AUDIT.md`. Jason approved this plan on 2026-11-02; `server.py` and the `app` subcommand are approved surfaces (AGENTS.md).
Files you may touch: ohyesmlx/server.py (new), ohyesmlx/cli.py, tests/test_server.py (new), tests/test_cli.py, docs/interfaces.md (v5.0 section only). Touch nothing else. In particular do not edit hardware.py, engines.py, catalog.py, recommend.py or fetch.py: if a shape does not match what the server needs, stop and report BLOCKED with the mismatch.
Constraints: stdlib only (`http.server`, `secrets`, `hmac`, `json`, `dataclasses`, `threading`, `signal`). Python 3.11+. Match the style of the surrounding modules (docstrings that give the reason once, injected seams with production defaults, no speculative options).
Must hold:
- The guard runs first in every do_* method, in AC-2's order, and a refused request never calls scan/detect/load (test it with a recording fake).
- Token compare is `hmac.compare_digest` on UTF-8 bytes; no response ever contains the token or echoes a header value.
- No `Access-Control-*` header anywhere. `Cache-Control: no-store` and `application/json; charset=utf-8` on every response.
- Refusals write one JSON line to stderr (AC-8); served requests write nothing; `log_message` is silenced.
- Bind failure: nothing on stdout, one stderr error line, exit 2 (AC-1).
- stdin EOF or SIGINT/SIGTERM shuts down cleanly, exit 0, port released (AC-7).
Tests: everything listed in Task 1 and Task 2 "Tests"/"Audit-added tests", against a real server on port 0 via `http.client`, plus the subprocess test for `app`. Each guard must be red-checked: remove it, watch its test fail, restore it; say in your report which tests failed for each removal.
Run `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q`; it must be green (959 before). Do not commit. Do not run the manual curl or browser checks (the coordinator does).
Report: per AC, the file:line and test names that satisfy it; the red-check results; the final pytest line; anything you were unsure of.
