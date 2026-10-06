# Plan: MTPLX as the sixth runtime (proposal, 2026-10-06)

Status: **PROPOSAL — nothing here is approved.** AGENTS.md requires Jason's yes before a new
surface (a `Runtime` class, a pin, a transport field). Decisions needed are listed in §7.

Built from three research documents, each read by the coordinator on 2026-10-06 and each
labelling claims VERIFIED / CLAIMED / INFERRED:

- `2026-10-06-mtplx-architecture.md` — source read at `youssofal/MTPLX@9882703` (v2.12.2).
- `2026-10-06-mtplx-surface.md` — CLI, API, ports, hooks.
- `2026-10-06-mtplx-landscape.md` — models, claims, bundles, community, which axis.

No MTPLX process has been started and no model loaded. Every "will load / will degrade" below is
a source-level prediction over real config and tensor bytes. Phase 1 turns predictions into
observations before any code is written.

## 1. What MTPLX is, in the harness's terms

A native Mac app plus a CLI (`mtplx serve`) that speculates with the model's **own MTP heads**
(no draft model) on stock `mlx==0.32.2`. Apache-2.0, one primary maintainer, active (2,000+
commits, 16 open issues, 27 open PRs). OpenAI-compatible HTTP, one model resident per server,
serial scheduler by default. Published claims (2–3× plain MLX, ~23% over oMLX) are single-machine
(M5 Max 128 GB) on MTPLX's own packs: **read, not reproduced, and not comparable to this M2 Max**.

Why it fits the harness: it is a *runtime*, and the question people are asking ("MTPLX or oMLX?")
is exactly the runtime axis. Why it is not a drop-in: MTP is its product, and MTP needs a head
the artifact may not carry.

## 2. Axis discipline (the part that decides everything)

MTPLX's own packs (`Youssofal/*`) change runtime, quant format, conversion provenance and chat
template together. Putting one in a runtime-axis column attributes nothing. The research found a
cleaner route on artifacts we already own:

