"""Fable 5.2 S6-F6: the SBOM can name a commit that does not hold the shipped code.

``scripts/build_app.sh:68`` copies the *working tree* with
``ditto "$ROOT/ohyesmlx" "$SITE_PACKAGES/ohyesmlx"`` -- uncommitted edits and untracked
files included -- and nothing in the build ever asks ``git status``.  The SBOM step at
``:111`` then stamps ``git rev-parse HEAD`` (``scripts/make_sbom.py:94-104``) and a source
digest taken from ``$ROOT/ohyesmlx/*.py`` at *SBOM time* (``make_sbom.py:107-113`` ->
``ohyesmlx/measure.py:436-440``).  So a release built from a dirty tree publishes "the git
commit it was built from" (``docs/release/gatekeeper.md:59``) for code that commit does not
contain, and an edit landing between the copy and the SBOM is hashed even though it did not
ship.  The digest also covers top-level ``*.py`` only, while ``ditto`` ships
``catalog.json``, ``engines-tested.json``, ``longtext.md`` and ``constraints/`` too.

Each test builds a throwaway release repo -- this script, a copy of ``ohyesmlx`` and a git
history -- so neither the real checkout nor a build is touched.  The assertions are written
so the finding's two accepted fix shapes both satisfy them: refusing to build on a dirty
worktree *or* recording ``git_dirty`` with no commit; hashing the copied tree (from the
bundled interpreter) *or* widening the digest's coverage.  Nothing here starts a server,
loads a model, downloads anything or signs a bundle.

Not tested here: the real ``scripts/build_app.sh`` ordering (the copy at :68 and SBOM at
:111 are only modelled), and whether a release build could actually be rolled while an
edit lands -- these tests establish that the code has no cleanliness check and that the
digest follows the repo, which is the mechanism the claim rests on.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SBOM_SCRIPT = REPO / "scripts" / "make_sbom.py"
PACKAGE = REPO / "ohyesmlx"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="the fixture needs git")

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments], check=True, capture_output=True, text=True
    )
    return completed.stdout


def _commit(repo: Path, message: str) -> None:
    _git(
        repo,
        "-c",
        "user.email=verifier@example.invalid",
        "-c",
        "user.name=Fable Verifier",
        "commit",
        "-q",
        "-m",
        message,
    )


def _fake_release(tmp_path: Path) -> Path:
    """A throwaway checkout shaped like the one ``build_app.sh`` runs in."""
    root = tmp_path / "release"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(SBOM_SCRIPT, scripts / "make_sbom.py")
    shutil.copytree(
        PACKAGE, root / "ohyesmlx", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _commit(root, "the release candidate")
    return root


def _run_sbom(root: Path, out: Path, package: Path | None = None) -> subprocess.CompletedProcess:
    """Run the SBOM step the way ``build_app.sh:111`` does, against the fake checkout.

    ``package`` is the tree that shipped: ``build_app.sh`` passes the copy it made inside the
    bundle with ``--package``, and the SBOM step must digest that tree rather than the checkout.
    """
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(root)
    command = [
        sys.executable,
        "-B",
        str(root / "scripts" / "make_sbom.py"),
        "--out",
        str(out),
        "--python",
        sys.executable,
        "--release-tag",
        "20261026",
        "--interpreter-url",
        "https://example.invalid/python.tar.gz",
        "--interpreter-sha256",
        "0" * 64,
        "--swift-version",
        "swift",
    ]
    if package is not None:
        command[5:5] = ["--package", str(package)]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=root,
        env=environment,
    )


def _tree_digest(package_dir: Path) -> str:
    """``ohyesmlx.measure._source_sha256``'s construction, applied to an arbitrary tree."""
    digest = hashlib.sha256()
    for path in sorted(package_dir.glob("*.py"), key=lambda item: item.name):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _document_digests(value) -> set[str]:
    """Every sha256-looking value in the document, wherever the field lives."""
    found: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            found |= _document_digests(item)
    elif isinstance(value, list):
        for item in value:
            found |= _document_digests(item)
    elif isinstance(value, str) and SHA256.match(value):
        found.add(value)
    return found


