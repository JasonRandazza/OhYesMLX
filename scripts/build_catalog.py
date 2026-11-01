"""Build ``ohyesmlx/catalog.json`` from read-only Hugging Face API calls.

Standard library only, and re-runnable: the researched columns (title, params, format,
modality, license, tier, measured_here, notes) are literals in ``SEED`` below, and the
columns a build must not invent -- the commit, the file list, each file's size and hash --
are read from the Hub every time. No weight bytes are fetched; the two endpoints are
metadata only:

    GET https://huggingface.co/api/models/<repo>                                   -> "sha"
    GET https://huggingface.co/api/models/<repo>/tree/<sha>?recursive=true&expand=true
                                                                   -> path, size, lfs.oid

``size`` is the file's byte length, ``lfs.oid`` the sha256 a download is verified against,
and a file with no ``lfs`` block is a plain git blob whose 40-hex ``oid`` goes in
``git_oid`` with ``sha256`` null (research §3.1, §3.4). The tree listing is paginated and
this follows the ``Link: rel="next"`` header, because a silently truncated page would
publish a ``size_bytes`` that is short of what the disk pays.

``params`` is the BASE model's count, not the artifact's ``safetensors.total``: that field
moves with the quantization (752,393,024 for the 0.8B OptiQ bundle against 873,438,784 for
its base), so it is not comparable across rows (research §1.1). The literals below are that
table's column; the one row the table does not carry, the 4B stock artifact, reads its base
``Qwen/Qwen3.5-4B`` by the same method.

Usage, from the repository root:

    python3 scripts/build_catalog.py

It rewrites ``ohyesmlx/catalog.json``, so a run today re-pins every repository to the commit
the Hub reports today and stamps that date in the file's ``built`` field.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://huggingface.co/api/models"
AGENT = "ohyesmlx-catalog-build/1"
OUTPUT = pathlib.Path(__file__).resolve().parent.parent / "ohyesmlx" / "catalog.json"

STOCK = "mlx affine 4-bit gs64"
LFM = "LFM Open License 1.0 (other)"

# The approved set, in the research table's order: starter rows first, then the two the
# disk cap excludes but this Mac has measured. Every literal here is from
# docs/research/2026-10-30-phase3-models.md §5 unless the note says otherwise.
SEED = [
    {
        "repo": "mlx-community/Qwen3-0.6B-4bit",
        "title": "Qwen3 0.6B 4-bit",
        "params": 751_632_384,
        "format": STOCK,
        "modality": "text",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "The 0.5B slot and the cheapest row by disk: 0.75B parameters, pure text, qwen3 (research 1.2).",
    },
    {
        "repo": "mlx-community/Qwen3.5-0.8B-4bit",
        "title": "Qwen3.5 0.8B 4-bit",
        "params": 873_438_784,
        "format": STOCK,
        "modality": "vision-language",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "The stock 4-bit of the base the OptiQ row below also quantizes; vision-bearing, and the text path loads it (research 0.4, 5).",
    },
    {
        "repo": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "title": "Qwen3.5 0.8B OptiQ 4-bit",
        "params": 873_438_784,
        "format": "OptiQ-4bit (4/8-bit mixed)",
        "modality": "vision-language",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "1.36x the stock 4-bit row, and 201,202,432 B of it is the vision sidecar the text path never reads (research 1.2).",
    },
    {
        "repo": "mlx-community/LFM2.5-1.2B-Instruct-4bit",
        "title": "LFM2.5 1.2B Instruct 4-bit",
        "params": 1_170_340_608,
        "format": STOCK,
        "modality": "text",
        "license": LFM,
        "tier": "starter",
        "measured_here": False,
        "notes": "Pure-text LFM2.5 at 1.17B (research 5).",
    },
    {
        "repo": "mlx-community/granite-4.0-h-1b-4bit",
        "title": "Granite 4.0 H 1B 4-bit",
        "params": 1_461_538_368,
        "format": STOCK,
        "modality": "text",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "The only hybrid family here: 4 attention layers of 40, so its KV is tiny and its residency is weights (research 1.2).",
    },
    {
        "repo": "mlx-community/Qwen3.5-2B-4bit",
        "title": "Qwen3.5 2B 4-bit",
        "params": 2_274_069_824,
        "format": STOCK,
        "modality": "vision-language",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "The stock 4-bit 2B; vision-bearing, as every Qwen3.5 package is (research 0.4, 5).",
    },
    {
        "repo": "RepublicOfKorokke/Qwen3.5-2B-oQ4",
        "title": "Qwen3.5 2B oQ4",
        "params": 2_274_069_824,
        "format": "oQ4 (mixed 4/5/6/8)",
        "modality": "vision-language",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "The one oQ artifact under the cap: mixed 4/5/6/8-bit with 41 overrides (research 1.2, 1.4).",
    },
    {
        "repo": "mlx-community/LFM2.5-2.6B-4bit",
        "title": "LFM2.5 2.6B 4-bit",
        "params": 2_697_198_592,
        "format": STOCK,
        "modality": "text",
        "license": LFM,
        "tier": "starter",
        "measured_here": False,
        "notes": "The largest strictly in-cap artifact at 2.697B parameters (research 1.2).",
    },
    {
        "repo": "mlx-community/SmolLM3-3B-4bit",
        "title": "SmolLM3 3B 4-bit",
        "params": 3_075_098_624,
        "format": STOCK,
        "modality": "text",
        "license": "apache-2.0",
        "tier": "starter",
        "measured_here": False,
        "notes": "Not 3B by parameters: 3.075B, 2.5% over the cap and in the starter tier on disk size (research 1.2).",
    },
    {
        "repo": "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "title": "Llama 3.2 3B Instruct 4-bit",
        "params": 3_212_749_824,
        "format": STOCK,
        "modality": "text",
        "license": "llama3.2",
        "tier": "starter",
        "measured_here": False,
        "notes": "Not 3B by parameters either: 3.213B, 7% over; the llama family has live PASS rows on all five engines (research 5, footnote 6).",
    },
    {
        "repo": "mlx-community/Qwen3.5-4B-4bit",
        "title": "Qwen3.5 4B 4-bit",
        # The research table does not carry this row: the base count is read from
        # Qwen/Qwen3.5-4B's metadata by the method research 1.1 pins for params.
        "params": 4_659_865_088,
        "format": STOCK,
        "modality": "vision-language",
        "license": "apache-2.0",
        "tier": "standard",
        "measured_here": True,
        "notes": "This Mac's measured control on stock 4-bit: PASS on mlx-lm, oMLX, OptiQ and vMLX (research 4.1).",
    },
    {
        "repo": "mlx-community/LFM2.5-8B-A1B-MLX-4bit",
        "title": "LFM2.5 8B A1B MoE 4-bit",
        "params": 8_467_856_832,
        "format": STOCK,
        "modality": "text",
        "license": LFM,
        "tier": "standard",
        "measured_here": True,
        "notes": "The only measured MoE: 8.47B total, 1B active, 32 experts top-4, PASS on all five engines (research 5).",
    },
]


def _get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode()), response.headers.get("Link")


def _next(link: str | None, base: str) -> str | None:
    """The ``rel="next"`` URL out of a ``Link`` header, or None on the last page."""
    if not link:
        return None
    for part in link.split(","):
        if 'rel="next"' in part:
            return urllib.parse.urljoin(base, part.split(";")[0].strip().strip("<>"))
    return None


def files_at(repo: str, revision: str) -> list[dict]:
    """Every file of *repo* at *revision*, following the listing's pagination."""
    url = f"{API}/{repo}/tree/{revision}?recursive=true&expand=true"
    files: list[dict] = []
    while url:
        entries, link = _get(url)
        for entry in entries:
            if entry.get("type") != "file":
                continue  # a directory entry carries no size and is not a download
            lfs = entry.get("lfs") or {}
            files.append(
                {
                    "path": entry["path"],
                    "size": entry["size"],
                    # A file is either an LFS object or a plain git blob; the pointer
                    # blob's oid is not the file's hash, so an LFS row records sha256 only.
                    "sha256": lfs.get("oid"),
                    "git_oid": None if lfs else entry.get("oid"),
                }
            )
        url = _next(link, url)
        time.sleep(0.2)
    return files


