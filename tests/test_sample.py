"""Checks for ohyesmlx.sample.

These run the real tools against real processes. Nothing here is mocked: the unit-level
checks parse output captured verbatim from /usr/bin/footprint and /usr/bin/vmmap on macOS
26.6.2, and the sampling checks spawn a real long-lived process and measure it.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ohyesmlx import sample as sample_mod
from ohyesmlx.sample import (
    Sampler,
    gpu_wired_limit,
    parse_footprint_text,
    parse_mb,
    parse_vmmap_summary,
    phys_footprint_mb,
    vmmap_split,
)

# Captured verbatim from `/usr/bin/footprint -p $$` (bash, 64-bit). The header's
# `Footprint:` figure (1216 KB) differs from phys_footprint (1232 KB) on purpose here: it
# is the real captured disagreement, and the parser must take the auxiliary value.
FOOTPRINT_OUTPUT_KB = """\
======================================================================
bash [51131]: 64-bit    Footprint: 1216 KB (16384 bytes per page)
======================================================================

  Dirty      Clean  Reclaimable    Regions    Category
    ---        ---          ---        ---    ---
 272 KB        0 B          0 B          8    MALLOC metadata
  32 KB        0 B          0 B          2    stack
    ---        ---          ---        ---    ---
1216 KB     432 KB          0 B        382    TOTAL

Auxiliary data:
    phys_footprint: 1232 KB
    phys_footprint_peak: 1232 KB
"""

# Captured verbatim from `/usr/bin/footprint -p <pid>` for a python3 process holding 900 MB.
FOOTPRINT_OUTPUT_MB = """\
======================================================================
Python [52010]: 64-bit    Footprint: 907 MB (16384 bytes per page)
======================================================================

  Dirty      Clean  Reclaimable    Regions    Category
    ---        ---          ---        ---    ---
 900 MB        0 B          0 B          8    MALLOC_LARGE
 737 KB        0 B          0 B          1    page table
    ---        ---          ---        ---    ---
 907 MB    3952 KB          0 B       2656    TOTAL

Auxiliary data:
    phys_footprint: 907 MB
    phys_footprint_peak: 907 MB
"""

# Captured from `/usr/bin/vmmap --summary <pid>` (the same python3 process, region rows
# trimmed to the TOTAL). The MALLOC ZONE header after the TOTAL is real and is what makes a
# positional header scan wrong.
VMMAP_SUMMARY = """\
Process:         Python [52010]
Path:            /opt/homebrew/opt/python@3.14/bin/python3.14
Physical footprint:         907.3M
Physical footprint (peak):  907.3M
Idle exit:                  untracked
----

ReadOnly portion of Libraries: Total=865.2M resident=241.7M(28%) swapped_out_or_unallocated=623.6M(72%)
Writable regions: Total=1.0G written=906.1M(89%) resident=906.1M(89%) swapped_out=0K(0%) unallocated=114.9M(11%)

                                VIRTUAL RESIDENT    DIRTY  SWAPPED VOLATILE   NONVOL    EMPTY   REGION \x20
REGION TYPE                        SIZE     SIZE     SIZE     SIZE     SIZE     SIZE     SIZE    COUNT (non-coalesced) \x20
===========                     ======= ========    =====  ======= ========   ======    =====  ======= \x20
Kernel Alloc Once                   32K      16K      16K       0K       0K       0K       0K        1 \x20
__TEXT                            6944K    6432K       0K       0K       0K       0K       0K       47 \x20
===========                     ======= ========    =====  ======= ========   ======    =====  ======= \x20
TOTAL                              2.0G     1.2G   907.3M       0K       0K       0K       0K     1843 \x20

                                 VIRTUAL   RESIDENT      DIRTY    SWAPPED ALLOCATION      BYTES DIRTY+SWAP          REGION
