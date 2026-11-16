"""Suite-wide guards for the real filesystem.

Every test drives its side effects through an injected seam, so nothing here should ever
fire. The one fixture below is the exception that keeps it true: a call that forgot its
scratch ``lock_dir`` fails the test instead of creating ``download.lock`` under this Mac's
Application Support directory (045-02b AC-4). It lives at the suite root rather than in
``test_fetch.py`` because every module's tests can call ``fetch.download``/``fetch.evict``.
"""

from __future__ import annotations

import os

import pytest

from ohyesmlx import fetch, runtimes


@pytest.fixture(autouse=True)
def _no_real_lock_dir(monkeypatch):
    """AC-4: no test reaches the real lock directory, whatever module it is in.

    ``download`` and ``evict`` both take a ``lock_dir``; a test that calls either passes a
    scratch directory. The comparison is by ``os.path.realpath``, so a ``lock_dir`` spelled
    through a symlink or ``..`` to the real directory is caught too.
    """
    real = os.path.realpath(fetch.DEFAULT_LOCK_DIR)
    acquire = fetch._acquire_lock

    def guarded(path):
        assert os.path.realpath(os.path.dirname(str(path))) != real, (
            f"a test reached the real lock directory {fetch.DEFAULT_LOCK_DIR}"
        )
        return acquire(path)

    monkeypatch.setattr(fetch, "_acquire_lock", guarded)


@pytest.fixture(autouse=True)
def _fresh_own_identity(monkeypatch):
    """``runtimes._OWN_IDENTITY`` caches this process's identity; a test that fakes
    ``_process_identity`` must not leave its fake cached for the next test (05-09)."""
    monkeypatch.setattr(runtimes, "_OWN_IDENTITY", {})
