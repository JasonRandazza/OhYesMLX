# AGENTS.md

Rules that bind automated contributors to OhYesMLX. Read this before touching anything.

## Precedence

1. This file.
2. `.paul/STATE.md` — the current position and the active boundaries.
3. `.paul/PROJECT.md` — requirements, constraints, and what is explicitly out of scope.
4. `.paul/ROADMAP.md` — phases and their order.

`.paul/STATE.md` is **the only project state store.** There is no `CONTEXT.md`, no
`docs/adr/`, and no wayfinder map. If a second thing starts tracking "what phase are we in",
delete it in the same commit that notices it.

`.paul/HANDOFF.md` is the one exception, and it is not a state store: it is a **session-transfer
note**, rewritten (never appended to) at the end of a session so the next one can resume. It
points at STATE, the research docs and this file rather than copying them. Superseded handoffs
go to `.paul/archive/`, which is history and not required reading. Where HANDOFF and STATE
disagree, STATE wins.

## The one rule that defines this project

**Vary one thing at a time.**

Every run declares its axis and holds the other constant:

- **Runtime axis** — the quantization format is fixed; the serving runtime varies.
- **Format axis** — the serving runtime is fixed; the quantization format varies.

A result that varied both is not a result. Every published table states which axis it
varied and carries the caveat naming what it therefore cannot claim.

## Metric definitions — do not redefine these

