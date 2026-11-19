# OhYesMLX

**Honest benchmarks for local LLM serving on Apple Silicon. One variable at a time.**

> A Mac user can point this at their own machine and find out whether their serving
> runtime or their quantization is what's actually costing them speed and memory.

OhYesMLX measures local LLM serving on Apple Silicon — speed, memory and on-disk size —
across the MLX serving runtimes and the specialized quantization formats built for them. It
drives every runtime over its OpenAI-compatible HTTP endpoint, samples macOS memory while
the run is in flight, and joins the results into one leaderboard table.

Published MLX numbers routinely change two variables at once — a different runtime *and* a
different quantization — and then credit the difference to whichever one the author is
promoting. OhYesMLX measures one variable at a time, and says so on every table it prints.

The project ships two front ends over one measurement core:

| | What it is | Who it is for |
|---|---|---|
| **The app** (`app/`, v5.0) | A SwiftUI app that scans this Mac, guides engine installs, recommends models that fit, downloads them, and runs a short benchmark. | A Mac owner who does not use a terminal. |
| **The CLI** (`ohyesmlx/`) | The harness: lifecycle over the serving engines, SSE measurement, macOS memory sampling, the result join, and the published grids. | Anyone reproducing or extending the research. |

The CLI is the measurement source of truth. The app is a client of it: it starts the same
Python backend (`ohyesmlx app`) and reads its localhost API, so a quickbench number and a
published number come from the same code path.

## The rule: vary one thing at a time

Every run declares which axis it varies and holds the other constant:

- **Runtime axis** — the quantization format is fixed; the serving runtime varies.
- **Format axis** — the serving runtime is fixed; the quantization format varies.

A result that varied both is not a result. The published MLX numbers that circulate mix the
two, which is why they cannot say whether the server or the weights made the difference.

| Study | Held constant | Varied | Answers |
|---|---|---|---|
| **A — runtime axis** | the quantization format — one artifact for the whole run | the serving runtimes: `mlxlm`, `osaurus`, `omlx`, `optiq`, `vmlx` | Does the *server* matter? Swift vs Python overhead, continuous batching, prefix and KV caching. |
| **B — format axis** | the runtime — whichever one you select, the same for every cell in the run | mlx-lm 4-bit, oQ, OptiQ, JANG | Does the *quantization* matter? |

The matrix is **ragged, not square.** Not every format loads in every runtime, so a full
cross-product is impossible and a diagonal tells you nothing about either axis in isolation.
What loads where, as of today:

| Format | Stock `mlx_lm.server` can load it? | Registered runtimes measured with it here |
|---|---|---|
| mlx-lm 4bit/8bit (affine) | yes | all five: `mlxlm`, `omlx`, `optiq`, `vmlx`, `osaurus` |
| oQ / oQe / oQ+ | **yes** — plain mlx-lm safetensors | the same five |
| OptiQ | yes | the same five — `optiq` is the runtime built for it |
| JANG / JANGTQ | **no** | `vmlx` and `osaurus`; no other registered runtime loads it |
| GGUF | no | none of the five — GGUF needs llama.cpp or LM Studio, which this harness does not drive |

Anything that varies both axes at once is a press release, not a benchmark.

## The app (v5.0)

The app is a double-click path to the same answer. It is a SwiftUI client over a local
Python backend; it never measures anything itself.

- **Scan** — reads the Mac's chip, unified memory and free disk, which is what every
  recommendation is fitted to.
- **Engines** — detects the serving engines already installed and can install the ones that
  are not, from hash-pinned wheels, with the user's consent. An install refuses any file
  whose hash is not in the release's SBOM.
- **Models** — a catalog of models with a recommender that says what fits this Mac, and a
  downloader that writes into the standard Hugging Face cache.
- **Quickbench** — two single-axis stages: the installed engines on the chosen model's
  format, then the winning engine across that model and its sibling formats. Every number
  is labelled *quick: measured on this Mac* and never joins the published tables.