def build() -> dict:
    models = []
    for row in SEED:
        info, _ = _get(f"{API}/{row['repo']}")
        if info.get("gated") is not False:
            raise SystemExit(
                f"{row['repo']} answered gated={info.get('gated')!r}; the seed is built from "
                "public repos only"
            )
        revision = info["sha"]
        files = files_at(row["repo"], revision)
        if not files:
            raise SystemExit(f"{row['repo']} listed no files at {revision}")
        models.append(
            {
                **{key: row[key] for key in (
                    "repo", "title", "params", "format", "modality", "license", "tier"
                )},
                "revision": revision,
                "size_bytes": sum(file["size"] for file in files),
                "files": sorted(files, key=lambda file: file["path"]),
                "engines": ["mlxlm", "osaurus", "omlx", "optiq", "vmlx"],
                "measured_here": row["measured_here"],
                "notes": row["notes"],
            }
        )
        print(f"{row['repo']:<45} {revision} {models[-1]['size_bytes']:>12}", file=sys.stderr)
    return {
        "built": datetime.now(timezone.utc).date().isoformat(),
        "source": (
            "GET https://huggingface.co/api/models/<repo> for the commit "
            "('sha'), and GET https://huggingface.co/api/models/<repo>/tree/<sha>"
            "?recursive=true&expand=true for each file's path, size, lfs.oid (sha256) "
            "or git oid; no weight bytes are fetched"
        ),
        "note": (
            f"Built by scripts/build_catalog.py: all {len(models)} repos answered "
            "'gated: false' to the anonymous API on this date. size_bytes is the sum of "
            "every listed file, README.md and .gitattributes included, which is what the "
            "disk pays and how the research table summed it (research 1.1)."
        ),
        "models": models,
    }


def main() -> None:
    payload = build()
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(payload['models'])} models)", file=sys.stderr)


if __name__ == "__main__":
    main()
