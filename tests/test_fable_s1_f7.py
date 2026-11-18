"""Fable 5.2 S1-F7: a lab-path refusal after the pip steps leaves a venv nothing rolls back.

`install.run_steps` calls `record_lab_path` after the step loop, outside the failed-step
branch (engines.py:1294-1295). `record_lab_path` raises `ValueError` from `check_lab_dir`
(engines.py:493) or `lab_paths` (engines.py:494) -- e.g. an existing `lab-paths.json` with
a key this version refuses. The raise unwinds `run_steps`, so the `created` venv root is
never passed to `_rollback` and no installer-authored `error`/`done` is emitted. The
server's `_run_job` catch-all then reports `internal` after the irreversible install, with
the venv still on disk and no lab path recorded.

The invariant: a late refusal takes the same rollback-and-refuse path a failed step does.
Nothing real runs: the subprocess seam creates the venv directory a real `-m venv` would,
detection and disk are literals, and every path is under `tmp_path`.
"""

from __future__ import annotations

import functools
import json
import os
from types import SimpleNamespace

from ohyesmlx import engines, server


def _create_venv(argv, timeout, env):
    root = engines._venv_root(argv)
    if root is not None and not os.path.lexists(root):
        os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    return 0, ""


def _detect_not_installed():
    return [SimpleNamespace(name="mlxlm", installed=False)]


def _hardware():
    return SimpleNamespace(disk_free_bytes=500 * 1024**3)


def test_a_lab_paths_refusal_after_the_pip_steps_rolls_the_venv_back(tmp_path):
    engines_dir = tmp_path / "engines"
    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(json.dumps({"bogus": "/x"}) + "\n", encoding="utf-8")
    root = engines_dir / f"mlxlm-{engines.TESTED_VERSIONS['mlxlm']}"

    install = functools.partial(
        engines.install,
        run=_create_venv,
        detect=_detect_not_installed,
        hardware=_hardware,
        sleep=lambda seconds: None,
        log_path=str(tmp_path / "install-log.jsonl"),
        lock=engines.EngineLocks(),
        python="/fake/python",
        engines_dir=str(engines_dir),
        timeout_s=900,
    )
    registry = server._Jobs()
    job = server._Job(registry, "0" * 16, "install", "mlxlm")
    assert registry.claim(job) is None
    handler = SimpleNamespace(
        server=SimpleNamespace(install=install), _macos_major=lambda: 15
    )

    server._Handler._run_job(handler, job)

    assert job.events[-1]["type"] == "done"
    assert job.events[-2]["type"] == "error"
    assert job.events[-2]["payload"]["code"] != "internal", (
        "the lab-path refusal reached the server's catch-all; install neither refused it "
        "nor took its rollback path"
    )
    assert not root.exists(), (
        "the venv the successful steps created is still on disk, unrecorded and unrolled back"
    )
    assert json.loads(lab_paths.read_text()) == {"bogus": "/x"}
