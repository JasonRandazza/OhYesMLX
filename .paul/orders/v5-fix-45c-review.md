# Order: 045-03 code-review fixes to the smoke scripts; one deliverable, no tangents
Reviews: `.paul/orders/v5-review-45c-standards.log`, `v5-review-45c-spec.log` (read their final reports). Accepted items only:
Files you may touch: scripts/smoke_clean_account.sh, scripts/smoke_clean_account.py, tests/test_smoke_clean_account.py. Touch nothing else.
1. Sweep (.sh `sweep`/`run`): after the existing pass, wait 10 s and run the port + client + app sweep again (an engine that was still loading when the app died binds late). Count every pid signalled across both passes; `run` returns 1 when that count is > 0 (print `sweep: N process(es) left behind`), else the client's status. Keep "never name a jrazz-owned process" (all listings stay `as_test_user`). Also sweep, as oymlxtest, any process whose command line contains `$TEST_HOME/Library/Application Support/OhYesMLX/engines/` or one of the in-bundle engine tools (`/Applications/oMLX.app/Contents/MacOS/omlx-cli`, `/Applications/vMLX.app/Contents/Resources/bundled-python/python/bin/vmlx`).
2. .py: bound the launch-line read (deadline 60 s, e.g. `select` on the pipe); on timeout take the existing launch-error path (`_shut_down`), recording `AC-2.launch_line` FAIL "no launch line within 60 s".
3. .py `hub_repo_dir`: use `ohyesmlx.fetch`'s one definition of the repo directory (`fetch.py:198-201`; the client already imports ohyesmlx). The .sh preflight keeps its own (it runs before the venv exists) with a one-line comment saying so.
4. Ports: the .py takes `--ports` (space-separated) from the .sh's `PORTS`; delete the .py's own tuple.
5. Rationale: `--no-deps`/pygame reasoning lives at `ohyesmlx/engines.py` (`_command_plan`); in smoke_clean_account.py and both test files replace restatements with a pointer.
6. Delete the dead `else list(keys)` branch (~.py:495).
7. tests/test_smoke_clean_account.py ~155-159: the optiq iteration must run optiq's real plan, not mlxlm's.
8. .sh setup: copy the client with `git -C "$REPO" show HEAD:scripts/smoke_clean_account.py`, so the client and the wheel come from the same revision.
Tests for 2, 3, 4 (pure parts). `sh -n`. Do NOT run setup/run/teardown, sudo, or ohyesmlx app. Run `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` (1324 before); green. Red-check 2. Do not commit.
Report: file:line per item, pytest line. Under 200 words.
