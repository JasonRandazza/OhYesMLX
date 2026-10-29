# Order: Plan 02-01 engines.detect_all (v5.0 Phase 2, seam S2)
Read first: .paul/phases/v5-onboarding/02-01-PLAN.md (this order is that plan; its ACs and boundaries bind), docs/research/2026-10-29-engine-install-paths.md
(table + sections 1.4, 2.4, 3.4, 4.4, 5.4, 6.2), docs/interfaces.md "v5.0 -- Onboarding shapes", ohyesmlx/hardware.py (match its injected-seam style).
Files you may touch: NEW ohyesmlx/engines.py, NEW tests/test_engines.py, docs/interfaces.md (ONLY the EngineStatus lines: name enum -> osaurus|omlx|optiq|mlxlm|vmlx, add "tested": bool).
Touch nothing else (no runtimes.py, cli.py, pyproject, no git, no server, no subprocess, no network, never run vmlx --version).
Interface: `detect_all(env=DEFAULT_ENV) -> list[EngineStatus]`; env offers exists(path), read_text(path), realpath(path), home. EngineStatus frozen dataclass with the
pinned fields plus `tested`. `install` field of EngineStatus is filled by plan 02-02: here use None and leave a one-line comment pointing at 02-02.
Names/ports are asked from runtimes.RUNTIMES filtered by an ONBOARDING_ENGINES tuple of the five names (mtplx excluded, D2). TESTED_VERSIONS is ONE dict:
osaurus 0.25.28, omlx 0.7.2, optiq 0.5.13, mlxlm 0.31.3, vmlx 1.6.59. Version from files (plistlib for Info.plist; regex on _version.py / __init__.py), never by running a binary.
TDD vertical slices, red before green, watch each fail first, literal expected values (AC-1..AC-4 in the plan): 1 names from RUNTIMES (five, no mtplx);
2 only oMLX files present -> only oMLX installed, stale /opt/homebrew/bin/osaurus without the app does not count; 3 versions from fixtures, unreadable file -> version None with installed True;
4 tested flag true on match, false on difference. Candidate paths per engine: research table (app bundles in /Applications, ~/.local/bin, ~/.omlx/bin, and the app-managed
venv dir ~/Library/Application Support/OhYesMLX/engines/<name>*/ for mlxlm and optiq, plus the dev locations the research lists).
Acceptance: all tests seen failing first; suite green (/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q). Report DONE or BLOCKED.