The backend is reachable on its own, behind a per-launch token printed on stdout:

```bash
ohyesmlx app --port 0 --lock-dir "$HOME/Library/Application Support/OhYesMLX"
```

### Distribution status

The release artifact is `dist/OhYesMLX-0.3.0.dmg`. It is **ad-hoc signed and not
notarized**, so macOS blocks the first launch until the user approves it:

1. Drag **OhYesMLX** onto the **Applications** folder in the disk-image window, then eject
   the image. Running it from Downloads, the Desktop or the image itself hits Apple's
   translocation path and the app refuses to install anything from there.
2. The first open shows *"Apple could not verify"* with **Move to Trash** and **Done**.
   Click **Done** — not Move to Trash.
3. System Settings > Privacy & Security > Security has an **Open Anyway** button for
   OhYesMLX. Click it, confirm, then open the app from Applications once more.

The whole procedure, including what the app writes to disk and how to remove all of it, is
in [docs/release/gatekeeper.md](docs/release/gatekeeper.md).

### Building it

```bash
scripts/build_app.sh                  # dist/OhYesMLX.app, the DMG, its .sha256 and an SBOM
scripts/check_bundle.sh dist/OhYesMLX.app
```

`build_app.sh` builds the release Swift binary, bundles the pinned python-build-standalone
interpreter with the `ohyesmlx` package in its site-packages, signs inside-out, and puts the
result in a read-only disk image. `check_bundle.sh` re-checks every packaging rule on the
finished bundle. The Swift package lives at [app/](app/); `scripts/dev_backend_venv.sh`
makes the virtualenv a development backend runs from.

## The CLI

OhYesMLX is packaged under PEP 621 with **zero external runtime dependencies** — the Python
standard library only.

### Install

```bash
git clone https://github.com/JasonRandazza/OhYesMLX.git
cd OhYesMLX
python3 -m pip install -e .
ohyesmlx --help
```

Python 3.11 or newer. The harness measures on macOS Apple Silicon only; it reads memory
with `/usr/bin/footprint` and drives runtimes that are macOS applications.

### The studies

`--study` names the one axis a run varies; there is no diagonal and no combined mode.

```bash
ohyesmlx run --study format \
  --cells "stock4bit__mlxlm=/path/to/model-4bit,oq4__mlxlm=/path/to/model-oQ4" \
  --rank decode_tps

ohyesmlx run --study runtime \
  --cells "oq4__mlxlm=/path/to/model-oQ4,oq4__omlx=/path/to/model-oQ4" \
  --rank decode_tps
```

`--cells` is the **only** cell-selection mechanism. Each cell is
`<format>__<runtime>=<artifact dir>`, named one by one; there is no glob and no `--all`,
because `results/` accumulates runs from every session and a cell set assembled by wildcard
silently joins columns that never belonged together.

A run writes `results/<run-id>/results.jsonl` plus the rendered markdown leaderboard — the
report. The run header records every pin, every workload's messages and output cap, and
every runtime version, so a join compares what actually ran.

### Pins and sweeps

A sweep is several runs that differ in exactly one header pin, joined afterwards. The pin
flags are `--concurrency`, `--prompt-tokens`, `--cache-state`, `--kv-quant`, `--mtp-depth`
and `--stream-experts`; leaving a pin out pins nothing, and the header records `None`
rather than pretending the runtime's default is the pinned value.

```bash
# prompt-length sweep: one prefill shape sized to a length, in tokens
ohyesmlx run --study runtime --cells "oq4__mlxlm=/path/to/model-oQ4" \
  --prompt-tokens 4096 --rank ttft_p50_s

# the pinned ten-turn conversation, the same prompt on every runtime
ohyesmlx run --study runtime \
  --cells "oq4__mlxlm=/path/to/model-oQ4,oq4__omlx=/path/to/model-oQ4" \
  --workloads multiturn --rank ttft_p50_s

# concurrency: N requests issued together per batch
ohyesmlx run --study runtime --cells "oq4__mlxlm=/path/to/model-oQ4" \
  --concurrency 8 --rank aggregate_tps
```