- **TTFT** — request sent → first *content* token. Includes prefill. Reasoning tokens are not content. Exception (Decision 119): a response that streams only reasoning, or mirrors reasoning into content, is timed on the stream it produced (`transport.timing_channel`), and every such row is labelled "timed on reasoning channel".
- **ITL / TPOT** — mean gap between successive output tokens after the first.
- **End-to-end latency** — P50 / P90 / P99. Never report a bare mean.
- **Output throughput** — per-request and aggregate are separate numbers and are reported separately.
- **Cold load time** — its own metric. Never folded into the first request.
- **Peak memory** — `footprint -p <pid>`. **Never `ps` RSS**: Metal buffers, mmap'd weights, and wired GPU memory account inconsistently under MLX. `peak_mb` is sound **within a runtime** and carries **no cross-runtime ranking**: Osaurus puts weights in wired GPU pages and oMLX in anonymous memory, and `phys_footprint` charges those differently (measured 2026-09-16; see `docs/research/2026-09-16-footprint-is-not-one-quantity.md`).
- **On-disk size** — includes sidecar files (e.g. JANGTQ's runtime sidecar).

Every measured run pins temperature 0, a fixed chat template, and a fixed output length, and
records every runtime's version. **At temperature 0 no seed is sent** (Jason, 2026-09-26): greedy
decoding makes it inert, and a seeded request forces mlx-lm and OptiQ onto their sequential path,
so a seeded harness never measures the batching path everyday clients use. The one exception is an
OptiQ MTP depth cell, which keeps the seed because OptiQ's MTP engine exists only on that path.
`Runtime.request_seed` is the one definition; each row records the seed it sent.
Runtimes ship different default `top_p` and `repetition_penalty`; leaving them unpinned invalidates the comparison.

Raw observations are never discarded. Summaries must stay recomputable from them.

## Hard boundaries

- **`--cells a,b,c` is the only cell-selection mechanism.** The predecessor project built six overlapping ones across ~3,700 lines. Any second mechanism gets deleted.
- **No governance layer.** No plan hashing, no sealed evidence bundles, no single-use action grants, no operator policy, no workspace scaffolding, no `doctor`. A directory name plus `results.jsonl` is the right amount of provenance for a single-user Mac tool.
- **No new dependency** without naming, in the commit message, what it replaces.
- **Downloads need a reason and a record.** The original rule was "no model downloads", because free disk was 36 GiB. That constraint is looser now (238 GiB free on 2026-09-16, about 100 GiB on 2026-09-24 — check `df` before a fetch), and Jason lifted the rule on 2026-09-16 for what v1 needs — 21.9 GB of LFM2.5-8B-A1B was fetched under it. A download still needs a stated purpose tied to a phase, and the repo ids go in a committed script (`scripts/fetch_moe.sh` is the pattern). **Never download while a measurement is running** — it competes for the disk that `cold_load_s` is timing.
- **No accuracy scoring in v1.** It is out of scope until v1 ships, however tempting.
- **One definition of everything.** A formula, a guard, a size or a constant lives in exactly one place and every caller asks it. Two copies drift: `report.py` and `measure.py` once carried two decode-rate formulas that disagreed on edge cases, and two disk-size walks, one of which miscounted HF-cache snapshots. A second copy gets deleted in the commit that notices it.
- **Each rationale is written once, where the thing it explains is defined.** Callers point at it; they do not restate it. A rule restated in seven docstrings has seven places to go stale.
- **Keep the code graph current.** After changing any `.py` file, run `graphify update .` so `graphify-out/` (gitignored, local) matches the code. A stale graph misleads the next agent the same way a stale docstring does. It is AST-only and costs no tokens.
- **Stop and ask before adding a module, a subcommand, or a header pin.** Code size is not the metric (the old ~1,000-line target predates v2/v3 and was retired 2026-09-23); a new surface is the thing that grows maintenance, so a new surface is the thing that needs Jason's yes.

## Runtime hazards, already paid for

- **OptiQ** flips `--stream-experts auto` on when `model_disk_bytes > 0.70 * total_RAM`. Identical weights then decode roughly 5× slower, with nothing in the artifact explaining it. Pin the flag explicitly.
- **OptiQ's `--max-context <int>` rotates, it does not refuse.** It installs a `RotatingKVCache`, so a longer prompt is silently windowed and measured as though it were whole. Qwen3.5 and LFM2 define their own `make_cache` and ignore the cap; a model that does not would start truncating at the cap with nothing in the output saying so. The harness pins `off` (2026-09-16). See `docs/research/2026-09-16-prompt-length-context-limits.md`.
- **Osaurus takes no tuning flags.** Everything that determines what you measure lives in `~/.osaurus/config/*.json` and an app plist. Snapshot it and diff against a checked-in baseline before every run.
- **oMLX** must be given a per-run temporary model catalog so only the cell's model is visible; otherwise it may serve something other than what you think.
- **oMLX's SSD prefix cache survives restarts** and consumes real disk. Clear it between cold-cache runs. The harness does this itself: its oMLX command puts the SSD cache under the per-run scratch base path that `stop()` removes, and passes `--no-cache` unless `cache_state=on` (`runtimes.Omlx.start_command`); the hazard is for anything run outside the harness.
- **Ports:** Osaurus 1337, `optiq serve` 8080, `mlx_lm.server` 8081, oMLX 8100, vMLX 8000. A run that does not release its port has failed, whatever else it reported.
- **A cell that produces incoherent output has FAILED, however fast it was.** Verified 2026-09-15: stock `mlx_lm.server` loads `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` in 4s, returns HTTP 200, generates a clean 64/64 tokens — and the text is mixed-script token salad with replacement characters. Nothing errored. A speed-only harness would have recorded that cell as healthy with excellent throughput. Every measured cell therefore passes a **coherence gate** before its numbers count, and a cell that fails the gate reports `FAIL` with its sample output, never a tok/s figure. This is not accuracy scoring (deferred to v2) — it is a floor, and it is cheap.
- **Exactly one model is resident at a time.** Never start a second runtime while another holds weights. On 64 GB of unified memory a 35B MoE is ~20 GB resident; two at once saturates memory, forces compression and swap, and silently corrupts every number in the run — the measurement would still complete and still look plausible. `measure.py` stops the previous runtime and confirms its port is free *before* starting the next. This is not an optimization; a run that violates it is void.
- **Thermal.** An M2 Max in a laptop chassis throttles under sustained inference. Interleave cell order, insert cooldowns, record drift. Walking cells in config order aliases thermal drift perfectly onto runtime identity.
- **Nothing else runs on this machine while a cell is measured.** Not a test suite, not a git operation, not a download, not "lightweight" background work. The harness cannot detect contention, so this rule holds without enforcement. It was paid for on 2026-09-16: a coordinator pushed commits and ran pytest during the oMLX column, and one cell warmed at 68–73 tok/s, then *measured* 40–60 before recovering to 75 on the quiet second visit. It published 60.7 at +40.6% drift and would have inverted the format ordering that replicates across three codebases. That column is discarded and kept, named with its reason.
- **Never edit `ohyesmlx/*.py` while a grid is running.** The runners re-enter the CLI once per column, so a mid-run edit means the columns ran different code and cannot be joined. Do defect work on a branch in a worktree and merge after the grid lands.
- **Discard a run only for a stated defect in its conditions, never for its number.** Keep the discarded directory and name it with the reason. A run thrown away without one was thrown away for its result.
- **Stale Osaurus instances accumulate.** `osaurus stop` frees the port and leaves the app alive at ~900 MB, so a port sweep misses it by design; three aged 5–7 h were resident through both grids on 2026-09-16. Sweep them by full executable path — `^/Applications/osaurus.app/Contents/MacOS/osaurus` — **never by the name `osaurus`**, because `osaurus mcp` is Jason's long-running process. Any MCP host that registers `osaurus mcp` relaunches the app on every session, and so does its Login Item; see `docs/runtimes/osaurus.md` §1.2.
- **`mlx_lm.server` lives in its own venv** at `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`, which must be on `PATH`. Without it every mlx-lm cell fails to start, and that failure looks exactly like an unsupported `model_type`. Check `from mlx_lm import load` in that venv before believing it.

## Delegation contract

Implementation is delegated to Command Code workers via `cc-agent`, on whatever route the fleet
profile names (`orca-fleet routes`; the `fleet-provider-routing` skill has the map — since
2026-09-24 `implement`/`refactor` run DeepSeek v4.1 flash, `test`/`explain` MiMo flash, `review`
MiMo pro; Luna is explicit-only). Claude Opus orchestrates and is the final reviewer.

A worker dispatch always carries: the plan's acceptance criteria, the exact files it may
touch, and "touch nothing else."

A ticket closes only when the coordinator has **personally observed** the diff and a
green test run — `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
(the repo has no venv with pytest; that one carries `pytest` and `tokenizers`).
**A worker's report is not evidence**, and neither is a worker's *justification* just because
its tests pass: a drift worker's code and tests were right while its stated reason for the
threshold was false, and only running it against real rows showed that. Conversely, treat a
BLOCKED or a flagged scope note as a finding — workers have repeatedly caught contradictions
in the order that the coordinator wrote. And the coordinator's own commit messages are held to
the same standard: say a fix is in the code only once it is in the code. The predecessor project recorded a
worker whose own tests passed while it deleted an unrelated function, and another that
ran a command against an explicit capitalised warning and left a server holding port 1337.

## Style

- Python 3.11+, flat package, stdlib first.
- Prefer deleting to adding. Prefer boring to clever.
- A deliberate shortcut with a known ceiling gets a `# ponytail:` comment naming the ceiling and the upgrade path.
- Non-trivial logic leaves one runnable check behind — the smallest thing that fails if the logic breaks.

## Dispatching work to Command Code

Work orders go out through `.paul/orders/dispatch.sh <role> <order-file>`, which prepends
`.paul/orders/PREAMBLE.md` verbatim. The preamble carries the project's standing rules and
is byte-identical on every dispatch, so the worker bills it as a cache read rather than fresh
input — 50x cheaper on DeepSeek — on the part of the
prompt that never changes. Order-specific text goes after it, never before: anything prepended
breaks the shared prefix and every order that follows pays full price.

Editing PREAMBLE.md costs one full re-read on the next dispatch. Edit it when the standing
rules actually change, not to tidy wording.

Traps worth keeping:

- `cc-agent` defaults to 40 turns; set `CC_AGENT_MAX_TURNS=200` for anything non-trivial.
  Scope each dispatch to one deliverable and forbid tangents explicitly. A DeepSeek peak window
  (when routed there) is a price bump the launcher announces and proceeds through, not a blocker.
- `explain` and `review` run in plan mode and cannot write. Research that must produce a
  file needs `implement`.
- The collateral-deletion guard compares definition snapshots and misfires under fan-out —
  concurrent workers' files register as deletions. Verify against `git`, not the warning.
- Pin interfaces in `docs/interfaces.md` before fanning out. Shapes are the coupling.

## Never infer a capability from the absence of a flag

`--help` documents a command line. It does not document a runtime. Every serving runtime here
is a GUI application that ships a CLI as one entry point among several, and its real
configuration surface spans four places:

1. the command-line flags,
2. a settings file with keys that have no flag (`~/.omlx/settings.json`, `~/.osaurus/`),
3. per-request fields the OpenAI-compatible endpoint honours,
4. behaviour decided only in the shipped source.

All four ship readable Python inside their app bundles. The source is the authority when it
disagrees with the documentation.

**A claim that a tool CANNOT do something needs evidence from the source or the settings, not
the absence of a flag.** A negative claim closes off investigation; a positive one invites it,
so the negative deserves the higher standard. If all you have is "there is no flag for it",
write exactly that — do not promote it to "it cannot".

This rule was bought at a real price. The harness published that oMLX "does not stream", on
the true observation that `omlx serve --help` exposes no streaming-granularity flag. oMLX
streams 15 deltas per response in its `reasoning_content` channel. One grep of its own bundle
finds `stream_interval: int = 1  # Tokens to batch before streaming (1=every token)`. The
reported TTFT was 5.499 s against a real 0.685 s — wrong by 8x, against the runtime, and it
would have shipped as a published claim.

Two habits that would have caught it, both cheap:

- **Probe with a large enough `max_tokens`.** The original probe used 8, small enough that one
  content delta looked like proof of non-streaming rather than a sample size of one.
- **Read the field you already record.** `content_event_count` was in every observation from
  the first live run onward and nothing consulted it.

`docs/runtimes/<name>.md` holds the per-runtime capability reference. Read it before claiming
a runtime cannot do something, and update it when you learn otherwise.
