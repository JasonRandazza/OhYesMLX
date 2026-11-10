"""Checks for ``scripts/hash_freeze.py``, with no network.

The script is a maintenance tool rather than a package module, so it is loaded from its
path. Every lookup goes through an injected fetcher replaying literal PyPI JSON, and every
expected value below is written out here rather than computed from the code under test.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hash_freeze.py"

_spec = importlib.util.spec_from_file_location("hash_freeze", SCRIPT)
hash_freeze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hash_freeze)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64

FREEZE = """# pip constraints for the test lab copy: its full dependency set, frozen 2026-11-02 (T2.5.5).
# Venv: /tmp/lab-venv
# Interpreter: Python 3.14.10 (arm64)
Alpha==1.0.0
Beta==2.3
"""

HEADER = (
    "# hashes: every file PyPI lists for each pin, "
    "https://pypi.org/pypi/<name>/<version>/json, "
)


def file_entry(filename, digest, *, upload="2026-11-02T10:00:00.000000Z", yanked=False):
    return {
        "filename": filename,
        "digests": {"sha256": digest},
        "upload_time_iso_8601": upload,
        "yanked": yanked,
    }


def payload(*entries):
    return {"urls": list(entries)}


def write_freeze(tmp_path, text=FREEZE):
    path = tmp_path / "constraints.txt"
    path.write_text(text, encoding="utf-8")
    return path


def fetcher(payloads):
    def fetch(url):
        if url not in payloads:
            raise AssertionError(f"unexpected fetch {url}")
        return payloads[url]

    return fetch


def pinned_pairs(text):
    """Every ``name==version`` token in *text*, in order, ignoring comments and hashes."""
    pairs = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--hash="):
            continue
        pairs.append(stripped.split()[0])
    return pairs


def test_hashes_are_every_listed_file_sorted_under_each_pin(tmp_path):
    freeze = write_freeze(tmp_path)
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry("Alpha-1.0.0-py3-none-any.whl", HEX_B),
                file_entry("Alpha-1.0.0.tar.gz", HEX_A),
                file_entry("Alpha-1.0.0-cp314.whl", HEX_C),
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(
                file_entry("Beta-2.3.tar.gz", HEX_A)
            ),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0

    lines = freeze.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == FREEZE.splitlines()[:3]
    assert lines[3].startswith(HEADER)
    assert date.fromisoformat(lines[3].rsplit(", ", 1)[1]) == date.today()
    assert lines[4:] == [
        "Alpha==1.0.0 \\",
        f"    --hash=sha256:{HEX_A} \\",
        f"    --hash=sha256:{HEX_B} \\",
        f"    --hash=sha256:{HEX_C}",
        "Beta==2.3 \\",
        f"    --hash=sha256:{HEX_A}",
    ]


def test_the_pin_set_is_identical_before_and_after_hashing(tmp_path):
    freeze = write_freeze(tmp_path)
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry("Alpha-1.0.0-py3-none-any.whl", HEX_A)
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(
                file_entry("Beta-2.3.tar.gz", HEX_B)
            ),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0

    assert pinned_pairs(freeze.read_text(encoding="utf-8")) == ["Alpha==1.0.0", "Beta==2.3"]


def test_a_second_run_replaces_the_hash_header_instead_of_adding_one(tmp_path):
    freeze = write_freeze(tmp_path)
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry("Alpha-1.0.0-py3-none-any.whl", HEX_A)
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(
                file_entry("Beta-2.3.tar.gz", HEX_B)
            ),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0
    first = freeze.read_text(encoding="utf-8")
    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0

    assert freeze.read_text(encoding="utf-8") == first
    assert sum(1 for line in first.splitlines() if line.startswith(HEADER)) == 1


def test_a_pin_with_no_files_exits_non_zero_and_leaves_the_file_byte_identical(tmp_path, capsys):
    freeze = write_freeze(tmp_path)
    before = freeze.read_bytes()
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry("Alpha-1.0.0-py3-none-any.whl", HEX_A)
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) != 0

    assert "Beta==2.3" in capsys.readouterr().err
    assert freeze.read_bytes() == before


def test_a_failed_fetch_is_named_and_writes_nothing(tmp_path, capsys):
    freeze = write_freeze(tmp_path)
    before = freeze.read_bytes()

    def refuse(url):
        raise OSError("connection refused")

    assert hash_freeze.main([str(freeze)], fetch_json=refuse) != 0

    assert "Alpha==1.0.0" in capsys.readouterr().err
    assert freeze.read_bytes() == before


def test_a_yanked_pin_is_printed_as_a_warning(tmp_path, capsys):
    freeze = write_freeze(tmp_path)
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry("Alpha-1.0.0-py3-none-any.whl", HEX_A, yanked=True)
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(
                file_entry("Beta-2.3.tar.gz", HEX_B)
            ),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0

    printed = capsys.readouterr().out
    assert "Alpha==1.0.0" in printed
    assert "yanked" in printed
    assert "Beta==2.3" not in printed


def test_a_file_uploaded_more_than_a_week_late_is_flagged(tmp_path, capsys):
    freeze = write_freeze(tmp_path)
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry(
                    "Alpha-1.0.0-py3-none-any.whl", HEX_A, upload="2026-11-02T00:00:00.000000Z"
                ),
                file_entry(
                    "Alpha-1.0.0-cp314.whl", HEX_B, upload="2026-11-12T00:00:00.000000Z"
                ),
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(
                file_entry("Beta-2.3.tar.gz", HEX_C, upload="2026-11-02T00:00:00.000000Z")
            ),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0

    printed = capsys.readouterr().out
    assert "LATE UPLOADS" in printed
    late = printed.split("LATE UPLOADS", 1)[1]
    assert "Alpha" in late
    assert "Alpha-1.0.0-cp314.whl" in late
    assert "2026-11-12T00:00:00+00:00" in late
    assert "Alpha-1.0.0-py3-none-any.whl" not in late
    assert "Beta-2.3.tar.gz" not in late


def test_a_file_exactly_seven_days_after_the_first_is_not_late(tmp_path, capsys):
    freeze = write_freeze(tmp_path)
    fetch = fetcher(
        {
            "https://pypi.org/pypi/Alpha/1.0.0/json": payload(
                file_entry(
                    "Alpha-1.0.0-py3-none-any.whl", HEX_A, upload="2026-11-02T00:00:00.000000Z"
                ),
                file_entry(
                    "Alpha-1.0.0-cp314.whl", HEX_B, upload="2026-11-09T00:00:00.000000Z"
                ),
            ),
            "https://pypi.org/pypi/Beta/2.3/json": payload(
                file_entry("Beta-2.3.tar.gz", HEX_C)
            ),
        }
    )

    assert hash_freeze.main([str(freeze)], fetch_json=fetch) == 0

    assert "LATE UPLOADS" not in capsys.readouterr().out


def test_only_https_pypi_org_urls_are_fetched():
    with pytest.raises(ValueError, match="https://pypi.org/"):
        hash_freeze._require_pypi("https://example.com/pypi/Alpha/1.0.0/json")
    with pytest.raises(ValueError, match="https://pypi.org/"):
        hash_freeze._require_pypi("http://pypi.org/pypi/Alpha/1.0.0/json")

    hash_freeze._require_pypi("https://pypi.org/pypi/Alpha/1.0.0/json")