`--workloads pinned` (the default) is the three shapes every column so far ran — `chat`,
`prefill`, `decode`. `--workloads multiturn` is ten turns, `turn-01`…`turn-10`, each one
turn longer than the last, with a fixed reply between them so turn N is the same prompt on
every runtime. The set is a **selector, not a pin**: the header records every shape it
measured.

### Joining: grid and sweep

```bash
ohyesmlx grid run_dir_1 run_dir_2 --rank decode_tps --out results/grid.md
ohyesmlx sweep --varying concurrency run_n1 run_n2 run_n8 --out results/concurrency.md
```

`grid` joins run directories that differ by format and runtime; `sweep` joins runs that
differ in exactly one named header pin — `concurrency`, `prompt_tokens`, `cache_state`,
`kv_quant`, `mtp_depth` or `stream_experts` — and refuses runs where any other pin
disagrees. Neither measures anything or starts a runtime: they read `results.jsonl` files
that already exist.

### Canary

An engine version bump is a claim, not a fact. `canary` measures one fixed cell per engine
on the decode workload and compares its decode tok/s and TTFT against the baseline the
manifest records for that engine:

```bash
ohyesmlx canary --yes
ohyesmlx canary --engines omlx,optiq --yes
ohyesmlx canary --engines omlx --record --allow-noisy --yes
```

Each engine gets one verdict — `no effect on our tables`, or `moved N%: re-run the grids
containing <engine>`. Nothing is written to the manifest unless `--record` is passed, and
without `--yes` the quiet-machine rule is printed and nothing starts.

### Quickbench from the CLI

```bash
ohyesmlx quickbench --repo <catalog repo id> --yes
ohyesmlx quickbench --repo <catalog repo id> --osaurus --yes
```

The same two-axis quickbench the app runs. `--osaurus` is required for OhYesMLX to pin
Osaurus's measurement-side host settings for its cells; without it Osaurus is skipped with
that reason.

## What is measured

The metric definitions are the project's own, written once in `AGENTS.md` and copied here.
They are not redefined per report.

- **TTFT** — request sent → first *content* token. Includes prefill. Reasoning tokens are
  not content. Exception: a response that streams only reasoning, or mirrors reasoning into
  content, is timed on the stream it produced (`transport.timing_channel`), and every such
  row is labelled "timed on reasoning channel".
- **ITL / TPOT** — mean gap between successive output tokens after the first.
- **End-to-end latency** — P50 / P90 / P99. Never report a bare mean.
- **Output throughput** — per-request and aggregate are separate numbers and are reported
  separately, because continuous batching wins one and loses the other.
- **Cold load time** — its own metric. Never folded into the first request.
- **Peak memory** — `footprint -p <pid>`, Apple's `phys_footprint`, what Activity Monitor
  shows. **Never `ps` RSS**: Metal buffers, mmap'd weights, and wired GPU memory account
  inconsistently under MLX. `peak_mb` is sound **within a runtime** and carries **no
  cross-runtime ranking**.
