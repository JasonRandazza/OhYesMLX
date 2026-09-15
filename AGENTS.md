# AGENTS.md

Rules that bind automated contributors to OhYesMLX. Read this before touching anything.

## Precedence

1. This file.
2. `.paul/STATE.md` — the current position and the active boundaries.
3. `.paul/PROJECT.md` — requirements, constraints, and what is explicitly out of scope.
4. `.paul/ROADMAP.md` — phases and their order.

`.paul/STATE.md` is **the only project state store.** There is no `CONTEXT.md`, no
`docs/adr/`, no handoff documents, and no wayfinder map. If a second thing starts
tracking "what phase are we in", delete it in the same commit that notices it.

## The one rule that defines this project

**Vary one thing at a time.**

Every run declares its axis and holds the other constant:

- **Runtime axis** — the quantization format is fixed; the serving runtime varies.
- **Format axis** — the serving runtime is fixed; the quantization format varies.

A result that varied both is not a result. Every published table states which axis it
varied and carries the caveat naming what it therefore cannot claim.

## Metric definitions — do not redefine these

- **TTFT** — request sent → first *content* token. Includes prefill. Reasoning tokens are not content.
- **ITL / TPOT** — mean gap between successive output tokens after the first.
- **End-to-end latency** — P50 / P90 / P99. Never report a bare mean.
- **Output throughput** — per-request and aggregate are separate numbers and are reported separately.
- **Cold load time** — its own metric. Never folded into the first request.
- **Peak memory** — `footprint -p <pid>`. **Never `ps` RSS**: Metal buffers, mmap'd weights, and wired GPU memory account inconsistently under MLX.
- **On-disk size** — includes sidecar files (e.g. JANGTQ's runtime sidecar).

Every measured run pins temperature 0, a fixed seed, a fixed chat template, and a fixed
output length, and records every runtime's version. Runtimes ship different default
`top_p` and `repetition_penalty`; leaving them unpinned invalidates the comparison.

Raw observations are never discarded. Summaries must stay recomputable from them.

## Hard boundaries

- **`--cells a,b,c` is the only cell-selection mechanism.** The predecessor project built six overlapping ones across ~3,700 lines. Any second mechanism gets deleted.
- **No governance layer.** No plan hashing, no sealed evidence bundles, no single-use action grants, no operator policy, no workspace scaffolding, no `doctor`. A directory name plus `results.jsonl` is the right amount of provenance for a single-user Mac tool.
- **No new dependency** without naming, in the commit message, what it replaces.
- **No model downloads.** v1 runs only on artifacts already in `~/.cache/huggingface/hub`. Free disk is 36 GiB.
- **No accuracy scoring in v1.** It is out of scope until v1 ships, however tempting.
- **Target size is ~1,000 lines.** If a module is growing past its share, that is the signal to stop and ask, not to keep going.

## Runtime hazards, already paid for

- **OptiQ** flips `--stream-experts auto` on when `model_disk_bytes > 0.70 * total_RAM`. Identical weights then decode roughly 5× slower, with nothing in the artifact explaining it. Pin the flag explicitly.
- **Osaurus takes no tuning flags.** Everything that determines what you measure lives in `~/.osaurus/config/*.json` and an app plist. Snapshot it and diff against a checked-in baseline before every run.
- **oMLX** must be given a per-run temporary model catalog so only the cell's model is visible; otherwise it may serve something other than what you think.
- **oMLX's SSD prefix cache survives restarts** and consumes real disk. Clear it between cold-cache runs.
- **Ports:** Osaurus 1337, `optiq serve` 8080, `mlx_lm.server` 8081, oMLX 8100. A run that does not release its port has failed, whatever else it reported.
- **A cell that produces incoherent output has FAILED, however fast it was.** Verified 2026-09-15: stock `mlx_lm.server` loads `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` in 4s, returns HTTP 200, generates a clean 64/64 tokens — and the text is mixed-script token salad with replacement characters. Nothing errored. A speed-only harness would have recorded that cell as healthy with excellent throughput. Every measured cell therefore passes a **coherence gate** before its numbers count, and a cell that fails the gate reports `FAIL` with its sample output, never a tok/s figure. This is not accuracy scoring (deferred to v2) — it is a floor, and it is cheap.
- **Exactly one model is resident at a time.** Never start a second runtime while another holds weights. On 64 GB of unified memory a 35B MoE is ~20 GB resident; two at once saturates memory, forces compression and swap, and silently corrupts every number in the run — the measurement would still complete and still look plausible. `measure.py` stops the previous runtime and confirms its port is free *before* starting the next. This is not an optimization; a run that violates it is void.
- **Thermal.** An M2 Max in a laptop chassis throttles under sustained inference. Interleave cell order, insert cooldowns, record drift. Walking cells in config order aliases thermal drift perfectly onto runtime identity.

## Delegation contract

Implementation is delegated to Command Code workers on `deepseek/deepseek-v4.1-flash`
via `cc-agent`. Claude Opus 5 orchestrates and is the final reviewer.

A worker dispatch always carries: the plan's acceptance criteria, the exact files it may
touch, and "touch nothing else."

A ticket closes only when the coordinator has **personally observed** the diff and a
green test run. **A worker's report is not evidence.** The predecessor project recorded a
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
is byte-identical on every dispatch, so DeepSeek V4.1 Flash bills it as a cache read at
$0.003/M rather than fresh input at $0.15/M — a 50x difference on the part of the prompt
that never changes. Order-specific text goes after it, never before: anything prepended
breaks the shared prefix and every order that follows pays full price.

Editing PREAMBLE.md costs one full re-read on the next dispatch. Edit it when the standing
rules actually change, not to tidy wording.

Traps worth keeping:

- `cc-agent` hardcodes `--max-turns 40`. Scope each dispatch to one deliverable and forbid
  tangents explicitly.
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
