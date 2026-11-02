"""The curated model catalog: what OhYesMLX offers to download, pinned to a commit.

Seam S4/S5's input. ``load()`` answers the one question a downloader has -- which files,
at which revision, of which size and hash -- for a short list of small MLX models chosen
by hand, so the app never asks Hugging Face "what is latest" while a user is waiting on
an answer (§4 of ``docs/research/2026-10-30-phase3-models.md``).

Four rules shape the file this reads:

- **Every row is pinned to a commit, not a branch.** ``revision`` is the 40-hex commit the
  tree listing was read at, so the listing and the download it describes cannot drift
  apart between builds.
- **``size_bytes`` is the sum of ``files``**, and every file the listing holds is in
  ``files``. It is what the disk pays -- README and ``.gitattributes`` included -- which is
  also how the research measured the table (its §1.1), so the two numbers agree.
- **A file carries exactly one hash, and it is what a download verifies against.** An LFS
  file carries ``sha256``, the tree listing's ``lfs.oid``, and a plain git file carries
  ``git_oid``, the listing's ``oid``. A file with both or neither is refused: two answers
  (or none) cannot verify a download, and how each is checked lives at ``fetch._verify``.
- **A row no engine can serve is not a row.** ``engines`` is a subset of the five engines
  in ``engines.ONBOARDING_ENGINES``, taken from the research table's own column.
- **``base`` names the model, not the format.** Every row of one base model carries that
  base's name -- ``Qwen3.5-2B`` on both its stock 4-bit and its oQ4 row -- so
  :func:`siblings` answers "what other formats of this model does the catalog hold?" from
  the data rather than by parsing titles at request time.

``load()`` refuses a missing, unreadable or ill-shaped file with ``ValueError`` naming the
file, the row and the field: a row half-read would report a size or a hash nobody checked.
The JSON itself is built by ``scripts/build_catalog.py`` from read-only Hub API calls.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
from dataclasses import dataclass

from ohyesmlx.engines import ONBOARDING_ENGINES

# The seed, beside the module the way the tested-versions manifest is: pyproject ships the
# whole `ohyesmlx` package in both builds, so a checkout and an installed wheel read the
# same file and no force-include is needed.
CATALOG_PATH = pathlib.Path(__file__).resolve().parent / "catalog.json"

# Free disk a download needs, as a multiple of its bytes: the extra covers a largest-shard
# `.incomplete` sitting beside the finished files (research 2026-10-30 section 4.3). The one
# definition: `recommend` asks `disk_needed` whether a model can fit, `fetch` asks it
# whether a download may start.
DISK_MARGIN = 1.2


def disk_needed(nbytes: int) -> int:
    """The free disk a download of *nbytes* needs: ``ceil(nbytes * DISK_MARGIN)``.

    The one disk-margin rule, rounded up so a byte-short answer never authorizes a
    download. The margin's rationale is the constant's comment above.
    """
    return math.ceil(nbytes * DISK_MARGIN)


# The two tiers, and what they mean. `starter` is the disk-size cap (about 2 GB of
# weights, so 3B-class artifacts are in); `standard` is the larger artifacts this Mac has
# already measured, which a first-time user may still be offered.
TIERS = ("starter", "standard")

# A Qwen3.5 MLX package is `Qwen3_5ForConditionalGeneration` with a vision_config, and the
# text path loads it; the row says so rather than calling it a text model (§0 of the
# research, and the reason a "text model per family" rule is satisfied by other families).
MODALITIES = ("text", "vision-language")

# One definition of the shapes: a Hugging Face repo id is exactly one org/name pair, a
# commit and a git blob id are 40 lowercase hex digits, and an LFS file's sha256 is 64.
_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ModelFile:
    """One file of a repo at the row's pinned revision.

    ``sha256`` is the LFS object's own sha256 and ``git_oid`` the id a non-LFS file is
    listed with; exactly one of the two is set, and it is the only thing a download can be
    verified against.
    """

    path: str
    size: int
    sha256: str | None
    git_oid: str | None


@dataclass(frozen=True)
class Model:
    """One catalog row: the model, its format, and everything a download needs."""

    repo: str
    title: str
    params: int  # the BASE model's count, never the quantized artifact's (§1.1)
    format: str
    modality: str  # one of MODALITIES
    license: str
    tier: str  # one of TIERS
    revision: str  # the 40-hex commit the listing was read at
    size_bytes: int  # == sum(file.size for file in files)
    files: list[ModelFile]  # every file the listing holds, in path order
    engines: list[str]  # a subset of ONBOARDING_ENGINES
    measured_here: bool  # a results/**/results.jsonl row exists for this exact artifact
    notes: str
    # Last because it is the one field with a default, and a default may not precede a field
    # without one. `load` requires it on every row -- a missing or non-string `base` is a
    # ValueError naming the repo -- so a catalog row can never take this default; it exists
    # for the rows other modules' tests build by hand, which name a model for a test of
    # something else.
    base: str = ""  # the base model's name, the same for every format of one base


def _string(where: str, entry: dict, field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where} field {field!r} must be a non-empty string")
    return value


def _integer(where: str, entry: dict, field: str, *, positive: bool) -> int:
    value = entry.get(field)
    # `isinstance(True, int)` is True, and a boolean is never a parameter count or a size.
    if isinstance(value, bool) or not isinstance(value, int) or (positive and value <= 0):
        raise ValueError(
            f"{where} field {field!r} must be a "
            f"{'positive' if positive else 'non-negative'} integer"
        )
    return value


def check_path(where: str, path) -> None:
    """The one file-path guard: a relative path inside the repo (AC-11).

    No leading ``/``, no ``..`` segment, no backslash, no NUL and no empty segment, so a
    hostile literal cannot name a file outside the snapshot tree. :func:`_files` applies it
    to every row at load and ``fetch.plan`` applies it to the row it is handed.
    """
    if not isinstance(path, str) or not path:
        raise ValueError(f"{where}: a file path is {path!r}; expected a non-empty string")
    if path.startswith("/"):
        raise ValueError(f"{where}: file path {path!r} is absolute")
    if "\\" in path:
        raise ValueError(f"{where}: file path {path!r} contains a backslash")
    if "\x00" in path:
        raise ValueError(f"{where}: file path {path!r} contains a NUL")
    for segment in path.split("/"):
        if segment == "..":
            raise ValueError(f"{where}: file path {path!r} walks up with '..'")
        if not segment:
            raise ValueError(f"{where}: file path {path!r} has an empty segment")


def _files(where: str, entry: dict) -> list[ModelFile]:
    entries = entry.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{where} field 'files' must be a non-empty list")
    files = []
    for position, item in enumerate(entries):
        at = f"{where} field 'files' entry #{position}"
        if not isinstance(item, dict):
            raise ValueError(f"{at} must be an object")
        path = item.get("path")
        check_path(f"{where} field 'files'", path)
        at = f"{where} field 'files' entry {path!r}"
        size = _integer(at, item, "size", positive=False)
        sha256 = item.get("sha256")
        if sha256 is not None and (
            not isinstance(sha256, str) or not _SHA256.match(sha256)
        ):
            raise ValueError(f"{at} field 'sha256' must be a 64-hex sha256 or null")
        git_oid = item.get("git_oid")
        if git_oid is not None and (
            not isinstance(git_oid, str) or not _COMMIT.match(git_oid)
        ):
            raise ValueError(f"{at} field 'git_oid' must be a 40-hex git blob id or null")
        if sha256 is not None and git_oid is not None:
            raise ValueError(
                f"{at} carries both 'sha256' and 'git_oid'; exactly one of them is what a "
                "download is verified against"
            )
        if sha256 is None and git_oid is None:
            raise ValueError(
                f"{at} carries neither 'sha256' nor 'git_oid'; one of them is what a "
                "download is verified against"
            )
        files.append(ModelFile(path=path, size=size, sha256=sha256, git_oid=git_oid))
    return files


def _model(path: pathlib.Path, position: int, entry) -> Model:
    """One validated row; every refusal names *path*, the row and the field at fault."""
    where = f"the model catalog {path} entry #{position}"
    if not isinstance(entry, dict):
        raise ValueError(f"{where} must be an object")
    repo = entry.get("repo")
    if not isinstance(repo, str) or not _REPO.match(repo):
        raise ValueError(f"{where} field 'repo' must be an org/name string")
    # From here the row can name itself, and every later message uses that name.
    where = f"the model catalog {path} entry {repo}"

    base = _string(where, entry, "base")
    title = _string(where, entry, "title")
    params = _integer(where, entry, "params", positive=True)
    model_format = _string(where, entry, "format")
    modality = _string(where, entry, "modality")
    if modality not in MODALITIES:
        raise ValueError(
            f"{where} field 'modality' is {modality!r}; expected one of "
            f"{', '.join(MODALITIES)}"
        )
    license_name = _string(where, entry, "license")
    tier = _string(where, entry, "tier")
    if tier not in TIERS:
        raise ValueError(
            f"{where} field 'tier' is {tier!r}; expected one of {', '.join(TIERS)}"
        )
    revision = _string(where, entry, "revision")
    if not _COMMIT.match(revision):
        raise ValueError(
            f"{where} field 'revision' must be a 40-hex commit sha, not {revision!r}"
        )
    files = _files(where, entry)
    size_bytes = _integer(where, entry, "size_bytes", positive=True)
    total = sum(file.size for file in files)
    if size_bytes != total:
        raise ValueError(
            f"{where} field 'size_bytes' is {size_bytes} and its 'files' sum to {total}"
        )
    engines = entry.get("engines")
    if not isinstance(engines, list) or not engines:
        raise ValueError(f"{where} field 'engines' must be a non-empty list")
    unknown = [name for name in engines if name not in ONBOARDING_ENGINES]
    if unknown:
        raise ValueError(
            f"{where} field 'engines' names {', '.join(map(repr, unknown))}; expected a "
            f"subset of {', '.join(ONBOARDING_ENGINES)}"
        )
    measured_here = entry.get("measured_here")
    if not isinstance(measured_here, bool):
        raise ValueError(f"{where} field 'measured_here' must be true or false")
    notes = _string(where, entry, "notes")

    return Model(
        repo=repo,
        base=base,
        title=title,
        params=params,
        format=model_format,
        modality=modality,
        license=license_name,
        tier=tier,
        revision=revision,
        size_bytes=size_bytes,
        files=files,
        engines=list(engines),
        measured_here=measured_here,
        notes=notes,
    )


def load(path=CATALOG_PATH) -> list[Model]:
    """Read and validate the catalog at *path*, row by row, in file order.

    The default is the shipped seed. A missing, unreadable or ill-shaped file raises
    ``ValueError`` naming the file -- and, for an ill-shaped row, the repo and the field --
    because a catalog half-read would offer a model at a size or a hash nobody checked.
    """
    path = pathlib.Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read the model catalog {path}: {error}") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError(f"the model catalog {path} is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(
            f"the model catalog {path} must be a JSON object holding 'built' and 'models'"
        )
    if not isinstance(payload.get("built"), str) or not payload["built"]:
        raise ValueError(f"the model catalog {path} has no string 'built' date")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError(f"the model catalog {path} has no 'models' list")
    return [_model(path, position, entry) for position, entry in enumerate(models)]


def siblings(model: Model, models: list[Model]) -> list[Model]:
    """The other rows of *model*'s base: every other format of the same model.

    In catalog order, so the stock format comes before the one built on it. The rows are
    matched on ``base`` -- the data -- and not on a title parsed at request time, which is
    why a hand-entered base is worth a test that lists every one of them.
    """
    return [
        other for other in models if other.base == model.base and other.repo != model.repo
    ]
