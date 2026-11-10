#!/usr/bin/env python3
"""Rewrite a pip freeze in place with the hashes PyPI lists for every pin.

The installer installs with ``--require-hashes`` (``engines._command_plan``), so each
``ohyesmlx/constraints/<engine>-<version>.txt`` is a full requirements file: every
``name==version`` line followed by one ``--hash=sha256:`` line per file PyPI publishes for
that exact version. A version pin alone does not stop a compromised maintainer from adding
a file to an existing version; a hash list does.

Usage::

    scripts/hash_freeze.py ohyesmlx/constraints/<engine>-<version>.txt

Metadata only: each pin is read from ``https://pypi.org/pypi/<name>/<version>/json`` and no
artifact is downloaded. The freeze's header comment lines are kept and one is added naming
the source and the date. A pin with no file, or a failed fetch, exits non-zero naming the
pin and writes nothing, because a half-hashed file refuses to install for a reason nobody
could read from it.

It also prints, under a LATE UPLOADS heading, every file uploaded more than seven days after
that version's first file. A file added to an existing version is the attack the hashes
exist to catch, so one added before this freeze was made is reviewed rather than trusted
blindly -- and reported rather than dropped, because a new-ABI wheel is often late for a
good reason.
"""

from __future__ import annotations

import json
import pathlib
import re
import ssl
import sys
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ohyesmlx import atomic_write_text  # noqa: E402  (after the repo root joins sys.path)

PYPI_ROOT = "https://pypi.org/"
PYPI_JSON = PYPI_ROOT + "pypi/{name}/{version}/json"
LATE_AFTER = timedelta(days=7)
HASHES_PREFIX = "# hashes: "
HASHES_HEADER = (
    HASHES_PREFIX
    + "every file PyPI lists for each pin, https://pypi.org/pypi/<name>/<version>/json, {date}"
)

_PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*)$")


def _require_pypi(url: str) -> None:
    """Refuse any URL that is not https on pypi.org: the one place that host is spelled twice."""
    if not url.startswith(PYPI_ROOT):
        raise ValueError(f"refusing to fetch {url}: only {PYPI_ROOT} is allowed")


def _fetch_json(url: str) -> dict:
    """The parsed JSON at *url*, over the default SSL context (verification on)."""
    _require_pypi(url)
    context = ssl.create_default_context()
    with urllib.request.urlopen(url, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _logical_lines(text: str):
    """The file's lines with ``\\`` continuations joined, so a hashed pin reads as one line."""
    pending = ""
    for line in text.splitlines():
        line = pending + " " + line.strip() if pending else line
        pending = ""
        if line.rstrip().endswith("\\"):
            pending = line.rstrip()[:-1].rstrip()
            continue
        yield line
    if pending:
        yield pending


def parse_freeze(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """The header comment lines and the ``(name, version)`` pins, in file order.

    Hash lines are ignored, so the script rewrites its own output rather than only a bare
    ``pip freeze``.
    """
    header = []
    pins = []
    for line in _logical_lines(text):
        stripped = line.strip()
        if stripped.startswith("#"):
            if not pins:
                header.append(stripped)
            continue
        if not stripped:
            continue
        match = _PIN.match(stripped.split()[0])
        if match is None:
            raise ValueError(f"{stripped.split()[0]!r} is not a name==version pin")
        pins.append((match["name"], match["version"]))
    return header, pins


def _digests(payload: dict) -> list[str]:
    """Every file's sha256 for one version, sorted: the hash list a pin line carries."""
    return sorted(
        entry["digests"]["sha256"] for entry in payload.get("urls") or []
    )


def _upload_time(entry: dict):
    """A file's upload time, or None when PyPI does not state one."""
    text = entry.get("upload_time_iso_8601")
    if not isinstance(text, str):
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _late_files(name: str, payload: dict) -> list[tuple[str, str, str]]:
    """The files uploaded more than ``LATE_AFTER`` after that version's first file."""
    dated = [(entry, _upload_time(entry)) for entry in payload["urls"]]
    times = [when for _entry, when in dated if when is not None]
    if not times:
        return []
    earliest = min(times)
    return [
        (name, entry.get("filename", "?"), when.isoformat())
        for entry, when in dated
        if when is not None and when - earliest > LATE_AFTER
    ]


def _render(header: list[str], blocks: list[tuple[str, list[str]]]) -> str:
    """The whole file: the kept header plus one hashes line, then each pin and its hashes."""
    lines = [line for line in header if not line.startswith(HASHES_PREFIX)]
    lines.append(HASHES_HEADER.format(date=date.today().isoformat()))
    for pin, hashes in blocks:
        lines.append(pin + " \\")
        for digest in hashes[:-1]:
            lines.append(f"    --hash=sha256:{digest} \\")
        lines.append(f"    --hash=sha256:{hashes[-1]}")
    return "\n".join(lines) + "\n"


def main(argv: list[str], fetch_json=_fetch_json) -> int:
    """Rewrite ``argv[0]``; 0 on success, non-zero (and nothing written) otherwise."""
    if len(argv) != 1:
        print("usage: hash_freeze.py <freeze-file>", file=sys.stderr)
        return 2
    path = pathlib.Path(argv[0])
    try:
        header, pins = parse_freeze(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        return 1
    if not pins:
        print(f"{path}: no name==version pins to hash", file=sys.stderr)
        return 1

    blocks: list[tuple[str, list[str]]] = []
    problems: list[str] = []
    late: list[tuple[str, str, str]] = []
    for name, version in pins:
        pin = f"{name}=={version}"
        try:
            url = PYPI_JSON.format(name=name, version=version)
            _require_pypi(url)
            payload = fetch_json(url)
            hashes = _digests(payload)
        except Exception as error:  # a fetch or a payload that raised is a pin that did not resolve
            problems.append(f"{pin}: fetch failed: {error}")
            continue
        if not hashes:
            problems.append(f"{pin}: PyPI lists no files for it")
            continue
        if any(entry.get("yanked") for entry in payload["urls"]):
            print(f"warning: {pin} is yanked on PyPI")
        late.extend(_late_files(name, payload))
        blocks.append((pin, hashes))

    if late:
        print("LATE UPLOADS")
        for package, filename, when in late:
            print(f"  {package}  {filename}  {when}")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"{path}: nothing written; {len(problems)} pin(s) did not resolve", file=sys.stderr)
        return 1

    atomic_write_text(path, _render(header, blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
