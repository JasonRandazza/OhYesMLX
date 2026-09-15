---
description: "OhYesMLX — session handoff, 2026-09-15"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-15

Written at the end of the founding session. Read this, then `.paul/STATE.md`, then
`AGENTS.md`. Everything else is reference.

## Where the project is

Repo: **https://github.com/JasonRandazza/OhYesMLX** (public, MIT). All work is on `main`.

Phases 1 and 2 are complete. Phase 2.1 (the coherence gate) is one worker-round from done.
**199 tests pass.** Eight modules, ~2,900 lines of source.

The project replaces `~/Dev/active/local-model-runtime-evaluation-harness` (LMRE), which
is **not yet archived** — its `transport.py`, flag pins, and research notes have been
ported, but leave it in place until Phase 4 confirms nothing else is needed.

## The three things that matter most

**1. A fast cell that emits garbage is a failed cell.** Stock `mlx_lm.server` loads
`Jundot/Qwen3.6-35B-A3B-oQ4-mtp` (256-expert MoE) in 4 seconds, returns HTTP 200, generates
a clean 64/64 tokens at full throughput — and the text is mixed-script token salad with
replacement characters. Nothing raised. Nothing timed out. A speed-only harness would have
recorded it as the healthiest, fastest row in the table. This is why the coherence gate
exists and why it precedes all measurement. Evidence:
`docs/research/2026-09-14-oq-portability-spike.md`, section "Round 2".

**2. Vary one thing at a time — and JANG cannot obey that rule.** JANG loads in no runtime
that loads the other formats. Three oMLX support PRs are open and unmerged, the maintainer
objected on the record, and JANG's own card says it "requires our custom loader" and is
"meant to be run in vMLX". It is a runtime+format bundle, not a quantization you can
isolate, so it gets its own labelled study after v1 — never a row on either axis.

**3. The format axis is the unoccupied ground.** `mlx-Chronos` already publishes a
runtime-axis protocol. No published format comparison holds the runtime constant. Lead with
the format axis; cite mlx-Chronos on the runtime axis rather than pretending to be first.
Evidence: `docs/research/2026-09-15-prior-art.md`.

## What to do next

**Phase 2.1 — finish the coherence gate (issue #7).** A worker is mid-flight rewiring it.
The gate judges the *measured responses*, makes zero extra transport calls, and fails a cell
by majority rule. Verify the diff and the suite yourself, then commit and close #7.

**Phase 3 — the format axis.** Download and run:

| | Model | Formats | GB |
|---|---|---|---|
| Dense | `Qwen3.5-4B` | stock-4bit, oQ4, oQ4e, OptiQ | 13.4 |
| MoE | `LFM2.5-8B-A1B` (32 experts) | stock-4bit, oQ4, oQ4e, OptiQ | 20.2 |

Exact repo ids are in `docs/research/2026-09-15-small-model-candidates.md`. Both fit the
36 GiB disk at 33.7 GB combined. **Carry the standing caveat in every table:** LFM2.5 has 32
experts, the failing checkpoint has 256, so a clean result validates the machinery and does
not exonerate stock mlx-lm on high-expert MoE.

**Phase 4 — the 256-expert question.** One cached artifact, two runtimes, coherence as the
outcome, **zero downloads**. This is the highest-value cheap experiment available.

## How this project is run

- **PAUL is the only spine.** `.paul/STATE.md` is the single state store. No `CONTEXT.md`,
  no ADRs, no second handoff document. If a second state file appears, delete it.
- **Delegate everything to Command Code.** `cc-agent <implement|refactor|explain|review>
  '<task>'`, running `deepseek/deepseek-v4.1-flash` at `max` reasoning effort (pinned in
  `~/.commandcode/config.json`). Claude tokens are the scarce resource; DeepSeek tokens are
  not. Run many sessions concurrently.
- **Opus is manager and final reviewer only.** Never accept a worker's word. Re-run the
  suite yourself with
  `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`, and read the
  diff. Do heavy lifting only when a worker is blocked by permissions or ships something
  that fails review.

## Traps that cost real time in this session

- **`cc-agent` hardcodes `--max-turns 40`.** Four workers hit it mid-task. Scope each
  dispatch to one deliverable and explicitly forbid tangents ("do not analyze tensors"), or
  drive `command-code` directly with a bigger budget.
- **`cc-agent explain` and `review` run in `--permission-mode plan` and cannot write.** A
  research task that must produce a file needs `implement`. Two research sessions were lost
  to this.
- **The collateral-deletion guard is unreliable under fan-out.** It compares definition
  snapshots before and after, so concurrent workers' files register as deletions. Verify
  against `git` instead.
- **Workers block well — let them.** Three separate BLOCKED reports found genuine
  contradictions in tickets I wrote. One measured four wiring variants and reported pass
  counts for each. Treat a BLOCKED as a finding, answer the question, and re-dispatch.
- **Pin interfaces before fanning out.** `docs/interfaces.md` is what let five workers build
  five modules concurrently that actually composed. The coupling is shapes, not files.
- **Readiness comes from the log, never the port.** `mlx_lm.server` binds its port and logs
  "Starting httpd" even after its load thread has died, so a POST connects and hangs forever.

## Machine state

- 36 GiB free on the internal SSD; `/System/Volumes/Data` 96% full. A disk audit is running
  (`docs/research/2026-09-15-disk-audit.md` when it lands). Jason is clearing JANG and
  LMRE-era models by hand and installing vMLX.
- The external drive holding `/Volumes/Storage` and Time Machine is **offline** — one
  physical HDD split two-thirds Time Machine, one-third storage, not accessible right now.
- Installed: Osaurus 0.25.3, oMLX 0.6.4, mlx-optiq 0.5.6, `llama-server`. **Not** installed:
  LM Studio. vMLX pending.
- `mlx-lm` 0.31.3 lives only in `/tmp/mlxspike` (the spike venv) and inside oMLX's bundle.
  It ships `gemma4` and `gemma4_text` but **not** `gemma4_unified`, which is why the gemma
  family was dropped as hero model.

## Open issues

- **#1** — the portability spike. Answered (LOADS, with garbage output). Close it after
  folding the verdict into the roadmap; that is already done, so it can simply be closed.
- **#7** — the coherence gate. In flight.
