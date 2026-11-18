"""Fable 5.2 S6-F7: check_bundle's P5-9 environment match is a substring, not a token.

``scripts/check_bundle.sh:213-231`` reads the backend's environment with
``/bin/ps eww -p "$BACKEND_PID" -o command=`` and decides P5-9 with two ``case``
patterns:

* ``*"PATH=/usr/bin:/bin:/usr/sbin:/sbin"*`` accepts any variable whose value
  *begins* with launchd's default, so ``PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin``
  prints "the backend's PATH is launchd's default", and ``MANPATH=/usr/bin:/bin:/usr/sbin:/sbin``
  satisfies it with no ``PATH`` at all (``*MANPATH=*`` ends with ``PATH=``).
* only ``PYTHONPATH=`` and ``PYTHONHOME=`` are looked for, but the message reads
  "the backend carries no PYTHON* variable".

The ``case`` block is read out of the script here rather than copied, so a change
to ``check_bundle.sh`` changes what these tests exercise.  The ``pass``/``fail``
helpers and the ``FAILURES`` counter are the script's own.  Nothing is started:
the dump is a fixture string, which is the only thing the block consumes.

The finding's other half -- that macOS 27.2.1 withholds another process's
environment, so the ``*)`` branch FAILs and the gate cannot print "all checks
PASS" -- is not testable from here and is refuted by measurement instead; see
``.paul/review/fable-5.2/verify/S6-F7.md``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_bundle.sh"

BACKEND_ARGV = "python3 -I -B -m ohyesmlx.cli app"

LAUNCHD_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "HOME": "/Users/tester",
    "USER": "tester",
    "LOGNAME": "tester",
    "TMPDIR": "/var/folders/test/",
    "LANG": "en_US.UTF-8",
}


def _helpers_and_case(text: str) -> tuple[str, str]:
    """The script's PASS/FAIL helpers and the ``case "$ENV_DUMP" in`` block."""
    lines = text.splitlines()
    helpers = [
        line
        for line in lines
        if line.strip() == "FAILURES=0"
        or line.strip().startswith("pass() {")
        or line.strip().startswith("fail() {")
    ]
    assert len(helpers) == 3, f"expected FAILURES=0 and two helpers, got {helpers!r}"

    start = None
    for index, line in enumerate(lines):
        if "ENV_DUMP=$(/bin/ps eww" in line:
            for candidate in range(index + 1, len(lines)):
                stripped = lines[candidate].strip()
                if stripped.startswith("case ") and "ENV_DUMP" in stripped:
                    start = candidate
                    break
            break
    assert start is not None, "check_bundle.sh no longer reads ENV_DUMP into a case"

    depth = 0
    block: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("case "):
            depth += 1
        block.append(line)
        if stripped == "esac":
            depth -= 1
            if depth == 0:
                break
    assert depth == 0, "unbalanced case/esac in the extracted block"
    return "\n".join(helpers), "\n".join(block)


def _dump(**overrides: str | None) -> str:
    """A ``ps eww -o command=`` line: argv, then ``KEY=value`` pairs."""
    pairs = {**LAUNCHD_ENV, **overrides}
    rendered = " ".join(f"{key}={value}" for key, value in pairs.items() if value is not None)
    return f"{BACKEND_ARGV} {rendered}"


def _run(env_dump: str) -> tuple[str, int]:
    """Feed the dump to the script's own block; return its output and FAILURES."""
    helpers, block = _helpers_and_case(SCRIPT.read_text())
    program = "\n".join([helpers, block, 'echo "COUNT=$FAILURES"', ""])
    proc = subprocess.run(
        ["/bin/sh", "-c", program],
        capture_output=True,
        text=True,
        env={**os.environ, "ENV_DUMP": env_dump},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    count = int(proc.stdout.rsplit("COUNT=", 1)[1].strip())
    return proc.stdout, count


def test_the_exact_launchd_path_and_no_python_variable_pass() -> None:
    """The state BackendLauncher produces is accepted (the check's happy path)."""
    output, count = _run(_dump())
    assert count == 0, output
    assert "PASS P5-9: the backend's PATH is launchd's default" in output
    assert "PASS P5-9: the backend carries no PYTHON* variable" in output


def test_a_longer_path_is_not_launchds_default() -> None:
    """``PATH`` with an extra directory must FAIL; the prefix match passes it today."""
    output, count = _run(_dump(PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"))
    assert "FAIL P5-9" in output, output
    assert count == 1, output


def test_manpath_is_not_a_path() -> None:
    """No ``PATH`` at all, but ``MANPATH`` ends in ``PATH=`` and satisfies the match."""
    output, count = _run(_dump(PATH=None, MANPATH="/usr/bin:/bin:/usr/sbin:/sbin"))
    assert "FAIL P5-9" in output, output
    assert count >= 1, output


def test_python_variables_beyond_path_and_home_are_found() -> None:
    """The message says PYTHON*, the patterns name two."""
    output, count = _run(_dump(PYTHONEXECUTABLE="/tmp/x"))
    assert "FAIL P5-9: the backend carries a PYTHON* variable" in output, output
    assert count == 1, output
