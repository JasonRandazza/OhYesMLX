# Order: Plan 02-02 engines.install_plan (v5.0 Phase 2, seam S2)
Read first: .paul/phases/v5-onboarding/02-02-PLAN.md (this order is that plan; ACs and boundaries bind), the table and sections 1.1, 2.1, 3.1, 4.1, 5.1, 6.3, 6.6 of
docs/research/2026-10-29-engine-install-paths.md, docs/interfaces.md "v5.0 -- Onboarding shapes" (`Plan`), and ohyesmlx/engines.py (02-01, done; match its style).
Files you may touch: ohyesmlx/engines.py, tests/test_engines.py. Touch nothing else (no git, no docs, no pyproject, no network, no subprocess, no installs).
Interface: `install_plan(name: str, macos_major: int) -> Plan`. `Plan` and `Step` frozen dataclasses with the pinned fields:
 Plan{engine, kind ("guided_download"|"command"), source_url, size_bytes_estimate (int|None), needs_admin (bool), steps[Step]}; Step{id, label, command (list[str]|None)}.
Unknown name -> ValueError. Data only: no side effects, no network, never resolve "latest" over the wire (release URLs point at /releases/latest).
Also set EngineStatus.install = install_plan(name, macos_major) inside detect_all? NO -- leave EngineStatus.install None; the server composes them in Phase 4.
Decision (Jason): pip engines pin the harness-tested version read from TESTED_VERSIONS (one definition): command plans create a venv at
~/Library/Application Support/OhYesMLX/engines/<name>-<tested version> (same path _app_engine_venvs in engines.py already expects) and run
`<venv>/bin/python -m pip install --no-input --disable-pip-version-check mlx-lm==<ver>` / `mlx-optiq==<ver>`. Interpreter placeholder in step 1: the literal "{python}" token (02-03 injects the real one). App engines: guided_download, steps = open the page, then verify via detection, command None.
Sizes (literals, bytes): Osaurus 85.9 MB; oMLX macOS15 837.8 MB / macOS26+ 875.2 MB; vMLX Sequoia 579.0 MB / Tahoe 604.5 MB; mlx-lm and OptiQ: size_bytes_estimate None (clean install size UNKNOWN in the research). Use MB = 1_000_000.
macOS selection: macos_major < 26 -> Sequoia asset names (oMLX-<ver>-macos15-sequoia.dmg, vMLX-<ver>-sequoia-arm64.dmg), else Tahoe (oMLX-<ver>-macos26-27.dmg, vMLX-<ver>-tahoe-arm64.dmg); put the asset hint in a step label; source_url stays the releases page.
TDD, vertical slices, red before green, watch each fail first, literal expected values: AC-1 app engines guided; AC-2 pip engines pinned commands (assert the exact argv lists);
AC-3 asset/size by macOS (15 vs 26); AC-4 unknown sizes None; unknown name ValueError; needs_admin False everywhere.
Acceptance: suite green (/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q). Report DONE or BLOCKED.
