---
phase: 04-server
plan: 02b
completed: 2026-11-02
duration: ~40min
description: "Pick.downloaded via fetch.downloaded (sizes and links), tested-release install URLs, throttled per-byte download progress"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 02b Summary

**Picks know what is already downloaded, guided installs open the tested release, and downloads report progress by byte.**

## AC Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC-1 `fetch.downloaded` (sizes + links, no hash, no write) | Pass | Tests on complete/partial/wrong-size scratch trees; worker red-check (size ignored -> wrong-size test fails) |
| AC-2 `Pick.downloaded`, no disk budget for it, reason text | Pass | Tests; live `/recommendations` answered (see finding) |
| AC-3 tested-release URLs | Pass | Live: `.../osaurus/releases/tag/0.25.29`, `.../omlx/releases/tag/v0.7.3`, `.../vmlx/releases/tag/v1.6.59`; red-check (`releases/latest` -> URL test fails) |
| AC-4 per-byte progress, throttled 0.5 s / 0.5% | Pass | Fake-clock tests, resume starts at partial size, monotonic; red-check (no throttle -> count test fails) |

1014 tests green.

## Finding (live check, 2026-11-02): the hero-model files on disk are not the pinned bytes

`/recommendations` marked nothing downloaded on this Mac, and that answer is correct. In
`~/.cache/huggingface/hub`, `model.safetensors` for `mlx-community/Qwen3.5-4B-4bit` (revision `0e7ffd5c`) and
`mlx-community/LFM2.5-8B-A1B-MLX-4bit` (`146590a4`) is a regular file in `snapshots/`, not a link into `blobs/`,
dated 2026-09-15 / 09-16 (the v1 fetches), and 873 / 139 bytes larger than the catalog's size for that
revision. Every other file matches. The difference is in the safetensors header region (both headers carry
`{"format": "mlx"}`); whether the tensor bytes are identical is not established. Published tables ran on these
files. Carried to STATE as Jason's call.

## Also found

- `fetch.download` checks an occupied snapshot path only after the transfer, so for these two models it would fetch
  ~3 / 4.8 GB and then refuse to overwrite (safely, nothing overwritten). A pre-transfer check is a Phase 4.5 item.
- `server._get_recommendations` calls `fetch.downloaded` directly rather than through a `make_server` seam; tests
  monkeypatch it. Fine for now; 04-02 may fold it into the seams it adds.

## Files Changed

ohyesmlx/fetch.py, recommend.py, engines.py, server.py (`_get_recommendations` only), their tests, docs/interfaces.md.
