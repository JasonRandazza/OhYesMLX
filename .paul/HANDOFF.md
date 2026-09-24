---
description: "OhYesMLX — session handoff, 2026-09-24 evening (v3.1 Hardening: Phase 4 code complete, sweeps not yet run)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-24 evening (Phase 4 code complete; sweeps tonight)

> Read this, then `.paul/STATE.md` (Current Position, Decisions 122–123), then `AGENTS.md`.
> STATE wins on conflict. The previous handoff is
> `.paul/archive/2026-09-24-handoff-morning-phase3-closed.md`.

## Where things stand

Phase 4 of v3.1 Hardening is **code complete and not yet exercised live**. Jason approved all
four proposed items and the mixed-channel TTFT refusal this morning; each landed as its own
commit, reviewed by the coordinator with a green suite. **Tests: 618 pass** (543 at the start of
the day). The measurement half of Phase 4 — the overnight sweeps — is what remains, and Jason
plans to run it tonight.

`git log origin/main..main` shows what is unpushed. Jason pushed the first batch mid-session; the
Phase 4 commits after `cb0bcb1` were local at the time of writing — check before assuming.

| commit | what |
|---|---|
| `e57775d` | Decision 122: runtime-axis TTFT and prefill orderings refuse rows timed on mixed channels (content vs reasoning). `report.CHANNEL_DEPENDENT_RANKS`; new row key `timing_channel`; the group lists values without positions and the recommendation is "none". |
| `360ca81` | AGENTS.md delegation text follows the fleet profile map (`implement`/`refactor` → DeepSeek v4.1 flash, `test`/`explain` → MiMo flash, `review` → MiMo pro; Luna explicit-only). |
| `3a47e12` | `docs/research/2026-09-24-kv-quant-surface.md`: the KV-quant control surface of every runtime, from source. |
| `eec6480` | `--kv-quant off\|affine8\|affine4` header pin. |
| `c33edc4` | The 2026-09-20 KV paper's vMLX rows are marked an inert codec; runtime notes corrected (`docs/runtimes/{optiq,vmlx,osaurus}.md`). |
| `3310e33` | `--mtp-depth off\|1\|2\|3` and `--stream-experts off\|on` header pins. |
| `d868f56` | `run --workloads multiturn`: ten fixed turns of one pinned conversation. |
| `a376728` | STATE/ROADMAP: Phase 4 code complete; Decisions 122–123. |

## What each Phase 4 setting does

All three pins follow the `--cache-state` pattern: a `run` flag recorded in the header, a
member of `report.PIN_FIELDS` / `ABSENT_PINS` / `SWEEP_PINS` / `SWEEP_VALUES` (so
`sweep --varying <pin>` joins runs that differ only in it), a `Runtime.<pin>_refusal()` asked
before start that turns a cell into **N/A with the reason**, and an absent pin (`None`) that
leaves every start command byte-identical to before. The rationale for each refusal is written
once, in `ohyesmlx/runtimes.py`, at the refusal.

### `--kv-quant off|affine8|affine4` (study 03-05)

- Renamed from the proposed `fp8`/`int4` on evidence: **no runtime here has a float8 KV codec**.
  Every codec in the set is MLX affine integer quantization (`docs/research/2026-09-24-kv-quant-surface.md` §2).
- **Only OptiQ quantizes the live cache** (`--kv-bits 8|4 --kv-group-size 64`).
- **vMLX's q4/q8 applies only to the prefix-cache copy**, and the harness has run with
  `--disable-prefix-cache` since 2026-09-15 (vMLX `scheduler.py:1393-1404`, `:2444-2458`). vMLX
  accepts only an explicit `off` (passing `--kv-cache-quantization none`) and refuses codec values.
  Consequence: **the vMLX rows of the 2026-09-20 KV paper measured nothing** — the paper now says so;
  its numbers are kept, not rewritten.
- mlx-lm and oMLX accept `off` only. Osaurus accepts `off` only when `cache.liveKVCodec ==
  engine_selected`.
- So a KV-quant sweep is effectively an **OptiQ sweep**; the other runtimes contribute `off` rows or N/A.

### `--mtp-depth off|1|2|3` (study 03-06)

- vMLX only. At depth N the start command drops `--disable-native-mtp` and passes
  `--native-mtp-depth N --native-mtp-depth-policy fixed`.
- `vmlx_mtp_refusal(artifact_dir)` is a static check of the bundle: config.json present, family
  wired in vMLX, MTP not declared dropped, MTP layers declared, and `mtp.*` tensors present in
  `model.safetensors.index.json`. A bundle without heads would decode plain autoregressive and
  publish as MTP; it is N/A instead.
- **Checked this evening against every snapshot in the HF cache: only
  `JANGQ-AI/Qwen3.5-4B-JANG_4S` passes.** The 35B MTP bundle the paper used,
  `Jundot/Qwen3.6-35B-A3B-oQ4-mtp`, is no longer on disk (its cache directory is a 4 KB stub), and
  the paper found it incoherent under vMLX with MTP both on and off anyway. Run the MTP sweep on
  the 4B JANG_4S; do not download the 35B bundle for it.
- Acceptance rate is a runtime self-report; it is recorded, not treated as a measurement.

### `--stream-experts off|on` (study 03-03)

- OptiQ: `--stream-experts` for `on`; `--no-stream-experts` for `off` **and** when absent (the
  existing internal pin stays — AGENTS.md hazard: OptiQ auto-enables streaming at 70% of RAM).