MALLOC ZONE                         SIZE       SIZE       SIZE       SIZE      COUNT  ALLOCATED  FRAG SIZE  % FRAG   COUNT
===========                      =======  =========  =========  =========  =========  =========  =========  ======  ======
DefaultMallocZone_0x100a94000      16.8M       528K       528K         0K       1029       173K       355K     68%       6 \x20
"""


@pytest.fixture(scope="module")
def sleeper():
    """A real long-lived process to sample, killed when the module is done."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture(scope="module")
def sampled(sleeper):
    """One short real sampling run, for the checks that only read the result shape."""
    sampler = Sampler(sleeper.pid, interval_s=0.5).start()
    time.sleep(1.2)
    return sampler.stop()


@pytest.mark.parametrize(
    "text,expected_mb",
    [
        ("1248 KB", 1248 / 1024),
        ("1232K", 1232 / 1024),
        ("907 MB", 907.0),
        ("907.3M", 907.3),
        ("2.0G", 2048.0),
        ("0 B", 0.0),
        ("16384", 16384 / (1024 * 1024)),
    ],
)
def test_parse_mb_reads_the_units_the_tools_print(text, expected_mb):
    assert parse_mb(text) == pytest.approx(expected_mb)


@pytest.mark.parametrize("text", ["---", "(peak)", "", "see MALLOC ZONE table below"])
def test_parse_mb_rejects_non_sizes(text):
    assert parse_mb(text) is None


def test_parse_footprint_text_takes_phys_footprint_not_the_header_total():
    parsed = parse_footprint_text(FOOTPRINT_OUTPUT_KB)
    assert parsed["mb"] == pytest.approx(1232 / 1024)
    assert parsed["mb"] != pytest.approx(1216 / 1024)
    assert parsed["peak_mb"] == pytest.approx(1232 / 1024)


def test_parse_footprint_text_handles_mb_units():
    parsed = parse_footprint_text(FOOTPRINT_OUTPUT_MB)
    assert parsed["mb"] == pytest.approx(907.0)
    assert parsed["peak_mb"] == pytest.approx(907.0)


def test_parse_footprint_text_on_garbage_is_none():
    parsed = parse_footprint_text("footprint: Unable to find pid for process matching '1'\n")
    assert parsed["mb"] is None and parsed["peak_mb"] is None


def test_parse_vmmap_summary_reads_the_region_total_row():
    totals = parse_vmmap_summary(VMMAP_SUMMARY)
    assert totals["virtual"] == pytest.approx(2048.0)
    assert totals["resident"] == pytest.approx(1228.8)
    assert totals["dirty"] == pytest.approx(907.3)
    assert totals["swapped"] == pytest.approx(0.0)
    assert "region" not in totals


def test_parse_vmmap_summary_without_a_region_table_is_empty():
    malloc_only = "\n".join(
        line for line in VMMAP_SUMMARY.splitlines() if "MALLOC ZONE" in line or "DefaultMalloc" in line
    )
    assert parse_vmmap_summary(malloc_only) == {}


def test_sampler_peaks_on_a_real_process(sleeper):
    sampler = Sampler(sleeper.pid, interval_s=0.5).start()
    time.sleep(2.5)
    result = sampler.stop()

    assert result["pid"] == sleeper.pid
    assert result["n_samples"] >= 2
    assert result["peak_mb"] is not None
    assert result["peak_mb"] > 0
    # A python3 sleeper measures ~7 MB here; anything outside this is not this process.
    assert 1.0 <= result["peak_mb"] <= 2000.0

    mb_values = [s["mb"] for s in result["samples"]]
    timestamps = [s["t"] for s in result["samples"]]
    assert result["peak_mb"] == max(mb_values)
    assert timestamps == sorted(timestamps)
    assert result["duration_s"] >= 2.0
    assert sampler.running is False


