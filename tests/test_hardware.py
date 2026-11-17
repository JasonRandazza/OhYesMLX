"""Checks for ohyesmlx.hardware.

Every check drives ``scan`` through its side effects: ``run`` is a fake that maps the exact
argv this module issues to the literal text the real command returns, ``disk_usage`` answers
a literal ``.free`` per path, and ``volume_paths`` names the volumes to inspect. No
subprocess is started, no disk is read, and no expected value is computed from the code
under test.
"""

from __future__ import annotations

import os

import subprocess
from collections import namedtuple

from ohyesmlx.hardware import (
    IOREG,
    SW_VERS,
    SYSCTL,
    TOOL_TIMEOUT_S,
    _volume_paths,
    model_budget,
    scan,
)


def fake_run(answers):
    """A ``run`` that answers each argv from *answers*, keyed by the argv tuple."""

    def run(argv):
        return answers[tuple(argv)]

    return run


Usage = namedtuple("Usage", "total used free")


def fake_disk_usage(frees):
    """A ``disk_usage`` reporting ``frees[path]`` as ``.free``; an exception value raises it."""

    def disk_usage(path):
        free = frees[path]
        if isinstance(free, Exception):
            raise free
        return Usage(total=0, used=0, free=free)

    return disk_usage


def no_volumes():
    """A ``volume_paths`` that names no volume, so a chip check sees no disk."""
    return []


def scan_hw(answers):
    """``scan`` driven by the chip answers alone, with no volume inspected."""
    return scan(
        run=fake_run(answers),
        disk_usage=fake_disk_usage({"/": 0}),
        volume_paths=no_volumes,
        cache_dir="/",
    )


IOREG_AGX = (IOREG, "-rc", "AGXAccelerator", "-d1")

AGX_M2_MAX_30 = """\
+-o AGXAcceleratorG14X  <class AGXAcceleratorG14X, id 0x10000046d, registered, matched, active, busy 0 (0 ms), retain 9>
    {
      "IOClass" = "AGXAcceleratorG14X"
      "IOMatchCategory" = "IOFramebuffer"
      "IOProviderClass" = "IOResource"
      "gpu-core-count" = 30
      "gpu-instance-count" = 1
      "name" = "AGXAccelerator"
    }
"""


M2_MAX_64 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M2 Max",
    (SYSCTL, "-n", "hw.memsize"): "68719476736",
    (SYSCTL, "-n", "hw.ncpu"): "12",
    (SW_VERS, "-productVersion"): "15.4",
    IOREG_AGX: AGX_M2_MAX_30,
}


def test_m2_max_64_gib_is_a_supported_max_chip():
    hw = scan_hw(M2_MAX_64)
    assert hw.chip == "Apple M2 Max"
    assert hw.family == "M2"
    assert hw.tier == "max"
    assert hw.ram_bytes == 68719476736
    assert hw.cpu_cores == 12
    assert hw.macos == "15.4"
    assert hw.supported is True
    assert hw.unsupported_reason is None
    assert hw.gpu_cores == 30
    assert hw.disk_free_bytes == 0
    assert hw.volumes == []
    assert hw.model_budget_bytes == 49392123904


def test_gpu_cores_is_the_ioreg_gpu_core_count():
    hw = scan_hw({**M2_MAX_64, IOREG_AGX: AGX_M2_MAX_30})
    assert hw.gpu_cores == 30


def test_gpu_cores_is_none_when_ioreg_omits_the_key_or_says_nothing():
    without_key = "\n".join(
        line for line in AGX_M2_MAX_30.splitlines() if "gpu-core-count" not in line
    )
    assert scan_hw({**M2_MAX_64, IOREG_AGX: without_key}).gpu_cores is None
    assert scan_hw({**M2_MAX_64, IOREG_AGX: ""}).gpu_cores is None


def test_gpu_cores_is_none_when_ioreg_fails_and_the_other_fields_survive():
    errors = [subprocess.CalledProcessError(1, list(IOREG_AGX)), OSError("ioreg not found")]
    for error in errors:

        def failing_run(argv, error=error):
            if tuple(argv) == IOREG_AGX:
                raise error
            return M2_MAX_64[tuple(argv)]

        hw = scan(run=failing_run, volume_paths=no_volumes)
        assert hw.gpu_cores is None
        assert hw.chip == "Apple M2 Max"
        assert hw.cpu_cores == 12
        assert hw.ram_bytes == 68719476736
        assert hw.model_budget_bytes == 49392123904