- vMLX: `--flash-moe` for `on`.
- Both runtimes can silently fall back to loading everything. So after start,
  `stream_experts_missing()` reads the head of the server log (`LOG_HEAD_BYTES` = 1 MiB) and the
  cell is **FAIL, with the log quoted,** unless the banner is there: OptiQ needs both
  `SSD expert streaming: on` and `pre-loaded`; vMLX needs `Flash MoE enabled:`. The runtime is still
  stopped in `finally`. `Handle.log_path` was added for this.

### `run --workloads pinned|multiturn` (study 03-04) — not a pin

- Default `pinned` is today's three shapes, byte-identical. `multiturn` swaps in ten workloads,
  `turn-01`…`turn-10`, all `max_tokens=128`. It is mutually exclusive with `--prompt-tokens`.
- `cli.DIALOGUE` holds the ten probe questions plus **nine fixed literal assistant replies**. The
  2026-09-20 probe fed each runtime its own replies back, so every runtime saw a different history —
  two things varied at once. Fixed replies make turn N the same prompt on every runtime.
- The header's existing workload list is the provenance; no new pin was needed.

### Not re-run: 03-07 speculative draft

It needs two resident models by design, which breaks the one-model rule. It stays a caveated
script study.

## Tonight: the sweeps

**No Phase 4 runner scripts exist yet.** The first job is writing them — delegate it
(`CC_AGENT_MAX_TURNS=300 .paul/orders/dispatch.sh implement <order>`), and land it **before**
the grid starts: AGENTS.md forbids editing `ohyesmlx/*.py` or running tests while a grid runs.
Model them on `scripts/run_sweep_cache.sh`, which already has the port sweep, the stale-Osaurus
sweep by full executable path, the Osaurus baseline snapshot/restore with `cmp`, the abort trap,
one log per run, and `OUT=` override. `scripts/gridspec-35b.sh` resolves the 35B snapshot paths.

Suggested runs, in the order of value (cheapest first is also fine for a first live check):

| study | runtimes × artifact | varying | extra | expected N/A |
|---|---|---|---|---|
| 03-05 KV quant | all five × `oq4` 35B (`$Q4`) | `kv_quant` off/affine8/affine4 | `--prompt-tokens 16384` and `32768` | affine8/affine4 on everything but OptiQ |
| 03-06 MTP | vMLX × `Qwen3.5-4B-JANG_4S` | `mtp_depth` off/1/2/3 | — | none (it passes the refusal) |
| 03-03 streaming | OptiQ, vMLX × `stock4bit` 35B (`$S4`) | `stream_experts` off/on | — | mlx-lm, oMLX, Osaurus |
| 03-04 multi-turn | all five × one 35B artifact | runtime axis, `--workloads multiturn` | — | none expected |

Then `ohyesmlx sweep --varying <pin>` over each study's results directory.

Things to watch in the first results, because none of this has run live:

- a streaming `on` cell that FAILs for a missing banner — read the quoted log before believing
  either the harness or the runtime; the banner strings were taken from source and recorded logs;
- an OptiQ `affine4` cell failing the coherence gate — that is a result, not a harness bug;
- the TTFT refusal (Decision 122) firing on the multi-turn runtime-axis report, which is expected
  on the Qwen artifacts (OptiQ times on content, the other four on reasoning).

Also queued for a quiet night: **the third 35B replicate**, which settles whether this morning's
8–27% level shift in mlx-lm/oMLX/vMLX is real (about 2.3 h):
`OUT=results/harden-35b-r3 sh scripts/run_grid_35b.sh`.

The machine must be quiet: no pytest, git, downloads, or Command Code workers while any of this runs.

## Deferred

- The single-run `render_markdown` leaderboard is guarded by neither A7 (no cross-runtime
  `peak_mb`/`cold_load_s` ordering) nor the Decision 122 channel refusal. Only the grid/sweep
  paths are. Worth a small order once the sweeps land.
- The Luna route trial is still owed (Luna is explicit-only now; one data point: it ran out of
  turns on Phase 2 and left two duplicated definitions).
- Phase 4 order files are in `.paul/orders/p4-*.md`; their `.log` files are untracked worker
  transcripts and can be deleted.

## Working notes carried forward

- **Offload to Command Code.** Claude tokens are scarce: Opus writes orders, reviews diffs and
  runs the suite; workers write code. Always set `CC_AGENT_MAX_TURNS` — 300 for code orders, 400
  for an order that spans two pins or several modules, never the default 40. One worker hit 200
  mid-edit today with no report; a 400-turn continuation order finished and trimmed it.
- A worker's BLOCKED is a finding: today's multi-turn worker correctly stopped on a snapshot test
  (`tests/test_report.py`, run-flag list) outside its allowlist.
- **Graphify:** the repo had no git hooks, and the Claude-side hook fires only on `.md` edits. On
  2026-09-24 `graphify hook install` added post-commit/post-checkout hooks; every commit now
  rebuilds `graphify-out/` in the background (log: `~/.cache/graphify-rebuild.log`). Uncommitted
  `.py` edits still need `graphify update .` by hand. Graphify's merge driver created a
  `.gitattributes`; Jason deleted it — if it reappears, it is harmless and untracked.
- Test command: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.

## Host state

- Google Drive was quit for the 2026-09-23 grids — relaunch it if it is still off (quit it again
  before tonight's run; it held ~100% CPU).
- About 100 GiB free after the Time Machine snapshot purge; check `df` before any fetch.
- Osaurus is out of `~/.commandcode/mcp.json` and Login Items (both relaunched the app).

## Next moves

1. Push any unpushed commits (`git log origin/main..main`).
2. Dispatch the Phase 4 runner scripts; review; commit; then start the sweeps on a quiet machine.
3. Morning after: `sweep --varying` reports per study, a research writeup per study under
   `docs/research/`, and STATE updated (Phase 4 closes when the studies are written up).
4. Third 35B replicate on the next free quiet night.
