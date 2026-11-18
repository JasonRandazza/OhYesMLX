"""S4-F10: a raise on the install failure path skips the rollback.

`engines.install`'s failure branch is `send("error", ...)` followed by `_rollback(...)` and
`send("done", ...)` (engines.py:1270-1280), and `cancelled` is the same shape (:1232-1237).
`send` (:1199-1213) first appends to `install-log.jsonl` through `_append_install_log`
(:1141-1156), whose `open(log_path, "a")` is unguarded, then calls `emit`. Either one raising
-- an ENOSPC log append, a caller's emitter -- means `_rollback` never runs and the half venv
the failed step created stays behind: the F2 state, reached without a rollback refusal.

The test drives `install` with the same fakes `tests/test_engines.py` uses, and raises from
`emit` on the `error` event, which is the finding's own test idea. No engine is installed, no
subprocess runs, nothing outside `tmp_path` is touched.
"""

from __future__ import annotations

import os
from pathlib import Path

from test_engines import FakeDetect, FakeLock, FakeRun, do_install

from ohyesmlx import engines


def create_venv(argv):
    """What a real `-m venv` step leaves: the directory its argv names."""
    if "venv" in argv:
        (Path(argv[-1]) / "bin").mkdir(parents=True, exist_ok=True)


def test_an_emitter_that_raises_on_the_error_event_still_rolls_the_venv_back(tmp_path):
    """The venv step mentioned a failed pip step created is gone after `install` returns."""
    root = tmp_path / "engines" / f"mlxlm-{engines.TESTED_VERSIONS['mlxlm']}"
    raised = []

    def emit(event):
        if event["type"] == "error":
            raised.append(event)
            raise OSError(28, "No space left on device")

    try:
        do_install(
            tmp_path,
            run=FakeRun([(0, "venv made"), (1, "no space left on device")], on_call=create_venv),
            emit=emit,
        )
    except OSError:
        pass

    assert raised, "precondition: the step failure emitted an `error` event"
    assert not root.exists(), (
        f"the venv at {root} was created by the venv step and left on disk: `send('error')` "
        f"raised before `_rollback` ran"
    )
    assert not (tmp_path / "lab-paths.json").exists(), (
        "a failed install must not record a lab path"
    )


class _AppendThatFailsOnErrorLines:
    """A log handle whose `write` raises ENOSPC for the `error` event's line, and only that."""

    def __init__(self, handle, refused):
        self.handle = handle
        self.refused = refused

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.handle.close()
        return False

    def write(self, text):
        if '"type": "error"' in text:
            self.refused.append(text)
            raise OSError(28, "No space left on device")
        return self.handle.write(text)


def test_a_log_append_that_raises_on_the_error_event_still_rolls_the_venv_back(tmp_path):
    """The finding's named trigger: the append itself raises (ENOSPC on install-log.jsonl)."""
    root = tmp_path / "engines" / f"mlxlm-{engines.TESTED_VERSIONS['mlxlm']}"
    log_path = tmp_path / "install-log.jsonl"
    real_open = open
    refused = []

    def open_that_refuses(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        if os.path.realpath(str(path)) == os.path.realpath(str(log_path)) and "a" in args[0]:
            return _AppendThatFailsOnErrorLines(handle, refused)
        return handle

    events = []
    engines.open = open_that_refuses
    try:
        try:
            do_install(
                tmp_path,
                run=FakeRun(
                    [(0, "venv made"), (1, "no space left on device")], on_call=create_venv
                ),
                emit=events.append,
            )
        except OSError:
            pass
    finally:
        del engines.open

    assert refused, "precondition: the install log append on the failure path raised"
    assert not root.exists(), (
        f"the venv at {root} was created by the venv step and left on disk: the log append "
        f"that precedes `_rollback` raised, so the rollback never ran"
    )
