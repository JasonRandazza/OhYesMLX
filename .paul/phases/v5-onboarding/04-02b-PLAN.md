---
phase: 04-server
plan: 02b
plan_type: tdd
wave: 1
depends_on: [] # runs before 04-02 APPLY: both touch server.py and test_server.py
files_modified: [ohyesmlx/fetch.py, ohyesmlx/recommend.py, ohyesmlx/engines.py, ohyesmlx/server.py, tests/test_fetch.py, tests/test_recommend.py, tests/test_engines.py, tests/test_server.py, docs/interfaces.md]
autonomous: true
description: "Picks know what is already downloaded, guided installs open the tested release, and downloads report progress by byte"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
A recommendation for a model already in the Hugging Face cache says so and is never excluded for disk, the
Osaurus, oMLX and vMLX install plans open the GitHub release page of the tested version, and a download reports
progress by byte while a file is in flight (Jason, 2026-11-02: per-byte progress gives users confidence the
download is working; most catalog models are a single multi-GB file, so per-file progress sat at 0% for minutes).

## Purpose
Found at the 04-01 checkpoint (2026-11-02). Every pick read "N GB download", including models on this Mac, and
the guided installs opened `releases/latest`, so a new user installs whatever shipped last: Osaurus 0.25.31 was
out within hours of 0.25.29 being adopted (Decision 139).
</objective>

<context>
@ohyesmlx/fetch.py `plan`, the present-blob check inside `_download` (verifies hashes; too slow per request for multi-GB files)
@ohyesmlx/recommend.py `pick`, `exclusion_reason`, the reason template
@ohyesmlx/engines.py `_GUIDED_SOURCES`, `TESTED_VERSIONS`, `_guided_plan`
@ohyesmlx/server.py `_get_recommendations`
GitHub tag pages, checked 2026-11-02 with `gh api`: `osaurus-ai/osaurus/releases/tag/0.25.29` (no `v`),
`jundot/omlx/releases/tag/v0.7.3`, `jjang-ai/vmlx/releases/tag/v1.6.59` — each carries its DMGs.
</context>

<acceptance_criteria>

## AC-1: fetch.downloaded
```gherkin
Given a catalog model and a cache dir
When `fetch.downloaded(model, cache_dir=None) -> bool`
Then True only when every file `plan` names has its snapshot link present and resolving to a blob of the catalog
 size; False otherwise, including a partial (`.incomplete`) download
And it never hashes (sizes only: a request-path check), never writes, and `plan`'s ValueError propagates
```

## AC-2: Pick.downloaded
```gherkin
Given `recommend.pick(hw, models, engines, free_disk, downloaded=frozenset())` and the same keyword on
 `exclusion_reason`
When a model's repo is in `downloaded`
Then its Pick carries `downloaded: true`, its reason says it is already on this Mac and names no download size,
 and the disk budget does not apply to it (memory still does)
And `GET /recommendations` passes the set built from `fetch.downloaded` over the catalog
```

## AC-3: Guided installs open the tested release
```gherkin
Given `install_plan(name, macos)` for osaurus, omlx or vmlx
Then `source_url` is that engine's GitHub release-tag URL for `TESTED_VERSIONS[name]`, built from one per-engine
 base and tag prefix ("" for Osaurus, "v" for oMLX and vMLX), never `releases/latest`
And a test pins the three URLs for the current manifest, so a version bump changes the URL with no other edit
```

## AC-4: Byte-level download progress
```gherkin
Given a download of a file larger than one chunk
When bytes are written to its `.incomplete`
Then `progress` events are emitted with `fraction` = (bytes of files already finished + bytes written so far of
 this file) / the model's total bytes, and payload {"path", "bytes_done", "bytes_total"}
And they are throttled: at most one every 0.5 s on the injected `clock`, and only when `fraction` has advanced by
 at least 0.005 since the last one, so a 2 GB download emits on the order of a few hundred events, never one per chunk
And a resumed download starts its fraction from the bytes already on disk, `fraction` never decreases, and the
 existing per-file completion `progress` event is kept
```

</acceptance_criteria>

<tasks>
<task type="auto">
  <name>Task 1: fetch.downloaded and Pick.downloaded</name>
  <files>ohyesmlx/fetch.py, ohyesmlx/recommend.py, ohyesmlx/server.py, tests/test_fetch.py, tests/test_recommend.py, tests/test_server.py, docs/interfaces.md</files>
  <action>AC-1 and AC-2. The reason text stays one fixed template per case in recommend.py. Pin `downloaded` in the Pick shape in docs/interfaces.md. Tests: a scratch cache tree with complete, partial and wrong-size files; a downloaded pick on a Mac too short of disk is still offered.</action>
  <verify>pytest green; live: `/recommendations` on this Mac marks Qwen3.5-4B-4bit and LFM2.5-8B-A1B-MLX-4bit (both in `~/.cache/huggingface/hub`) downloaded</verify>
  <done>AC-1, AC-2 satisfied</done>
</task>
<task type="auto">
  <name>Task 3: byte-level download progress</name>
  <files>ohyesmlx/fetch.py, tests/test_fetch.py, docs/interfaces.md</files>
  <action>AC-4, inside the existing write loop of `_download` (the `while True` that reads `CHUNK_SIZE` and writes to the `.incomplete`); the two throttle constants live once, at module level, with their reason. Use the injected `clock`, never `time.time` directly. Update the existing event-sequence tests to the new sequence rather than loosening them. Tests: a multi-chunk fake body under a fake clock emits throttled, monotonic events; a resume starts at the partial size; tiny files emit only the per-file event. Note the payload in docs/interfaces.md beside the job event shape.</action>
  <verify>pytest green; red-check: remove the 0.5 s throttle and the event-count test fails</verify>
  <done>AC-4 satisfied</done>
</task>
<task type="auto">
  <name>Task 2: tested-release source URLs</name>
  <files>ohyesmlx/engines.py, tests/test_engines.py</files>
  <action>AC-3: replace the three `_GUIDED_SOURCES` URLs with a base + tag-prefix table and build the URL from `TESTED_VERSIONS`. Keep `_url_allowed`'s host rule unchanged (github.com).</action>
  <verify>pytest green; `install_plan("osaurus", 26).source_url` ends `/releases/tag/0.25.29`</verify>
  <done>AC-3 satisfied</done>
</task>
</tasks>

<boundaries>
## DO NOT CHANGE
- server.py beyond `_get_recommendations`; the fetch download path except the progress emission in its write loop; the catalog
## SCOPE LIMITS
- No hashing on the request path; no change to the download's guards, lock, ledger or verification
</boundaries>

<output>
After completion, create `.paul/phases/v5-onboarding/04-02b-SUMMARY.md`
</output>