M1_16 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M1",
    (SYSCTL, "-n", "hw.memsize"): "17179869184",
    (SYSCTL, "-n", "hw.ncpu"): "8",
    (SW_VERS, "-productVersion"): "15.4",
    IOREG_AGX: "",
}


def test_m1_base_is_base_tier():
    hw = scan_hw(M1_16)
    assert hw.chip == "Apple M1"
    assert hw.family == "M1"
    assert hw.tier == "base"
    assert hw.ram_bytes == 17179869184
    assert hw.cpu_cores == 8
    assert hw.supported is True
    assert hw.unsupported_reason is None


M3_PRO_36 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M3 Pro",
    (SYSCTL, "-n", "hw.memsize"): "38654705664",
    (SYSCTL, "-n", "hw.ncpu"): "12",
    (SW_VERS, "-productVersion"): "14.7.1",
    IOREG_AGX: "",
}


def test_m3_pro_is_pro_tier():
    hw = scan_hw(M3_PRO_36)
    assert hw.chip == "Apple M3 Pro"
    assert hw.family == "M3"
    assert hw.tier == "pro"
    assert hw.ram_bytes == 38654705664
    assert hw.macos == "14.7.1"
    assert hw.supported is True


M4_ULTRA_128 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M4 Ultra",
    (SYSCTL, "-n", "hw.memsize"): "137438953472",
    (SYSCTL, "-n", "hw.ncpu"): "28",
    (SW_VERS, "-productVersion"): "15.4",
    IOREG_AGX: "",
}


def test_m4_ultra_is_ultra_tier():
    hw = scan_hw(M4_ULTRA_128)
    assert hw.chip == "Apple M4 Ultra"
    assert hw.family == "M4"
    assert hw.tier == "ultra"
    assert hw.ram_bytes == 137438953472
    assert hw.supported is True


INTEL_16 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz",
    (SYSCTL, "-n", "hw.memsize"): "17179869184",
    (SYSCTL, "-n", "hw.ncpu"): "12",
    (SW_VERS, "-productVersion"): "10.15.7",
    IOREG_AGX: "",
}


def test_intel_is_unsupported_and_says_why():
    hw = scan_hw(INTEL_16)
    assert hw.chip == "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz"
    assert hw.ram_bytes == 17179869184
    assert hw.cpu_cores == 12
    assert hw.macos == "10.15.7"
    assert hw.supported is False
    assert hw.unsupported_reason == "this Mac is not Apple silicon"


M2_4 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M2",
    (SYSCTL, "-n", "hw.memsize"): "4294967296",
    (SYSCTL, "-n", "hw.ncpu"): "8",
    (SW_VERS, "-productVersion"): "13.6.9",
    IOREG_AGX: "",
}


def test_apple_silicon_under_8_gib_is_unsupported():
    hw = scan_hw(M2_4)
    assert hw.chip == "Apple M2"
    assert hw.family == "M2"
    assert hw.tier == "base"
    assert hw.ram_bytes == 4294967296
    assert hw.cpu_cores == 8
    assert hw.supported is False
    assert hw.unsupported_reason == "this Mac has less than 8 GiB of unified memory"


M7_32 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M7",
    (SYSCTL, "-n", "hw.memsize"): "34359738368",
    (SYSCTL, "-n", "hw.ncpu"): "10",
    (SW_VERS, "-productVersion"): "27.0",
    IOREG_AGX: "",
}


def test_an_unknown_future_apple_chip_stays_supported_at_base_tier():
    hw = scan_hw(M7_32)
    assert hw.chip == "Apple M7"
    assert hw.family == "M7"
    assert hw.tier == "base"
    assert hw.ram_bytes == 34359738368
    assert hw.cpu_cores == 10
    assert hw.macos == "27.0"
    assert hw.supported is True
    assert hw.unsupported_reason is None


def test_disk_free_bytes_is_the_cache_volumes_free_space():
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=fake_disk_usage({"/": 123456789012}),
        volume_paths=lambda: ["/"],
        cache_dir="/",
    )
    assert hw.disk_free_bytes == 123456789012


def test_volumes_are_reported_in_volume_path_order():
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=fake_disk_usage({"/": 123456789012, "/Volumes/Ext": 987654321}),
        volume_paths=lambda: ["/", "/Volumes/Ext"],
        cache_dir="/",
    )
    assert hw.volumes == [
        {"path": "/", "free_bytes": 123456789012},
        {"path": "/Volumes/Ext", "free_bytes": 987654321},
    ]
    assert hw.disk_free_bytes == 123456789012


