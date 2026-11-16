"""Fable 5.2 S5-F11: a handle signals the process group of a stranger that inherited a
reaped launcher pid.

``await_ready`` polls ``_process_alive(spawned)`` (:2220), and for ``osaurus serve`` -- a
launcher that exits after handoff -- that poll reaps the child with ``waitpid(WNOHANG)``
(:618-624). The pid is then free for reuse, but the handle keeps it for the rest of the cell.
At stop, ``_process_alive`` finds ``waitpid`` raising ``ECHILD`` and falls through to
``os.kill(pid, 0)`` (:625-631), which answers for whatever same-user process holds the number
now; ``_signal_tree`` (:651-659) then sends TERM, and after the grace period KILL, to
``os.getpgid(pid)`` -- that stranger's whole group.

Nothing here starts a server or signals a process: the pid belongs to a child this test
spawned, ``os.kill``/``os.getpgid``/``os.killpg`` are faked to answer for it the way the
kernel answers for a reused pid, and the only assertion is that no group signal was sent.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from ohyesmlx import runtimes


def launcher_reaped_by_the_readiness_poll():
    """A spawned launcher that has exited and been reaped by ``_process_alive`` itself.

    This is the sequence ``await_ready`` performs: poll ``_process_alive`` until it answers
    False, and the ``waitpid(WNOHANG)`` inside that call is what reaps the child.
    """
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if runtimes._process_alive(child.pid) is False:
            return child.pid
        time.sleep(0.01)
    child.kill()
    raise AssertionError("precondition: the launcher never exited")


def test_handle_stop_never_signals_the_group_of_a_pid_it_already_reaped(tmp_path, monkeypatch):
    """The reaped launcher pid now belongs to a stranger; stop must not signal its group."""
    pid = launcher_reaped_by_the_readiness_poll()

    signalled = []
    # The pid has been handed out again: kill(pid, 0) and getpgid(pid) answer for the holder.
    # No precondition is asserted here on `_process_alive`, deliberately: today it reads the
    # reused number as alive (which is the bug), and a fix makes it read as gone.
    monkeypatch.setattr(os, "kill", lambda target, sig: None)
    monkeypatch.setattr(os, "getpgid", lambda target: 777)
    monkeypatch.setattr(os, "killpg", lambda group, sig: signalled.append((group, sig)))

    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: ())
    monkeypatch.setattr(runtimes, "_run", lambda command, timeout_s: None)
    monkeypatch.setattr(runtimes, "writable_root", lambda: tmp_path)
    clock = iter(range(0, 10_000))
    monkeypatch.setattr(runtimes, "_now", lambda: float(next(clock)))
    monkeypatch.setattr(runtimes, "_sleep", lambda seconds: None)

    handle = runtimes.Handle(
        pid=pid,
        port=1337,
        base_url="http://127.0.0.1:1337/v1",
        model_id="m",
        version="1.0",
        cold_load_s=0.0,
        stop_command=("osaurus", "stop"),
    )
    # A fix may stop raising here (nothing is left to signal); the assertion is the signal.
    try:
        handle.stop()
    except runtimes.RuntimeStopError:
        pass

    assert signalled == [], (
        f"stop signalled process group(s) {signalled} for pid {pid}, which this process "
        "reaped while waiting for the runtime to become ready; the group belongs to "
        "whoever inherited the number"
    )
