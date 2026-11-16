"""Reproduction for Fable 5.2 S2-F3: a cell measured across two runtime builds reports one.

The claim: ``measure._visit`` stamps ``runtime_version`` only on the first visit that started.
The assignment sits inside ``if result.cold_load_s is None`` (``measure.py:861-865``), and
``grep -n "handle.version" ohyesmlx/*.py`` finds that one line and nothing else — so a second
visit starts the same runtime again, and whatever build it reports is read by nobody.

The consequence the finding names: a GUI runtime with an updater (Osaurus has gone
0.25.6 -> 0.25.18, which is guard 4's own documented 1.15x step) updates between a cell's cold
and hot visit; the row's samples then come from two builds while the row carries the first
build's version. ``report._check_one_value_per_key`` (guard 4) compares one string per row and
``_check_known_runtime_versions`` only refuses ``unknown`` prefixes, so neither can see it.

The test drives the real ``_visit`` loop through the existing harness fakes, with a runtime
whose handle answers a different version on each start. Two visits are forced the only way the
loop makes them: a nine-batch budget is split across ``VISIT_ROUNDS`` (5 + 4).

On the current code the row is PASS and stamped with the first visit's build, so both tests
fail. They pass only when a later visit's version is compared and a mismatch makes the row
something other than PASS with both builds named.
"""

from __future__ import annotations

import json

import pytest

from test_measure import Harness, FakeRuntime


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """``test_measure``'s harness, which is a fixture in that file rather than in conftest."""
    return Harness(monkeypatch, tmp_path)


class UpdatingRuntime(FakeRuntime):
    """One runtime whose build changes between visits: start #1 answers one version, #2 another.

    The real handle takes its version at ``start()`` (``runtimes.Handle.version`` is read once,
    after the process is up), so the fake takes its version there too. Everything else is the
    shared fake, so the loop under test is the real one.
    """

    def __init__(self, name, recorder, versions, **kwargs):
        super().__init__(name, recorder, **kwargs)
        self.versions = list(versions)

    def start(self, *args, **kwargs):
        # ``attempts`` is incremented by the parent's ``start``; read it before the call so
        # visit 1 answers ``versions[0]`` and visit 2 answers ``versions[1]``.
        index = min(self.attempts, len(self.versions) - 1)
        self.version = self.versions[index]
        return super().start(*args, **kwargs)


FIRST = "0.25.6"
SECOND = "0.25.18"


def an_updated_runtime(harness):
    runtime = UpdatingRuntime(
        "osaurus", harness.recorder, [FIRST, SECOND], port=1337, cold_load_s=7.5
    )
    harness.runtimes.RUNTIMES["osaurus"] = runtime
    return runtime


def test_an_update_between_visits_cannot_leave_a_pass_row(harness):
    """Two visits, two builds: the row is one build or it is not a row.

    A PASS row's figures come from whatever the runtime did on both visits. A build change
    between them is the held-constant variable moving inside one row, which is the one thing
    this project refuses to publish — guard 4 exists to refuse exactly this between run
    directories, and its own docstring records 1.15x across such a step.
    """
    runtime = an_updated_runtime(harness)

    results = harness.run([harness.cell("oq__osaurus", "osaurus")], measured=9)

    assert runtime.attempts == 2, (
        "the nine-batch budget must be split across two visits for this to be the question; "
        f"the loop started the runtime {runtime.attempts} time(s)"
    )
    assert [handle.version for handle in runtime.handles] == [FIRST, SECOND]

    result = results[0]
    assert result.status != "PASS", (
        f"a row measured across {FIRST} and {SECOND} published {result.status} "
        f"stamped {result.runtime_version!r}: samples from two builds are one row"
    )
    assert FIRST in (result.reason or "") and SECOND in (result.reason or ""), (
        f"the verdict names one build only: {result.reason!r}"
    )


def test_the_persisted_record_cannot_present_two_builds_as_one(harness):
    """What a reader of ``results.jsonl`` is told, and what it cannot be told.

    The record keeps every sample, so the raw evidence of both builds is on disk — but the one
    field that names a build is stamped on the first visit only, and nothing else in the record
    carries the second. Nor can a consumer recover it: guard 4 compares one string per row
    (``report.py:1649-1660``) and the unknown-version check only refuses ``unknown`` prefixes
    (``report.py:1481-1494``). A PASS line that says ``0.25.6`` after ``0.25.18`` measured the
    hot visit is exactly the row the project's rules forbid, and nothing downstream can mark it.
    """
    from ohyesmlx import report

    runtime = an_updated_runtime(harness)

    results = harness.run([harness.cell("oq__osaurus", "osaurus")], measured=9)

    assert [handle.version for handle in runtime.handles] == [FIRST, SECOND]
    record, = harness.lines()
    line = json.dumps(record)
    runs = [("run", harness.header(), [record])]

    # The two guards that read a version, run over this record: both accept it. The blindness
    # is evidence for the finding's second half, not the defect itself.
    report._check_known_runtime_versions(runs)
    report._check_one_value_per_key(
        runs,
        field="runtime_version",
        kind="runtime",
        key_of=lambda row: (row.get("runtime"), row.get("runtime_version")),
        verb="measured",
        clause="two versions of one runtime are two results",
    )

    assert results[0].runtime_version == FIRST
    assert SECOND in line, (
        "the FAIL record must name both builds so the mixed-build evidence is persisted: "
        f"{SECOND} is absent from {record}"
    )
    assert not (record["status"] == "PASS" and record["runtime_version"] == FIRST), (
        f"the record publishes status {record['status']} stamped "
        f"{record['runtime_version']!r} while the hot visit ran {SECOND}; and neither guard "
        f"notices, because neither can see a second version on one row"
    )
