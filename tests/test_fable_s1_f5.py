"""Fable 5.2 S1-F5: `done` frees the job slot before the download's ledger write and lock release.

`fetch._download` emits `done` (fetch.py:1177) and returns; only then does `download`'s
`finally` run `_record` (the ledger read plus an fsynced atomic write, fetch.py:717) and
`_release_lock` (fetch.py:718). The server hands `job.append` in as `emit` (server.py:742),
and `_Job.append` frees the one job slot the moment a `done` event is stored
(server.py:199-202). So a client that acts on `done` -- the next download, or an evict --
can meet a lock that still names this live process and a ledger that does not yet list
what was just fetched.

The fetch half uses the fake transport and scratch cache from `test_fetch` (same directory,
not a package) rather than a second copy of that harness. No socket is opened and the real
cache is never touched.
"""

from __future__ import annotations

import json

from ohyesmlx import fetch, server

from test_fetch import CONFIG, REPO, TWO_FILES, WEIGHTS, Harness, make_model, serve


def test_done_arrives_while_the_lock_is_still_held_and_the_ledger_is_unwritten(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)
    observed = {}

    def emit(event):
        if event["type"] != "done":
            return
        lock_file = harness.locks / fetch.LOCK_NAME
        ledger_lists_repo = False
        if harness.ledger.exists():
            ledger_lists_repo = REPO in json.loads(harness.ledger.read_text())["repos"]
        observed["lock_present_at_done"] = lock_file.exists()
        observed["ledger_lists_repo_at_done"] = ledger_lists_repo

    assert harness.download(emit=emit) is True

    assert observed == {
        "lock_present_at_done": False,
        "ledger_lists_repo_at_done": True,
    }


def test_the_job_slot_is_freed_when_the_worker_returns_and_done_is_published_after():
    registry = server._Jobs()
    job = server._Job(registry, "0" * 16, "download", REPO)
    assert registry.claim(job) is None

    job.append(server._event("result", "downloaded", None))
    job.append(server._event("done", "download finished", None))

    assert registry.running is job, "the module's done frees nothing: its finally has not run"
    assert job.done is False and job.events[-1]["type"] == "result"

    job.finish("unused")

    assert registry.running is None
    assert job.done is True and job.events[-1]["type"] == "done"
    assert job.events[-1]["message"] == "download finished"
