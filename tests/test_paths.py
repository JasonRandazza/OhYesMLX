"""Checks for the one writable root (plan 045-02a, AC-1).

In this checkout every path AC-1 moves resolves byte-identically to the path it had before,
so no harness run, canary or published table moves. An installed package has no writable
tree beside it, so the baseline, the runtime logs, the Osaurus backup and the fetch ledger
all land under the app's Application Support directory, created 0700. No test touches this
Mac's real home: a scratch HOME is one of the inputs.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import ohyesmlx
from ohyesmlx import engines, fetch, osaurus_settings, quickbench, runtimes

REPO = Path(ohyesmlx.__file__).resolve().parents[1]


# --- the checkout keeps today's paths ---------------------------------------------------------


def test_the_checkout_writable_root_is_the_repository_root():
    assert ohyesmlx._is_checkout(), "this suite is expected to run from a checkout"
    assert ohyesmlx.writable_root() == REPO


def test_the_checkout_baseline_and_logs_paths_are_byte_identical_to_today():
    assert osaurus_settings.BASELINE_PATH == (
        REPO / "config" / "osaurus-settings-baseline.json"
    )
    assert runtimes.LOGS_DIR == REPO / "results" / "logs"
    # The pre-change derivations, written out: the two paths the harness has always used.
    assert str(osaurus_settings.BASELINE_PATH) == os.path.join(
        str(REPO), "config", "osaurus-settings-baseline.json"
    )
    assert str(runtimes.LOGS_DIR) == os.path.join(str(REPO), "results", "logs")


def test_every_application_support_path_derives_from_the_one_helper():
    assert ohyesmlx.app_support_dir() == Path.home() / "Library" / "Application Support" / "OhYesMLX"
    assert Path(engines.DEFAULT_ENGINES_DIR) == ohyesmlx.app_support_dir() / "engines"
    assert Path(engines.DEFAULT_INSTALL_LOG) == ohyesmlx.app_support_dir() / "install-log.jsonl"
    assert Path(engines.LAB_PATHS_FILE) == ohyesmlx.app_support_dir() / "lab-paths.json"
    assert Path(fetch._APP_SUPPORT) == ohyesmlx.app_support_dir()
    assert Path(quickbench.DEFAULT_RESULTS_DIR) == ohyesmlx.app_support_dir() / "quickbench"
    assert Path(quickbench.DEFAULT_BACKUP_DIR) == (
        ohyesmlx.app_support_dir() / "quickbench" / "osaurus-backup"
    )


def test_engines_takes_a_scratch_home(tmp_path):
    home = str(tmp_path)
    expected = ohyesmlx.app_support_dir(home)
    assert engines._engines_dir(home) == str(expected / "engines")
    assert engines._lab_paths_file(home) == str(expected / "lab-paths.json")


# --- an installed package writes only under Application Support --------------------------------


@pytest.fixture
def installed_package(monkeypatch, tmp_path):
    """A read-only package tree with no `.git`: what an installed app looks like on disk.

    `__file__` is pointed at a copy under *tmp_path*, so `_repo_root` and the `.git` probe
    both answer about that tree. The tree is made read-only afterwards, so a write that
    still tried to land beside the package would fail loudly rather than pass unseen.
    """
    home = tmp_path / "home"
    tree = tmp_path / "site-packages"
    package = tree / "ohyesmlx"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (tree / "config").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(ohyesmlx, "__file__", str(package / "__init__.py"))
    assert not ohyesmlx._is_checkout()
    (tree / "config").chmod(0o500)
    tree.chmod(0o500)
    try:
        yield tree
    finally:
        tree.chmod(0o755)
        (tree / "config").chmod(0o755)


def test_without_a_checkout_the_writable_root_is_application_support(installed_package):
    assert ohyesmlx.writable_root() == ohyesmlx.app_support_dir()
    assert ohyesmlx.writable_root() == (
        Path(os.environ["HOME"]) / "Library" / "Application Support" / "OhYesMLX"
    )
    assert not str(ohyesmlx.writable_root()).startswith(str(installed_package))


def test_a_pin_round_trip_without_a_checkout_writes_only_under_application_support(
    installed_package,
):
    app_support = ohyesmlx.writable_root()
    config_dir = Path(os.environ["HOME"]) / ".osaurus" / "config"
    config_dir.mkdir(parents=True)
    for name in osaurus_settings.PIN_FILES:
        (config_dir / name).write_text(json.dumps({"cache": {}}), encoding="utf-8")
    backup_dir = app_support / "quickbench" / "osaurus-backup"
    baseline = app_support / "config" / "osaurus-settings-baseline.json"

    osaurus_settings.pin(config_dir, backup_dir=backup_dir, baseline_path=baseline)
    assert baseline.exists(), "the baseline did not follow the writable root"
    assert baseline.is_relative_to(app_support)
    assert osaurus_settings.restore(
        config_dir, backup_dir=backup_dir, baseline_path=baseline
    )
    assert list((installed_package / "config").iterdir()) == [], (
        "the pin wrote beside the read-only package tree"
    )


def test_an_engine_spawn_log_without_a_checkout_lands_under_application_support(
    installed_package, monkeypatch
):
    app_support = ohyesmlx.writable_root()
    # What LOGS_DIR would be had the module been imported in this state.
    monkeypatch.setattr(runtimes, "LOGS_DIR", app_support / "results" / "logs")

    class FakePopen:
        def __init__(self, *args, **kwargs):
            self.pid = 4321

    monkeypatch.setattr(runtimes.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runtimes, "_engine_env", lambda: {})

    log_path = runtimes._log_path("probe")
    assert runtimes._spawn(("/bin/echo",), log_path) == 4321

    assert log_path.is_file()
    assert log_path.parent == app_support / "results" / "logs"
    assert not (installed_package / "results").exists()


# --- ensure_app_support: 0700, new or pre-existing --------------------------------------------


def test_ensure_app_support_creates_the_directory_0700(tmp_path):
    path = ohyesmlx.ensure_app_support(tmp_path / "home")

    assert path == tmp_path / "home" / "Library" / "Application Support" / "OhYesMLX"
    assert path.is_dir()
    assert stat.S_IMODE(path.stat().st_mode) == 0o700


def test_ensure_app_support_tightens_a_pre_existing_0755_directory(tmp_path):
    path = tmp_path / "home" / "Library" / "Application Support" / "OhYesMLX"
    path.mkdir(parents=True)
    path.chmod(0o755)

    assert ohyesmlx.ensure_app_support(tmp_path / "home") == path
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
