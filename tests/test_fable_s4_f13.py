"""S4-F13: the download lock can be stolen between `O_EXCL` create and the pid write.

`fetch._acquire_lock` (fetch.py:366-390) creates the lock with `O_CREAT|O_EXCL` at :373 and
writes this process's pid only afterwards, at :387-388. A second process that arrives in that
window hits `FileExistsError` at :374, reads an empty file, folds the `ValueError` into
`pid = None` at :378-379, skips the liveness check at :380 because `pid is None`, removes the
live owner's lock at :383 and creates its own. Both callers then hold "the" lock and write one
`.incomplete` and one `fetched.json` concurrently.

This is not the accepted check-then-remove race (two callers both finding a *dead* owner:
dossier-S1.md:269, threat-model §9). Here the owner is alive; only its pid is not written yet.

The test is the finding's own idea: the lock a live owner has created but not yet written is
held, so `_acquire_lock` must answer False.
"""

from __future__ import annotations

from ohyesmlx import fetch


def test_an_empty_lock_naming_no_pid_is_held_not_reclaimed(tmp_path):
    """A lock file that exists with no pid yet is the mid-creation window of a live owner."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True)
    lock = lock_dir / fetch.LOCK_NAME
    lock.write_text("", encoding="utf-8")

    acquired = fetch._acquire_lock(str(lock))

    assert acquired is False, (
        "the empty lock at the create/write window was reclaimed and re-created: a second "
        "process now holds the lock a live first process is about to write its pid to, so "
        "two downloads run at once"
    )
    assert lock.exists(), "a held lock's file must not be removed"
