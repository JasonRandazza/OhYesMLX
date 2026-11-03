# UAT Issues: Phase 4 (server, jobs, quickbench)

**Tested:** 2026-11-03
**Source:** `04-01` .. `04-03c` SUMMARY files, after review-fix commit `6c84f5c`
**Tester:** Jason via verify-work workflow, live `ohyesmlx app --port 8765` driven with curl

## Results

| # | Check | Result |
|---|---|---|
| 0 | Launch line `{"port", "token"}` | Pass |
| 1 | `GET /hardware` (M2 Max, `gpu_cores: 30`) | Pass |
| 2 | Guard: no token 401, foreign Origin 403 | Pass |
| 3 | `GET /engines`: five engines, vMLX `tested: false` | Pass |
| 4 | `GET /recommendations`: `downloaded`, `measured_here` on Qwen3.5-2B-4bit (178.6 tok/s, omlx, quick) | Pass (see UAT-001) |
| 5 | `GET /quickbench/plan` on an uncached repo: 400 `bad_args`, download first | Pass |
| 6 | Refused evict job: stream `error` (`unknown_repo`) + `done`, closes; next `POST /jobs` 202, not 409 | Pass |
| 7 | Ctrl-C: clean exit, port 8765 released | Pass |

## Open Issues

### UAT-001: Hero models on disk report `downloaded: false`

**Discovered:** 2026-11-03
**Phase/Plan:** 04-02b
**Severity:** Minor (known; STATE Blockers row "Resolved 2026-11-03")
**Feature:** `GET /recommendations` `Pick.downloaded`
**Description:** `mlx-community/Qwen3.5-4B-4bit` and `mlx-community/LFM2.5-8B-A1B-MLX-4bit` are in `~/.cache/huggingface/hub` but show `downloaded: false`.
**Expected:** `true`, or a state that does not offer a 3.1 / 4.8 GB re-download of bytes already present.
**Actual:** `false`: `fetch.downloaded` compares file sizes against the pinned revision, and these two files are a re-serialisation of it (same tensors, reordered, header 873 / 139 bytes longer; proven by sha256 on 2026-11-03).
**Route:** Phase 4.5 or Phase 5 decision: accept a tensor-equivalent file (header splice + hash, as the 2026-11-03 check did), or leave it, since only files rewritten outside the downloader can hit it.

## Resolved Issues

None yet.

---

*Phase: 04-server*
*Tested: 2026-11-03*
