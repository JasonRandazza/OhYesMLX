"""Fable 5.2 S1-F8: evict deletes `refs/main` although another tool rewrote it.

`_download` records `ref_path` in the ledger only when it creates the file
(fetch.py:871-874). `evict` then removes every `created_links` entry with a bare
`os.remove` and no content check (fetch.py:1250-1258), while blobs get a "still
referenced" test. So a `refs/main` that `huggingface-cli download` has since rewritten
to a newer commit is still deleted, and the user's own offline copy stops resolving
by name.

The download runs against the fake transport from `test_fetch` (same directory, not a
package) into a scratch cache; no socket is opened.
"""

from __future__ import annotations

import os

from test_fetch import CONFIG, REV, SHA, TWO_FILES, WEIGHTS, Harness, make_model, serve

FOREIGN = "b" * 40


def test_evict_keeps_a_refs_main_that_no_longer_holds_the_ledger_revision(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)
    assert harness.download() is True
    assert harness.ref.read_text().strip() == REV

    # Another tool (e.g. `huggingface-cli download org/name`) rewrites the ref it finds
    # and adds its own snapshot under the commit that ref names.
    harness.ref.write_text(FOREIGN + "\n", encoding="utf-8")
    foreign_snapshot = harness.repo_dir / "snapshots" / FOREIGN
    foreign_snapshot.mkdir(parents=True)
    os.symlink(
        os.path.relpath(harness.blobs / SHA, foreign_snapshot),
        foreign_snapshot / "weights.safetensors",
    )

    assert harness.evict() is True

    assert (harness.blobs / SHA).exists(), "the shared blob is kept; the scan found the other snapshot"
    assert foreign_snapshot.is_dir(), "the foreign snapshot is left alone"
    assert harness.ref.exists(), (
        "evict removed refs/main, whose content is no longer what this app wrote"
    )
    assert harness.ref.read_text() == FOREIGN + "\n"
