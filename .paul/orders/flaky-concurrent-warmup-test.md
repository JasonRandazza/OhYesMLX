GOAL: tests/test_measure.py::test_a_concurrent_warmup_settles_on_the_batchs_aggregate_throughput
fails on GitHub CI (run 35128400486: "the window closed", warmup_plateau False) and passes
locally. Its responder sleeps 20 ms per request, so batch spans come from the real clock and
shared CI runners jitter past the 3% plateau tolerance. Make it deterministic.

FILES YOU MAY EDIT: tests/test_measure.py only. No production code.

REQUIRED: the test must no longer depend on real wall-clock timing. Prefer the smallest change
that uses what the harness already offers (look for an injectable/fake clock or monkeypatchable
time source used by measure.py for batch spans); otherwise monkeypatch that clock in this test so
every batch span is identical. Keep the test's meaning: per-request decode rates climb (never
settle) while aggregate is flat, and the window closes before the cap. Check whether other tests
using CLIMBING_SLEEP_S or real sleeps for spans have the same exposure; fix those the same way.

ACCEPTANCE: pytest -q green from 451 (use
/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python). Prove determinism: run the test
under CPU contention (e.g. `for i in 1..8: yes > /dev/null &` then pytest -k that test
--count or a 20x loop, then kill the yes loops) before and after; report both pass counts.
No git.
