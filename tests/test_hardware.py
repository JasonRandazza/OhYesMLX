"""Checks for ohyesmlx.hardware.

Every check drives ``scan`` through its one side effect: ``run`` is a fake that maps the
exact argv this module issues to the literal text the real command returns. No subprocess
is started, and no expected value is computed from the code under test.
"""

from __future__ import annotations

from ohyesmlx.hardware import scan


def fake_run(answers):
    """A ``run`` that answers each argv from *answers*, keyed by the argv tuple."""

    def run(argv):
        return answers[tuple(argv)]

    return run


M2_MAX_64 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M2 Max",
    ("sysctl", "-n", "hw.memsize"): "68719476736",
    ("sysctl", "-n", "hw.ncpu"): "12",
    ("sw_vers", "-productVersion"): "15.4",
}


def test_m2_max_64_gib_is_a_supported_max_chip():
    hw = scan(run=fake_run(M2_MAX_64))
    assert hw.chip == "Apple M2 Max"
    assert hw.family == "M2"
    assert hw.tier == "max"
    assert hw.ram_bytes == 68719476736
    assert hw.cpu_cores == 12
    assert hw.macos == "15.4"
    assert hw.supported is True
    assert hw.unsupported_reason is None
    assert hw.gpu_cores is None
    assert hw.disk_free_bytes == 0
    assert hw.volumes == []
    assert hw.model_budget_bytes == 0


M1_16 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M1",
    ("sysctl", "-n", "hw.memsize"): "17179869184",
    ("sysctl", "-n", "hw.ncpu"): "8",
    ("sw_vers", "-productVersion"): "15.4",
}


def test_m1_base_is_base_tier():
    hw = scan(run=fake_run(M1_16))
    assert hw.chip == "Apple M1"
    assert hw.family == "M1"
    assert hw.tier == "base"
    assert hw.ram_bytes == 17179869184
    assert hw.cpu_cores == 8
    assert hw.supported is True
    assert hw.unsupported_reason is None


M3_PRO_36 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M3 Pro",
    ("sysctl", "-n", "hw.memsize"): "38654705664",
    ("sysctl", "-n", "hw.ncpu"): "12",
    ("sw_vers", "-productVersion"): "14.7.1",
}


def test_m3_pro_is_pro_tier():
    hw = scan(run=fake_run(M3_PRO_36))
    assert hw.chip == "Apple M3 Pro"
    assert hw.family == "M3"
    assert hw.tier == "pro"
    assert hw.ram_bytes == 38654705664
    assert hw.macos == "14.7.1"
    assert hw.supported is True


M4_ULTRA_128 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M4 Ultra",
    ("sysctl", "-n", "hw.memsize"): "137438953472",
    ("sysctl", "-n", "hw.ncpu"): "28",
    ("sw_vers", "-productVersion"): "15.4",
}


def test_m4_ultra_is_ultra_tier():
    hw = scan(run=fake_run(M4_ULTRA_128))
    assert hw.chip == "Apple M4 Ultra"
    assert hw.family == "M4"
    assert hw.tier == "ultra"
    assert hw.ram_bytes == 137438953472
    assert hw.supported is True


INTEL_16 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz",
    ("sysctl", "-n", "hw.memsize"): "17179869184",
    ("sysctl", "-n", "hw.ncpu"): "12",
    ("sw_vers", "-productVersion"): "10.15.7",
}


def test_intel_is_unsupported_and_says_why():
    hw = scan(run=fake_run(INTEL_16))
    assert hw.chip == "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz"
    assert hw.ram_bytes == 17179869184
    assert hw.cpu_cores == 12
    assert hw.macos == "10.15.7"
    assert hw.supported is False
    assert hw.unsupported_reason == "this Mac is not Apple silicon"


M2_4 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M2",
    ("sysctl", "-n", "hw.memsize"): "4294967296",
    ("sysctl", "-n", "hw.ncpu"): "8",
    ("sw_vers", "-productVersion"): "13.6.9",
}


def test_apple_silicon_under_8_gib_is_unsupported():
    hw = scan(run=fake_run(M2_4))
    assert hw.chip == "Apple M2"
    assert hw.family == "M2"
    assert hw.tier == "base"
    assert hw.ram_bytes == 4294967296
    assert hw.cpu_cores == 8
    assert hw.supported is False
    assert hw.unsupported_reason == "this Mac has less than 8 GiB of unified memory"


M7_32 = {
    ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M7",
    ("sysctl", "-n", "hw.memsize"): "34359738368",
    ("sysctl", "-n", "hw.ncpu"): "10",
    ("sw_vers", "-productVersion"): "27.0",
}


def test_an_unknown_future_apple_chip_stays_supported_at_base_tier():
    hw = scan(run=fake_run(M7_32))
    assert hw.chip == "Apple M7"
    assert hw.family == "M7"
    assert hw.tier == "base"
    assert hw.ram_bytes == 34359738368
    assert hw.cpu_cores == 10
    assert hw.macos == "27.0"
    assert hw.supported is True
    assert hw.unsupported_reason is None
