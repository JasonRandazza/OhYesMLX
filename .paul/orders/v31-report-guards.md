# Order: report.py deferred fixes (v3.1)
Files you may touch: ohyesmlx/report.py, tests/test_report.py, docs/interfaces.md. Touch nothing else.
1. Grid/sweep entries: a row with status N/A renders `—` today (`_entry`, ~line 1800), the same as
   "a combination no run measured". Render it `N/A`, and add a legend row for it wherever the `—`
   legend row is printed (~line 1424 and any grid equivalent). `—` stays for no row at all.
2. Single-run leaderboard `render_markdown` (~line 423), axis="runtime": it orders rows by any rank.
   Apply the same two refusals the grid applies, via the existing `_uncomparable_across_runtimes`
   (A7 `CROSS_RUNTIME_UNCOMPARABLE`, Decision 122 `CHANNEL_DEPENDENT_RANKS` with mixed channels):
   the table still prints every row's value but without an ordering claim (no position), plus the
   same note text the grid prints (reuse, do not restate). Format axis is unchanged.
3. A TTFT-ranked table over rows with concurrency > 1 (sweep and leaderboard) carries no caveat that
   concurrent TTFT includes queueing. Add one sentence, defined once as a constant, printed only then.
Acceptance: every existing render not hitting these cases stays byte-identical (prove with the existing
snapshot tests); one new test per item that fails if the change is reverted (red-check each).
`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` green. No git, no runtimes.
Report DONE with the diff summary and red-check evidence, or BLOCKED with the reason.
