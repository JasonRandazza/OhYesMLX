"""Write the release SBOM: the bundled interpreter and every pinned engine dependency (P5-12).

Plan 05-06, AC-3; plan 05-13, AC-4. Stdlib only, and the one definition of what the release
records:

    python3 scripts/make_sbom.py --check          # the runnable check, no arguments needed
    python3 scripts/make_sbom.py --out dist/OhYesMLX-0.3.0-sbom.json \
        --python dist/OhYesMLX.app/Contents/Resources/python/bin/python3 \
        --package dist/OhYesMLX.app/Contents/Resources/python/lib/python3.14/site-packages/ohyesmlx \
        --release-tag 20261026 --interpreter-url URL --interpreter-sha256 SHA \
        --swift-version "swift-driver version: ..."

The package's own source sha256 is asked of ``ohyesmlx.measure._source_sha256()``, never copied:
that function is the record of what the measurement code was when the binary was built. It is
asked of the *bundled interpreter* over the *copied package* (S6-F6): the tree hashed is the tree
that shipped, not the checkout minutes later, and the same interpreter runs the import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "ohyesmlx-sbom/1"
REPO_ROOT = Path(__file__).resolve().parents[1]

# Run by ``--python``, not by the interpreter running this script. sys.argv[1] is the directory
# that holds the package (so the import resolves to the copy under test), sys.argv[2] the package
# itself. The source digest is the package's own ``_source_sha256``; the second digest covers
# every other shipped file, which that one deliberately does not (it is the harness's definition
# of the measurement code and is not widened here).
DIGESTS = """\
import hashlib, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from ohyesmlx.measure import _source_sha256

package = pathlib.Path(sys.argv[2])
data = hashlib.sha256()
for path in sorted(package.rglob("*")):
    if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
        continue
    if path.suffix == ".py":
        continue
    data.update(path.relative_to(package).as_posix().encode("utf-8"))
    data.update(b"\\0")
    data.update(hashlib.sha256(path.read_bytes()).digest())
print(json.dumps({"source_sha256": _source_sha256(), "data_files_sha256": data.hexdigest()}))
"""


def parse_requirements(text: str) -> list[dict]:
    """Every ``name==version`` pin and its hashes, from one hashed constraints file.

    The files are a full requirements file (threat model T-01): every pin carries a hash for
    every file PyPI listed, and any option line or unhashed pin is an error, not something to
    skip.
    """
    packages: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.endswith("\\"):
            line = line[:-1].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash="):
            if not packages:
                raise ValueError(f"a hash line before any pin: {raw.strip()!r}")
            digest = line.split("=", 1)[1]
            if not digest.startswith("sha256:"):
                raise ValueError(f"unexpected hash form: {raw.strip()!r}")
            packages[-1]["sha256"].append(digest.split(":", 1)[1])
            continue
        if line.startswith("-"):
            raise ValueError(f"unexpected option line: {raw.strip()!r}")
        name, separator, version = line.partition("==")
        if not separator or not name or not version:
            raise ValueError(f"pin without ==: {raw.strip()!r}")
        packages.append({"package": name, "version": version, "sha256": []})
    for entry in packages:
        if not entry["sha256"]:
            raise ValueError(f"{entry['package']}=={entry['version']} has no hash")
    return packages


def engine_dependencies(constraints_dir: Path) -> list[dict]:
    """One entry per committed constraints file, named ``<engine>-<version>.txt``."""
    entries = []
    for path in sorted(constraints_dir.glob("*.txt")):
        engine, _, version = path.stem.rpartition("-")
        if not engine or not version:
            raise ValueError(f"{path.name} is not <engine>-<version>.txt")
        entries.append(
            {
                "engine": engine,
                "engine_version": version,
                "file": path.name,
                "packages": parse_requirements(path.read_text(encoding="utf-8")),
            }
        )
    if not entries:
        raise ValueError(f"no constraints files under {constraints_dir}")
    return entries


def interpreter_version(python: Path) -> str:
    # -B: asking a bundled interpreter its own version must not write bytecode into the app.
    result = subprocess.run(
        [str(python), "-I", "-B", "-c", "import platform; print(platform.python_version())"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_commit(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def require_clean(repo: Path) -> None:
    """Refuse a release SBOM for a working tree that holds edits the commit does not.

    ``build_app.sh`` copies ``ohyesmlx`` with ``ditto``, untracked and modified files included, so
    a commit recorded beside a dirty copy is a claim about code the commit does not contain. The
    two shipped trees are the ones the copy covers (S6-F6).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--", "ohyesmlx", "app"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"make_sbom.py: cannot ask git whether {repo} is clean: {error}")
    if result.stdout.strip():
        listing = "\n".join(result.stdout.splitlines()[:10])
        raise SystemExit(
            "make_sbom.py: the worktree has uncommitted changes under ohyesmlx/ or app/, which "
            "the build copies into the bundle; a release SBOM would name a commit that does not "
            f"hold the shipped code. Commit or discard them, then build again:\n{listing}"
        )