def test_a_clean_worktree_still_records_the_commit_it_copied(tmp_path):
    """Control: the assertion below is about dirt, not about never recording a commit."""
    root = _fake_release(tmp_path)
    head = _git(root, "rev-parse", "HEAD").strip()

    completed = _run_sbom(root, tmp_path / "sbom.json")

    assert completed.returncode == 0, completed.stderr
    document = json.loads((tmp_path / "sbom.json").read_text(encoding="utf-8"))
    assert document["app"]["git_commit"] == head, document["app"]


def test_a_dirty_worktree_does_not_stamp_a_bare_git_commit(tmp_path):
    """The finding's own test: a build from a dirty tree must not name HEAD unchallenged."""
    root = _fake_release(tmp_path)
    initialiser = root / "ohyesmlx" / "__init__.py"
    initialiser.write_text(
        initialiser.read_text(encoding="utf-8") + "\n# an edit that was never committed\n",
        encoding="utf-8",
    )
    assert _git(root, "status", "--porcelain", "--", "ohyesmlx").strip(), "the fixture is dirty"

    completed = _run_sbom(root, tmp_path / "sbom.json")
    if completed.returncode != 0:
        # Refusing to build a release from a dirty worktree is the other accepted answer.
        return
    app = json.loads((tmp_path / "sbom.json").read_text(encoding="utf-8"))["app"]
    assert app.get("git_commit") is None or app.get("git_dirty") is True, (
        "build_app.sh:68 copied an uncommitted edit into the bundle, and the SBOM still "
        f"stamped git_commit={app.get('git_commit')!r} with no git_dirty marker; that "
        "commit's tree is not the code the bundle holds (gatekeeper.md:59)"
    )


def test_the_digest_describes_the_tree_that_was_copied_not_the_repo_minutes_later(tmp_path):
    """An edit after ``build_app.sh:68``'s copy is hashed although it did not ship."""
    root = _fake_release(tmp_path)
    shipped = tmp_path / "shipped" / "ohyesmlx"
    shutil.copytree(
        root / "ohyesmlx", shipped, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    shipped_digest = _tree_digest(shipped)

    # The copy has been made; minutes later, before :111, an edit lands and is committed.
    report = root / "ohyesmlx" / "report.py"
    report.write_text(
        report.read_text(encoding="utf-8") + "\n# landed after the bundle copy\n", encoding="utf-8"
    )
    _git(root, "add", "ohyesmlx/report.py")
    _commit(root, "an edit that landed after the copy")

    completed = _run_sbom(root, tmp_path / "sbom.json", package=shipped)

    assert completed.returncode == 0, completed.stderr
    app = json.loads((tmp_path / "sbom.json").read_text(encoding="utf-8"))["app"]
    assert app["source_sha256"] == shipped_digest, (
        "the SBOM's source_sha256 hashes $ROOT/ohyesmlx at SBOM time, not the tree "
        "build_app.sh:68 copied into the bundle"
    )


def test_the_build_hands_the_copied_tree_to_the_sbom_step():
    """The corrected test above is only meaningful while the build passes the copy."""
    build = (REPO / "scripts" / "build_app.sh").read_text(encoding="utf-8")
    assert '--package "$SITE_PACKAGES/ohyesmlx"' in build, (
        "build_app.sh no longer tells make_sbom.py which tree shipped, so the SBOM digests "
        "the checkout rather than the bundle"
    )


def test_the_recorded_digests_cover_every_shipped_file(tmp_path):
    """A shipped data file can change without moving any digest the SBOM records."""
    root = _fake_release(tmp_path)
    catalog = root / "ohyesmlx" / "catalog.json"
    assert catalog.exists(), "catalog.json ships inside the package"

    first_run = _run_sbom(root, tmp_path / "first.json")
    assert first_run.returncode == 0, first_run.stderr
    first = _document_digests(json.loads((tmp_path / "first.json").read_text(encoding="utf-8")))

    catalog.write_text(catalog.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _git(root, "add", "ohyesmlx/catalog.json")
    _commit(root, "a catalog change that ships")

    second_run = _run_sbom(root, tmp_path / "second.json")
    assert second_run.returncode == 0, second_run.stderr
    second = _document_digests(json.loads((tmp_path / "second.json").read_text(encoding="utf-8")))

    assert first != second, (
        "catalog.json (which models are offered and downloaded) ships inside the bundle, "
        "but no digest in the SBOM changes when it changes: the digest covers top-level "
        "*.py only (measure.py:436-440), so engines-tested.json and longtext.md are "
        "unhashed too"
    )