| Artifact (already on disk) | MTP head | Predicted MTPLX behaviour | Use |
|---|---|---|---|
| `mlx-community/Qwen3.5-4B-OptiQ-4bit` | sidecar, 29 tensors, **exact** match to MTPLX's canonical set | attaches (unrun) | **primary** |
| `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | sidecar, 37 tensors, exact match | attaches (unrun) | replicate, later |
| `JANGQ-AI/Qwen3.5-4B-JANG_4S` | embedded, 31 tensors, exact match | plausible; trunk load unproven | **bridge to vMLX ladder** |
| Qwen3.5-4B-oQ4e, Qwen3.6-35B-oQ4 | declared, none shipped | **warns and serves AR silently** | AR control only, log-gated |
| Qwen3.5-4B-oQ4 (no index) | declared, none shipped | raises at load | skip |
| LFM2.5-8B-A1B (all five) | none exists | AR-only family | AR only, never an "MTP" cell |

Lineage caveat: OptiQ's `optiq/runtime/mtp/` is vendored MTPLX code, so MTPLX-vs-OptiQ on an
OptiQ pack compares two engines that share ancestry and a sidecar format. It is still one
variable (the runtime), but it is not two independent MTP implementations. vMLX is the
independent one, which is why the JANG_4S bridge matters.

## 3. The people's question, answered without a second variable

"MTPLX vs oMLX" has a one-variable form: **same artifact, MTP off, runtime varies** (AR column
in each), then MTPLX's MTP depths as a separate, labelled factor inside its own column. That
separates "is the engine faster at plain decode" from "does MTP buy anything", which the vendor
comparison pages blur. It needs one artifact both can load; whether oMLX loads the OptiQ 4B pack
is a Phase 1 probe item (oMLX served `oQ4` bundles in earlier work; the OptiQ pack is unchecked).
If no common artifact exists, say so and do not substitute.

## 4. Phases

**Phase 0 — housekeeping (before any of this).** Finish the v3.1 → 0.3.1 bump already pending in
STATE. MTPLX is v4 work, not v3.1.

**Phase 1 — load probes (observation only, harness unchanged).**
- Install into its own venv, `~/.local/share/ohyesmlx/mtplx-2.12.2`, mirroring the mlx-lm venv
  pattern. Reason recorded: package install only; **no model downloads**, all artifacts are on disk.
  Check `df` first. Nothing else runs on the machine during a probe.
- One model resident at a time. For each artifact in §2: start, record raise / degrade / attach,
  one 64-token request, coherence read, stop, confirm the port is free.
- Close the open items the research could not: (1) JANG_4S trunk load (tensor prefix, quant
  bookkeeping); (2) the "head drafted" receipt — candidate is `mtplx_stats.mtp_depth` /
  `accept_rate` in the final SSE chunk; a **0%-acceptance head that loads cleanly is a real
  failure mode** (default `hidden_variant` / `concat_order` for sidecars with no contract
  block), so load success is not enough; (3) whether a zero RAM-bank budget honestly disables
  warm restore (gates `cache_state=off`); (4) seed does not change scheduling (inferred); (5)
  `/v1/models` handling of a mismatched `model` string; (6) the thinking default per family;
  (7) the oMLX-loads-OptiQ-4B question from §3.
- Output: `docs/runtimes/mtplx.md` (capability reference, the pattern every other runtime has)
  and a go / no-go per cell set. If the OptiQ sidecar attaches but acceptance is ~0%, that is a
  finding and the plan stops there.

**Phase 2 — harness code (worker-delegated, new surface ⇒ needs Jason's yes first).**
- `Mtplx` subclass in `ohyesmlx/runtimes.py` (no new module): `start_command` as in the surface
  doc §10 (`--host 127.0.0.1 --port <free> --model-id <pin> --no-stats-footer`), `/health` +
  `/v1/models` readiness, version off `mtplx --version`, `mtplx stop` plus the usual
  `await_port_free`, no request seed (greedy-inert; OptiQ's seed exception does **not** apply).
- **Port:** MTPLX's default 8000 is vMLX's. Assign a distinct port (proposal: 8200) in the
  AGENTS.md hazard list.
- `mtplx_mtp_refusal`, mirroring `vmlx_mtp_refusal` / `optiq_mtp_refusal`: a depth pin is gated
  by a real load observation, never by the config's declaration.
- Depth mapping: `--no-mtp` for off; `--depth N --generation-mode mtp` otherwise; scheduler
  declared serial. Family caps recorded.
- `kv_quant`: MTPLX's q8/q4 is symmetric per-head with fp32 scales, not MLX affine. Refuse the
  existing values rather than rename; a codec cell would need a new value (a header pin, so a
  separate ask).
- The receipt: transport must keep `mtplx_stats` from the final SSE chunk in the raw row. This
  is a new field on the observation (surface change; raw rows are never discarded, so the full
  chunk is kept and the summary is recomputable).
- Tests, `graphify update .`, sampler survey written into AGENTS.md before the first measured
  cell (Decision 131). Survey so far: temperature honoured, penalties default 0.0, no
  `generation_config` penalty path, loop guard off. To record per artifact: thinking default,
  resolved profile.

**Phase 3 — cells (each one confirmed with Jason before launch).**
- **A — runtime axis, one artifact:** `Qwen3.5-4B-OptiQ-4bit`, columns `optiq` and `mtplx`,
  depth off/1/2/3, cache off, temp 0, seed recorded per row (OptiQ's MTP path sends one, MTPLX
  does not; the conditions block says so, not a footnote).
- **B — depth ladder inside MTPLX.** The published vMLX ladder found depth 1 buys nothing and
  depth 3 costs 18% on JANG_4S; MTPLX defaults to depth 3. First cross-engine test of whether
  that default survives M2 Max.
- **C — bridge, only if JANG_4S loads:** `vmlx` vs `mtplx` on the same embedded head, depths
  off/1/2/3. The cleanest independent-implementation comparison available.
- **D — the AR "vs oMLX" column** from §3, if a common artifact exists.
- **Never:** a `Youssofal/*` pack in a runtime column; an MTP cell on oQ4/oQ4e/35B-oQ4 without
  the log gate; an LFM2.5 MTP cell; vendor numbers in our tables without lane, chip, pack and
  version restated. A Youssofal pack may run later as a separate, explicitly two-variable
  "what a user gets out of the box" lane, labelled as not a ranking.

**Phase 4 — records.** Write-up under `docs/research/`, STATE decisions, AGENTS.md port and
runtime lines, Deep Wiki update (finding + roadmap), and the README runtime table.

## 5. Cost and risk

- Phase 1 is cheap (an install, about a dozen short loads) and produces the go / no-go.
- Largest risk: silent 0%-acceptance or silent AR degrade producing a plausible-looking MTP cell.
  Mitigation is the refusal gate plus the receipt; this is the class of failure AGENTS.md exists
  for.
- Bus factor is one maintainer with a fast release cadence. Pin the version of record in every
  row; a new build joins nothing earlier (the Osaurus lesson).
- Disk: no model downloads planned. The venv is small; MTPLX's SSD session cache must be pointed
  at the per-run scratch so `stop()` removes it.

## 6. Delegation

Phase 1 is run by the coordinator (it starts servers; workers do not). Phase 2 goes out as
dispatch orders with exact file lists, one deliverable each; the coordinator personally observes
the diff and a green `pytest` before closing. Phase 3 launches only on Jason's confirmation, with
nothing else on the machine.

## 7. Decisions needed from Jason

1. Version label: treat as **v4.0** (new runtime, new axis row) after the 0.3.1 bump?
2. Approve Phase 1 (venv install at `~/.local/share/ohyesmlx/mtplx-2.12.2`, no model downloads)?
3. Pre-approve the Phase 2 surfaces *conditional on Phase 1 passing*: an `Mtplx` runtime class,
   port 8200, `mtplx_stats` kept in the raw observation?
4. Is a later out-of-the-box "Youssofal pack" lane (labelled two-variable, no ranking) wanted, or
   keep MTPLX strictly one-variable?
