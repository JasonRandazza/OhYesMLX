"""Plan 055-02, AC-3: ``Hardware.disk_volume`` names the volume the disk figure measures.

The probe is the cache path's nearest existing ancestor, walked up to the first mount point,
so the label the screens show cannot name a different volume from the number beside it. Every
check drives the side effects the way ``test_hardware`` does -- a fake ``run`` for the chip
commands and a fake ``disk_usage`` -- and ``os.path.ismount`` is replaced, so no answer here
depends on the disks this Mac happens to have.
"""

from __future__ import annotations

import os
from collections import namedtuple

from ohyesmlx import hardware
from ohyesmlx.hardware import IOREG, SW_VERS, SYSCTL, scan

Usage = namedtuple("Usage", "total used free")

IOREG_AGX = (IOREG, "-rc", "AGXAccelerator", "-d1")

M2_MAX_64 = {
    (SYSCTL, "-n", "machdep.cpu.brand_string"): "Apple M2 Max",
    (SYSCTL, "-n", "hw.memsize"): "68719476736",
    (SYSCTL, "-n", "hw.ncpu"): "12",
    (SW_VERS, "-productVersion"): "15.4",
    IOREG_AGX: "",
}


def fake_run(answers):
    def run(argv):
        return answers[tuple(argv)]

    return run


def no_volumes():
    return []


def one_usage(free, total=994_000_000_000):
    """A ``disk_usage`` answering every path with one volume's numbers."""

    def disk_usage(path):
        return Usage(total=total, used=0, free=free)

    return disk_usage


def mount_only_at(monkeypatch, mount):
    """Make *mount* the one mount point ``os.path.ismount`` reports."""
    monkeypatch.setattr(os.path, "ismount", lambda path: path == mount)


def test_scan_reports_the_volume_the_cache_lives_on(tmp_path, monkeypatch):
    mount = os.path.realpath(tmp_path)
    mount_only_at(monkeypatch, mount)
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=one_usage(987_654_321),
        volume_paths=no_volumes,
        cache_dir=str(tmp_path / "hub"),  # not created: the nearest existing ancestor is asked
    )
    assert hw.disk_volume == mount


def test_the_volume_is_found_by_walking_up_to_the_first_mount_point(tmp_path, monkeypatch):
    """The nearest existing ancestor need not be the mount: the lookup keeps walking up."""
    mount = os.path.realpath(tmp_path)
    inside = tmp_path / "nested"
    inside.mkdir()
    mount_only_at(monkeypatch, mount)
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=one_usage(987_654_321),
        volume_paths=no_volumes,
        cache_dir=str(inside / "hub"),
    )
    assert hw.disk_volume == mount


def test_the_free_figure_and_the_volume_name_come_from_the_same_probe(tmp_path, monkeypatch):
    """AC-3: the label names the volume ``disk_free_bytes`` was measured on."""
    mount = os.path.realpath(tmp_path)
    mount_only_at(monkeypatch, mount)
    asked = []

    def disk_usage(path):
        asked.append(path)
        return Usage(total=994_000_000_000, used=0, free=987_654_321)

    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=disk_usage,
        volume_paths=no_volumes,
        cache_dir=str(tmp_path / "hub"),
    )
    assert asked == [mount], "one probe must answer both the free figure and the volume"
    assert hw.disk_free_bytes == 987_654_321
    assert hw.disk_volume == mount


def test_the_startup_disk_maps_to_slash(tmp_path, monkeypatch):
    mount_only_at(monkeypatch, "/")
    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=one_usage(123_456_789_012),
        volume_paths=no_volumes,
        cache_dir="/",
    )
    assert hw.disk_volume == "/"
    assert hardware._volume_mount_point("/", lambda path: path == "/") == "/"


def test_a_failed_disk_probe_reports_no_volume_rather_than_a_guess():
    """The ``except OSError`` path: free and total are 0, and the volume is null, never "/"."""

    def disk_usage(path):
        raise OSError("the volume cannot be read")

    hw = scan(
        run=fake_run(M2_MAX_64),
        disk_usage=disk_usage,
        volume_paths=no_volumes,
        cache_dir="/",
    )
    assert hw.disk_free_bytes == 0
    assert hw.disk_total_bytes == 0
    assert hw.disk_volume is None
