---
phase: 04-server
plan: 02b
plan_type: tdd
wave: 1
depends_on: [] # runs before 04-02 APPLY: both touch server.py and test_server.py
files_modified: [ohyesmlx/fetch.py, ohyesmlx/recommend.py, ohyesmlx/engines.py, ohyesmlx/server.py, tests/test_fetch.py, tests/test_recommend.py, tests/test_engines.py, tests/test_server.py, docs/interfaces.md]
autonomous: true
description: "Picks know what is already downloaded, and guided installs open the tested release, not the latest"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
A recommendation for a model already in the Hugging Face cache says so and is never excluded for disk, and the
Osaurus, oMLX and vMLX install plans open the GitHub release page of the tested version.

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
  <name>Task 2: tested-release source URLs</name>
  <files>ohyesmlx/engines.py, tests/test_engines.py</files>
  <action>AC-3: replace the three `_GUIDED_SOURCES` URLs with a base + tag-prefix table and build the URL from `TESTED_VERSIONS`. Keep `_url_allowed`'s host rule unchanged (github.com).</action>
  <verify>pytest green; `install_plan("osaurus", 26).source_url` ends `/releases/tag/0.25.29`</verify>
  <done>AC-3 satisfied</done>
</task>
</tasks>

<boundaries>
## DO NOT CHANGE
- server.py beyond `_get_recommendations`; the fetch download path; the catalog
## SCOPE LIMITS
- No byte-level download progress (noted for 04-02's checkpoint), no hashing on the request path
</boundaries>

<output>
After completion, create `.paul/phases/v5-onboarding/04-02b-SUMMARY.md`
</output>