def test_an_unreadable_volume_is_skipped_and_the_rest_remain():
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=fake_disk_usage(
            {
                "/": 123456789012,
                "/Volumes/Gone": OSError("no such volume"),
                "/Volumes/Ext": 987654321,
            }
        ),
        volume_paths=lambda: ["/", "/Volumes/Gone", "/Volumes/Ext"],
        cache_dir="/",
    )
    assert hw.volumes == [
        {"path": "/", "free_bytes": 123456789012},
        {"path": "/Volumes/Ext", "free_bytes": 987654321},
    ]
    assert hw.disk_free_bytes == 123456789012


def test_an_unreadable_root_reports_zero_free_and_leaves_the_other_volumes():
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=fake_disk_usage(
            {"/": OSError("no such volume"), "/Volumes/Ext": 987654321}
        ),
        volume_paths=lambda: ["/", "/Volumes/Ext"],
        cache_dir="/",
    )
    assert hw.disk_free_bytes == 0
    assert hw.volumes == [{"path": "/Volumes/Ext", "free_bytes": 987654321}]


def test_disk_free_bytes_follows_the_cache_not_the_root_volume(tmp_path):
    cache_volume = os.path.realpath(tmp_path)
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=fake_disk_usage({"/": 123456789012, cache_volume: 987654321}),
        volume_paths=lambda: ["/"],
        cache_dir=str(tmp_path / "hub"),  # not created yet: the nearest existing parent is asked
    )
    assert hw.disk_free_bytes == 987654321


def test_model_budget_takes_two_thirds_of_ram_under_36_gib_less_two_gib():
    assert model_budget(17179869184) == 9305762474
    assert model_budget(8589934592) == 3579139413


def test_model_budget_takes_three_quarters_of_ram_from_36_gib_less_two_gib():
    assert model_budget(68719476736) == 49392123904


def test_scan_reports_the_model_budget_for_an_m2_max_with_64_gib():
    hw = scan_hw(M2_MAX_64)
    assert hw.model_budget_bytes == 49392123904


def test_volume_paths_lists_root_then_real_volumes_skipping_the_startup_alias(tmp_path):
    (tmp_path / "Ext").mkdir()
    (tmp_path / "Other").mkdir()
    (tmp_path / "not-a-volume").write_text("")
    (tmp_path / "Macintosh HD").symlink_to("/")
    assert _volume_paths(root=str(tmp_path)) == [
        "/",
        str(tmp_path / "Ext"),
        str(tmp_path / "Other"),
    ]


def test_volume_paths_tolerates_a_missing_volumes_root(tmp_path):
    assert _volume_paths(root=str(tmp_path / "missing")) == ["/"]


def test_volume_paths_skips_hidden_and_recovery_system_volumes(tmp_path):
    (tmp_path / ".timemachine").mkdir()
    (tmp_path / "Recovery").mkdir()
    (tmp_path / "Ext").mkdir()
    assert _volume_paths(root=str(tmp_path)) == ["/", str(tmp_path / "Ext")]


# --- AC-5: absolute tools and a bounded scan --------------------------------------------------


def test_every_tool_is_named_by_absolute_path():
    assert SYSCTL == "/usr/sbin/sysctl"
    assert SW_VERS == "/usr/bin/sw_vers"
    assert IOREG == "/usr/sbin/ioreg"


def test_the_scan_calls_every_tool_with_the_ten_second_timeout(monkeypatch):
    from ohyesmlx import hardware

    calls = []

    class Completed:
        stdout = "x"

    def fake(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return Completed()

    monkeypatch.setattr(hardware.subprocess, "run", fake)

    assert hardware._run([SYSCTL, "-n", "hw.ncpu"]) == "x"
    assert TOOL_TIMEOUT_S == 10
    assert len(calls) == 1
    assert calls[0][0] == (SYSCTL, "-n", "hw.ncpu")
    assert calls[0][1]["timeout"] == TOOL_TIMEOUT_S


def test_a_hung_tool_raises_instead_of_hanging_the_scan():
    def hung(argv):
        raise subprocess.TimeoutExpired(argv, TOOL_TIMEOUT_S)

    try:
        scan(run=hung, volume_paths=no_volumes)
    except subprocess.TimeoutExpired:
        pass
    else:
        raise AssertionError("a hung tool was reported as a scan")