- **On-disk size** — includes sidecar files (for example JANGTQ's runtime sidecar), so no
  format is credited with a smaller footprint than it has.

Every measured run pins temperature 0 and a fixed output length, sends identical messages,
and records every runtime's version. **At temperature 0 no seed is sent**: greedy decoding
makes it inert, and a request that carries one forces mlx-lm and OptiQ onto their
sequential serving path, so a seeded harness never measures the batching path everyday
clients use. The one definition is `Runtime.request_seed`; every row records the seed it
actually sent as `request_seed`. OptiQ is additionally started with its sampler flags
pinned (`--temp 0 --top-p 1 --top-k 0 --min-p 0`), because `optiq serve` otherwise injects
an artifact's own `generation_config.json` sampling values into the command; vMLX is pinned
to a repetition penalty of 1.0. The other runtimes are asked for temperature 0 and nothing
else, so their `top_p` and `repetition_penalty` are whatever those servers default to —
which is why a row is read beside the runtime version it was measured under. The chat
template is each runtime's own.

Two rules sit above the metrics:

- **A fast cell that emits garbage is a failed cell.** Every measured cell passes a
  coherence gate before any number is published, and a cell that fails reports `FAIL` with
  its sample output, never a tok/s figure. Stock `mlx_lm.server` once loaded a 256-expert
  oQ4 MoE in seconds, answered HTTP 200 at full throughput and emitted token salad;
  nothing raised.
- **Raw observations are never discarded**, so every summary stays recomputable.

Only one model is resident at a time. `measure.py` stops the previous runtime and confirms
its port is free before starting the next: two engines at once saturate unified memory and
silently corrupt every number in the run.

## Supported runtimes and formats

The registry is `runtimes.RUNTIMES`: `mlxlm` (`mlx_lm.server`), `osaurus`, `omlx`,
`optiq` and `vmlx`. That is the whole of what this harness can drive, and therefore the
whole of what it can claim to have measured.

Architectures: any model can be benchmarked as long as it sits on local disk in the
standard Hugging Face / MLX layout (`config.json`, `tokenizer.json`, safetensors) and the
chosen runtime's MLX engine implements its architecture. That includes dense families
(Llama, Qwen, Mistral, Phi, DeepSeek-R1-Distill, Gemma 2) and mixture-of-experts families
(LFM 2.5, Qwen 3.6 MoE, Mixtral).

Quantization formats, stated for the five registered runtimes:

- **Standard MLX 4-bit / 8-bit (`mlx-lm` affine):** plain safetensors; all five load it.
- **oQ / oQe / oQ+:** plain MLX safetensors; all five load it.
- **OptiQ:** built for `optiq serve`; the other four have served it in the runs recorded
  here.
- **JANG / JANGTQ (`JANG_4S`, `JANG_2L`):** a proprietary quantized format that needs a
  JANG-aware runtime, which among the registered five means `vmlx` or `osaurus`. Not
  loadable in `mlxlm`, `omlx` or `optiq`. MLX Studio is a separate application outside this
  registry; no harness run drives it.

Per-runtime capability references, including what each engine pins and where its load
lands, are in [docs/runtimes/](docs/runtimes/). The shapes modules compose on are pinned in
[docs/interfaces/](docs/interfaces/).

### What does not work

- **Unsupported model types in stock MLX.** Architectures not yet implemented in the
  runtime's MLX backend cannot load. For example, `gemma-4-12B-it-qat`
  (`model_type: gemma4_unified`) is rejected by stock `mlx-lm 0.31.3`.
- **Non-MLX formats.** GGUF (llama.cpp), AWQ, GPTQ (CUDA) and EXL2 are not loadable by MLX
  runtimes.
- **Incomplete or omitted parameter weights.** Weights missing architecture-mandated
  tensor blocks fail loadability — for example dense OptiQ weights missing the vision
  parameter blocks a multimodal runtime like vMLX requires.
- **Speculative draft decoding on hybrid linear-attention.** Stock
  `mlx_lm.server --draft-model` refuses models using non-trimmable recurrent KV caches
  (hybrid linear-attention `ArraysCache`).
- **Non-macOS systems.** OhYesMLX requires macOS Apple Silicon unified memory and uses
  `/usr/bin/footprint -p <pid>` for true memory residency. Linux and Windows are not
  supported.
- **Anything else running during a measurement.** Nothing else runs on the machine while a
  cell is measured — not a test suite, not a download, not a build. The harness cannot
  detect contention, so this is a discipline rather than a check: a column measured while
  commits were pushed and the test suite ran beside it drifted 40% and would have inverted
  a format ordering that replicates across three codebases. Downloading weights while a
  measurement is in flight competes for the disk that cold load is timing.

## Published research

Every study is written up under [docs/research/](docs/research/), with its raw observations
kept under `results/`. The major papers:

**Foundations (v1)**

- [The oQ portability spike](docs/research/2026-09-14-oq-portability-spike.md) — whether
  the first format even loads across runtimes, cell by cell.
- [The grid's real shape](docs/research/2026-09-15-grid-loadability-probe.md) — which of
  the 20 format × runtime cells run at all, and why the predicted refusals were wrong.
- [Cold load is not one quantity](docs/research/2026-09-15-cold-load-is-not-one-quantity.md)
  — a lazy loader's `cold_load_s` is time-to-listening, not a load time.
- [The first live run](docs/research/2026-09-15-first-live-run.md) — the two FAIL rows
  that surfaced the transport defects.
- [Dense format axis](docs/research/2026-09-16-phase5-joined-grid.md) — one runtime held
  constant, four formats varied.
- [MoE format axis](docs/research/2026-09-16-moe-format-axis.md) — the same design on an
  MoE artifact.
- [Prompt-length sweep](docs/research/2026-09-16-prompt-length-sweep.md) — TTFT and
  prefill across prompt sizes.
- [Prompt length and context limits](docs/research/2026-09-16-prompt-length-context-limits.md)
  — what each engine does when the prompt exceeds its context.
- [Cold vs warm cache state](docs/research/2026-09-17-cache-state-split.md) — the same
  cells with prefix reuse off and on.

**JANG and accuracy (v2)**

- [Dense JANG study](docs/research/2026-09-17-dense-jang-study.md) — the proprietary
  format on a dense model, speed and memory.
- [MoE JANG study](docs/research/2026-09-17-moe-jang-study.md) — the same on an MoE
  artifact.
- [JANG cross-runtime synthesis](docs/research/2026-09-17-jang-cross-runtime.md) — what the
  two grids license and what they do not.
- [Accuracy, dense](docs/research/2026-09-18-accuracy-dense.md) and
  [accuracy, MoE](docs/research/2026-09-19-accuracy-moe.md) — MMLU, IFEval and GSM8K over
  the same endpoints.
- [Accuracy vs throughput Pareto](docs/research/2026-09-19-accuracy-pareto.md) — the
  quality-per-token frontier.

**Large models and dynamics (v3, v3.1)**

- [35B MoE serving](docs/research/2026-09-20-35b-moe-serving.md) — the large-model grid
  and its recommendations.
- [Cold vs warm load attribution at 35B](docs/research/2026-09-20-cold-warm-load-attribution-35b.md)
  — page cache, Metal accounting and the true cost of the first token.
- [Expert streaming under memory pressure](docs/research/2026-09-20-expert-streaming-high-memory-pressure.md)
  — what NVMe-backed experts cost.
- [Multi-turn conversation dynamics](docs/research/2026-09-20-multiturn-conversation-sweep.md)
  — how TTFT grows with the conversation.
- [Quantized KV caches](docs/research/2026-09-20-quantized-kv-caches.md) — MLX's affine
  codecs at 4 and 8 bits.
- [Native MTP](docs/research/2026-09-20-native-mtp-vmlx.md) and
  [speculative draft decoding](docs/research/2026-09-20-speculative-draft-decoding.md) —
  the two ways to draft tokens, measured apart.
- [Hardening validation grids](docs/research/2026-09-24-hardening-validation-grids.md) and
  [seedless validation grids](docs/research/2026-09-28-seedless-validation-grids.md) — the
  re-runs that hold the format orderings, without a seed.
- [Concurrency and batching](docs/research/2026-09-27-concurrency-batching.md) — per-request
  and aggregate throughput at N.
- [Cold-load ordering audit](docs/research/2026-11-19-cold-load-ordering-audit.md) — which
  published cold-load orderings the timed-window defect flips, and which hold.

## Lineage: OhYesMLX replaces LMRE

OhYesMLX is the successor to **LMRE — the Local Model Runtime Evaluation Harness**
([archived repository](https://github.com/JasonRandazza/local-model-runtime-evaluation-harness)).
LMRE was built from 2026-07-13 and released as v0.4.0 on 2026-08-07; it was archived on
2026-09-25, with its repository kept read-only.

By its own accounting LMRE reached 334 commits, about 21,800 lines of source and 774
passing tests — and no published benchmark table. Roughly 4,000 of those lines did the
measuring; about 16,000 governed permission to measure (plan hashing, sealed evidence
bundles, single-use action grants, operator policy and workspace scaffolding), and six
overlapping mechanisms selected which cells to run, across about 3,700 lines. Its design
paired each format with the runtime built for it, which meant a finished measurement still
could not say which variable caused a difference.

OhYesMLX is a second attempt at the same question made from what that taught, not a rewrite
of the code. **Ported and still running** (each credited in the source):

- **SSE streaming transport** — `ohyesmlx/transport.py`, ported near-verbatim. Every line of
  the stream loop is a bug someone already paid for.
- **Runtime start-command flag pins** — `ohyesmlx/runtimes.py`. They are not defaults, they
  are pins; they include OptiQ's `--no-stream-experts`, without which identical weights
  decode roughly five times slower.
- **Model-ID alias registry** — each runtime names the same model differently.
- **oMLX per-run model catalog** — without it oMLX may serve a different model from the one
  under test.
- **Osaurus settings attestation** — `ohyesmlx/osaurus_settings.py`. Osaurus takes no
  tuning flags, so its config files are snapshotted and diffed.

**Not carried over:** the governance layer, the six overlapping cell-selection mechanisms
(replaced by `--cells a,b,c` alone), the diagonal study design (replaced by the two
single-variable axes), and accuracy scoring in v1 — deferred to v2 and then built on
`lm-evaluation-harness` rather than a bespoke scorer, because that is what absorbed the
predecessor.

Several of OhYesMLX's rules exist because LMRE surfaced the problem: attribution needs one
variable; decode rate is defined over the content window in one place; cells are visited in
an order that cancels thermal drift; and a worker's report is never evidence — the diff and
a green test run are.

## Status

- **v1 — small-model format axis and sweeps (0.1.0).** Dense (`Qwen3.5-4B`) and MoE
  (`LFM2.5-8B-A1B`) format benchmarks across four runtimes, concurrency and prompt-length
  sweeps, KV cache reuse.
- **v2 — the JANG study and task accuracy scoring (0.2.0).** Single-variable evaluation of
  JANG quantizations, the cross-runtime synthesis, and MMLU / IFEval / GSM8K scoring via
  `lm-evaluation-harness`.
- **v3 — large-model scaling, context dynamics and public release (0.3.0, 2026-09-23).**
  35B MoE scaling (`Qwen3.6-35B-A3B`), NVMe expert streaming under memory pressure,
  multi-turn dynamics, quantized KV caches, and native multi-token prediction against
  speculative draft decoding.
- **v3.1 — hardening (in progress).** Same-build canaries, validation grids, and the
  cache-off re-runs behind the published concurrency and format tables.
- **v5.0 — the onboarding app.** Phases 0–5 complete as of 2026-11-19: the SwiftUI app,
  the hardened localhost API, engine installs, the model catalog and recommender, the
  downloader, quickbench, and the ad-hoc-signed DMG. Phase 5.5 (deferred cleanup) is in
  progress; Phase 5.6 (UI aesthetics) follows.

`.paul/STATE.md` is the live position; `.paul/PROJECT.md` is the charter and what has
shipped since.

## License

MIT. See [LICENSE](LICENSE).