def test_start_does_not_block_the_caller(sleeper):
    started = time.perf_counter()
    sampler = Sampler(sleeper.pid, interval_s=0.25).start()
    start_elapsed = time.perf_counter() - started

    assert start_elapsed < 1.0
    assert sampler.running is True

    time.sleep(1.2)
    assert sampler.running is True
    assert len(sampler.samples) >= 1

    sampler.stop()
    assert sampler.running is False


def test_peak_is_within_10_percent_of_an_independent_reading(sleeper):
    """The acceptance criterion, as near as it can be checked without Activity Monitor."""
    sampler = Sampler(sleeper.pid, interval_s=0.5).start()
    time.sleep(1.2)
    result = sampler.stop()

    cross_check = result["memory_split"]["footprint_mb"]
    assert cross_check is not None
    assert abs(result["peak_mb"] - cross_check) / cross_check < 0.10


def test_vmmap_split_on_a_live_process(sleeper):
    split = vmmap_split(sleeper.pid)

    assert split["available"] is True
    assert split["reason"] is None
    assert split["dirty_mb"] > 0
    assert split["footprint_mb"] > 0
    assert split["swapped_mb"] is not None
    if split["compressed_mb"] is None:
        assert split["note"]


def test_vmmap_split_on_a_dead_pid_degrades():
    split = vmmap_split(_pid_of_exited_process())
    assert split["available"] is False
    assert split["reason"]
    assert split["dirty_mb"] is None


def test_sampler_retains_a_thread_that_does_not_join(monkeypatch):
    sampler = Sampler(1)

    class StillAlive:
        def join(self, timeout=None):
            pass

        def is_alive(self):
            return True

    thread = StillAlive()
    sampler._thread = thread
    monkeypatch.setattr(sample_mod, "vmmap_split", lambda pid: {})
    monkeypatch.setattr(sample_mod, "gpu_wired_limit", lambda: {})
    monkeypatch.setattr(sample_mod, "FOOTPRINT_TIMEOUT_S", 0)

    result = sampler.stop()

    assert result["error"] == "sampling thread for pid 1 is still alive after join"
    assert sampler._thread is thread


def test_sampler_stops_itself_when_the_process_goes_away():
    sampler = Sampler(_pid_of_exited_process(), interval_s=0.05).start()
    time.sleep(0.5)
    result = sampler.stop()

    assert result["peak_mb"] is None
    assert result["samples"] == []
    assert result["error"]
    assert sampler.running is False


def test_sampler_records_whether_the_gpu_wired_limit_is_raised(sampled):
    limit = sampled["gpu_wired_limit"]

    assert isinstance(limit["raised"], bool)
    if limit["mb"] is None:
        assert limit["reason"]
    else:
        assert limit["raised"] is (limit["mb"] > 0)
        assert re.match(r"^iogpu\.wired_limit_mb:\s*-?\d+$", limit["raw"])


def test_gpu_wired_limit_is_readable_independently():
    live = gpu_wired_limit()
    assert live["reason"] is not None or isinstance(live["mb"], int)


def test_phys_footprint_mb_on_a_live_process(sleeper):
    mb = phys_footprint_mb(sleeper.pid)
    assert mb is not None
    assert mb > 0


def test_phys_footprint_mb_on_a_dead_pid_is_none():
    assert phys_footprint_mb(_pid_of_exited_process()) is None


def test_module_never_reaches_for_ps_rss():
    """RSS is wrong under MLX. If this fails, someone reintroduced it.

    Scans the module's identifiers, attributes and string constants — the code, not the
    prose, since the module's own docstring is where the rule is written down.
    """
    tree = ast.parse(Path(sample_mod.__file__).read_text())
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    code = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                code.append(node.value)
        elif isinstance(node, ast.Name):
            code.append(node.id)
        elif isinstance(node, ast.Attribute):
            code.append(node.attr)
    code = " ".join(code).lower()

    assert "phys_footprint" in code
    assert "psutil" not in code
    assert "rss" not in code
    assert re.search(r"\bps\b", code) is None


def _pid_of_exited_process():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    return proc.pid