def source_sha256() -> str:
    """The package's own source digest, asked of the one function that defines it."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from ohyesmlx.measure import _source_sha256

    return _source_sha256()


def bundle_digests(python: Path, package: Path) -> tuple[str, str]:
    """The shipped source and data digests, from the bundled interpreter over the copied tree.

    ``--python`` is the interpreter inside the app and ``--package`` the copy the build put into
    it, so both digests describe what shipped rather than the checkout the script runs in.
    """
    try:
        result = subprocess.run(
            [str(python), "-I", "-B", "-c", DIGESTS, str(package.parent), str(package)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"make_sbom.py: {python} could not digest {package}:\n{error.stderr.strip()}"
        )
    facts = json.loads(result.stdout)
    return facts["source_sha256"], facts["data_files_sha256"]


def build_document(
    *,
    app_version: str,
    commit: str | None,
    digest: str,
    data_digest: str,
    python_version: str,
    release_tag: str,
    interpreter_url: str,
    interpreter_sha256: str,
    swift_version: str,
    engines: list[dict],
) -> dict:
    return {
        "schema": SCHEMA,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "app": {
            "name": "OhYesMLX",
            "version": app_version,
            "git_commit": commit,
            "source_sha256": digest,
            "data_files_sha256": data_digest,
        },
        "interpreter": {
            "name": "CPython",
            "distribution": "python-build-standalone",
            "version": python_version,
            "release_tag": release_tag,
            "url": interpreter_url,
            "sha256": interpreter_sha256,
        },
        "swift": {"toolchain": swift_version},
        "engine_dependencies": engines,
    }


def check() -> int:
    """The runnable check: the parser, the committed constraints, and the document's shape."""
    sample = (
        "# a comment\n"
        "alpha==1.0 \\\n"
        "    --hash=sha256:aa \\\n"
        "    --hash=sha256:bb\n"
        "beta==2.0 \\\n"
        "    --hash=sha256:cc\n"
    )
    parsed = parse_requirements(sample)
    assert [entry["package"] for entry in parsed] == ["alpha", "beta"], parsed
    assert parsed[0]["sha256"] == ["aa", "bb"], parsed
    assert parsed[1]["version"] == "2.0", parsed

    for bad in ("gamma==1.0\n", "--index-url https://example.invalid\n", "delta\n"):
        try:
            parse_requirements(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"parse_requirements accepted {bad!r}")

    engines = engine_dependencies(REPO_ROOT / "ohyesmlx" / "constraints")
    names = {entry["engine"] for entry in engines}
    assert names == {"mlxlm", "optiq"}, names
    for entry in engines:
        assert entry["packages"], entry
        for package in entry["packages"]:
            assert package["sha256"], package
            assert all(len(digest) == 64 for digest in package["sha256"]), package

    digest = source_sha256()
    assert len(digest) == 64 and int(digest, 16) >= 0, digest

    document = build_document(
        app_version="0.0.0",
        commit="0" * 40,
        digest=digest,
        data_digest="0" * 64,
        python_version="3.14.10",
        release_tag="20261026",
        interpreter_url="https://example.invalid/python.tar.gz",
        interpreter_sha256="0" * 64,
        swift_version="swift",
        engines=engines,
    )
    assert json.loads(json.dumps(document))["interpreter"]["version"] == "3.14.10"
    for key in ("app", "interpreter", "swift", "engine_dependencies"):
        assert key in document, key

    counts = ", ".join(f"{entry['engine']} {len(entry['packages'])}" for entry in engines)
    print(f"ok: schema {SCHEMA}; constraints {counts}; source sha256 {digest[:16]}…")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="run the check and write nothing")
    parser.add_argument("--out", help="the SBOM to write")
    parser.add_argument("--python", help="the bundled interpreter to record, and to ask")
    parser.add_argument(
        "--package",
        default=str(REPO_ROOT / "ohyesmlx"),
        help="the copied ohyesmlx tree that shipped (build_app.sh passes the bundle's)",
    )
    parser.add_argument("--release-tag", help="the python-build-standalone release")
    parser.add_argument("--interpreter-url", help="where the interpreter tarball came from")
    parser.add_argument("--interpreter-sha256", help="the tarball's pinned sha256")
    parser.add_argument("--swift-version", help="the toolchain that built the binary")
    arguments = parser.parse_args(argv)

    if arguments.check:
        return check()

    missing = [
        flag
        for flag in (
            "out",
            "python",
            "release_tag",
            "interpreter_url",
            "interpreter_sha256",
            "swift_version",
        )
        if not getattr(arguments, flag)
    ]
    if missing:
        parser.error("missing " + ", ".join(f"--{flag.replace('_', '-')}" for flag in missing))

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from ohyesmlx import __version__

    require_clean(REPO_ROOT)
    digest, data_digest = bundle_digests(Path(arguments.python), Path(arguments.package))

    document = build_document(
        app_version=__version__,
        commit=git_commit(REPO_ROOT),
        digest=digest,
        data_digest=data_digest,
        python_version=interpreter_version(Path(arguments.python)),
        release_tag=arguments.release_tag,
        interpreter_url=arguments.interpreter_url,
        interpreter_sha256=arguments.interpreter_sha256,
        swift_version=arguments.swift_version,
        engines=engine_dependencies(REPO_ROOT / "ohyesmlx" / "constraints"),
    )

    out = Path(arguments.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=False) + "\n"
    out.write_text(text, encoding="utf-8")

    recorded = document["engine_dependencies"]
    packages = sum(len(entry["packages"]) for entry in recorded)
    print(
        f"wrote {out} ({len(text.encode('utf-8'))} bytes): ohyesmlx {document['app']['version']}, "
        f"CPython {document['interpreter']['version']}, {packages} pinned packages in "
        f"{len(recorded)} engines; sha256 {hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}…"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
