# OhYesMLX

**Honest benchmarks for local LLM serving on Apple Silicon.**

> On a Mac, for the *same model*, does the serving runtime and its quantization format
> actually change how fast it runs, how much memory it eats, and how smart it stays?

Nobody has published a clean answer. The numbers that circulate mix two variables at
once — a different runtime *and* a different quantization — and then credit the
difference to whichever one the author is promoting.

OhYesMLX measures one variable at a time.

## How OhYesMLX Helps You: Cutting Out the Guesswork

Choosing the right local LLM serving configuration on Apple Silicon usually involves wading through conflicting vendor benchmarks, fragmented forum posts, and weeks of painful trial-and-error:

- **Vendor claims conflict:** One developer claims a "3x speedup" by switching runtimes; another claims their proprietary quantization matches "4-bit quality at 2-bit footprint." Because their benchmarks change both the runtime *and* the quantization simultaneously, it is impossible to know what actually drove the difference.
- **Hidden operational hazards:** Does your runtime secretly rotate out KV cache context instead of refusing? Does it lazy-load weights on the first request, silently adding a 9-second pause to your first user interaction? Does it crash the macOS GPU watchdog on 32k prefill? Does it switch to NVMe streaming under memory pressure and drop decode throughput from 75 tok/s to 8 tok/s without warning?
- **Misleading metrics:** Standard `ps` RSS reports garbage under MLX on unified memory because Metal buffers, mmap'd weights, and wired GPU memory account inconsistently. And raw tok/s numbers mean nothing if the server silently emits mixed-script token salad without throwing an error.

**OhYesMLX does not dictate what model or runtime you should use.** There is no single "best" setup for everyone. Instead, OhYesMLX gives you **rigorous, empirical evidence** tailored to your hardware and your workload:

| Your Hardware & Workload | What OhYesMLX Measures & Reveals | Practical Decision You Can Make |
|---|---|---|
| **Tight Unified Memory (16 GB / 24 GB / 32 GB)** | True kernel `phys_footprint`, on-disk sidecars, INT4/FP8 KV cache compression, and NVMe expert streaming floors. | Know with certainty whether a 35B MoE or 8B model will fit in unified memory without OS memory paging or swap thrashing. |
| **Interactive Chat & Coding (Snappy UX)** | Time-to-First-Token (TTFT), cold vs warm KV cache hit speedups, and multi-turn context latency growth. | Identify runtimes that deliver sub-20ms inter-token latency and preserve prompt cache across conversation turns without re-prefill penalties. |
| **Long-Document & RAG Ingestion** | Prompt prefill throughput (tok/s), chunked prefill stability up to 32k/64k, and GPU watchdog resilience. | Avoid runtimes that deadlock or hit macOS Metal watchdog timeouts during heavy prefill batches. |
| **Quality vs Storage Optimization** | Decode speed, memory footprint and on-disk size per format; the published accuracy studies add MMLU, IFEval and GSM8K. | Determine empirically whether a 2-bit or proprietary quant saves enough disk/RAM to justify its quality trade-off, or if uniform 4-bit strictly dominates. |

Instead of spending weeks guessing or writing throwaway test scripts, you can run a single-variable study in an afternoon and get reproducible data to select the best setup for your exact needs.

## The two studies

The matrix is **ragged, not square.** Not every quantization format loads in every
runtime, so a full cross-product is impossible and a diagonal tells you nothing about
either axis in isolation. Instead:

| Study | Held constant | Varied | Answers |
|---|---|---|---|
| **A — Runtime axis** | the quantization format — one artifact for the whole run | the serving runtimes: `mlxlm`, `osaurus`, `omlx`, `optiq`, `vmlx` | Does the *server* matter? Swift vs Python overhead, continuous batching, prefix and KV caching. |
| **B — Format axis** | the runtime — whichever one you select, the same for every cell in the run | mlx-lm 4-bit, oQ, OptiQ, JANG | Does the *quantization* matter? |

What loads where, as of today:

| Format | Stock `mlx_lm.server` can load it? | Registered runtimes measured with it here |
|---|---|---|
| mlx-lm 4bit/8bit (affine) | yes | all five: `mlxlm`, `omlx`, `optiq`, `vmlx`, `osaurus` |
| oQ / oQe / oQ+ | **yes** — plain mlx-lm safetensors | the same five |
| OptiQ | yes | the same five — `optiq` is the runtime built for it |
| JANG / JANGTQ | **no** | `vmlx` and `osaurus`; no other registered runtime loads it |
| GGUF | no | none of the five — GGUF needs llama.cpp or LM Studio, which this harness does not drive |

Anything that varies both axes at once is a press release, not a benchmark.

## What gets measured

- **TTFT** — request sent → first token of the runtime's *output stream*. Includes prefill.
  When a runtime answers only in its reasoning channel, or mirrors its reasoning into content,
  that channel is the output stream and the row prints `timed on reasoning channel` beside the
  number (`transport.timing_channel`, `report._reasoning_timed_note`).
- **ITL / TPOT** — mean gap between output tokens after the first. The "feels fast" number.
- **End-to-end latency** — P50 / P90 / P99. Never a bare mean.
- **Output throughput** — reported **per-request and aggregate separately**, because
  continuous batching wins one and loses the other.
- **Cold load time** — reported on its own, not folded into the first request.
- **Peak memory** — via `footprint -p <pid>` (Apple's `phys_footprint`, what Activity
  Monitor shows). `ps` RSS is *wrong* for MLX: Metal buffers, mmap'd weights, and wired
  GPU memory account inconsistently.
- **On-disk size** — including sidecar files, so no format gets credited with a smaller
  footprint than it has.

Every run pins temperature 0 and a fixed seed **in the request body**, records each workload's
prompt and output cap, and records every runtime version. OptiQ is started with its sampler
flags pinned too (`--temp 0 --top-p 1 --top-k 0 --min-p 0`, `runtimes.Optiq.start_command`):
left to itself, `optiq serve` injects an artifact's own `generation_config.json` sampling
values into the command. The other four runtimes are asked for temperature 0 and the seed and
nothing else, so their `top_p`, `top_k`, `min_p` and `repetition_penalty` are whatever those
servers default to — which is why a row is read beside the runtime version it was measured
under.

Raw observations are never discarded, so every summary stays recomputable.

## Quickstart & CLI Usage

OhYesMLX is packaged under PEP 621 with zero external runtime dependencies (Python standard library only).

### Installation

```bash
# Clone the repository
git clone https://github.com/JasonRandazza/OhYesMLX.git
cd OhYesMLX

# Run directly or install as an editable package
python3 -m pip install -e .
```

### Running Single-Variable Studies

To guarantee valid attribution, OhYesMLX enforces that every benchmark run varies exactly one axis (`--study runtime` or `--study format`):

```bash
# 1. Format Study: Hold runtime constant (e.g. mlxlm), vary quantization formats
ohyesmlx run --study format \
  --cells "stock4bit__mlxlm=/path/to/model-4bit,oq4__mlxlm=/path/to/model-oQ4" \
  --rank decode_tps

# 2. Runtime Study: Hold quantization format constant (e.g. oq4), vary serving runtimes
ohyesmlx run --study runtime \
  --cells "oq4__mlxlm=/path/to/model-oQ4,oq4__omlx=/path/to/model-oQ4" \
  --rank decode_tps
```

### Comparing Runs

```bash
# Join multiple runs into a comparative markdown grid
ohyesmlx grid run_dir_1 run_dir_2 --rank decode_tps --out results/grid.md
```

## Model & Architecture Compatibility Guide

When you clone or install OhYesMLX, **you are not restricted to the models measured in our published benchmarks.** The harness accepts any local model path via `--cells` (the only cell selector, by design).

Because OhYesMLX benchmarks serving runtimes on Apple Silicon, whether a model runs depends on the requirements of the runtime you choose.

### Supported Architectures & Formats (What Works)

Any model can be benchmarked as long as:
1. It resides on local disk in standard HuggingFace / MLX format (containing `.safetensors` or MLX weights, `config.json`, and `tokenizer.json`).
2. The chosen serving runtime's MLX engine implements that architecture.

Verified working architecture families:
- **Dense architectures:** Llama (3, 3.1, 3.2), Qwen (2.5, 3.5), Mistral, Phi (3, 4), DeepSeek-R1-Distill (Qwen & Llama), Gemma 2.
- **Mixture-of-Experts (MoE):** LFM 2.5 (e.g. `LFM2.5-8B-A1B` with 16 experts), Qwen 3.6 MoE (e.g. `Qwen3.6-35B-A3B` with 256 fine-grained routed experts), Mixtral (8x7B, 8x22B).

**Quantization format compatibility** — stated for the five registered runtimes
(`runtimes.RUNTIMES`: `mlxlm`, `omlx`, `optiq`, `vmlx`, `osaurus`), which is the whole of what
this harness can drive and therefore the whole of what it can claim to have measured:
- **Standard MLX 4-bit / 8-bit (`mlx-lm` affine):** plain safetensors; all five load it.
- **oQ / oQe / oQ+:** plain MLX safetensors; all five load it.
- **OptiQ:** built for `optiq serve`; the other four have served it in the runs recorded here.
- **JANG / JANGTQ (`JANG_4S`, `JANG_2L`):** proprietary quantized format; it needs a JANG-aware
  runtime, which among the registered five means `vmlx` or `osaurus`. Not loadable in `mlxlm`,
  `omlx` or `optiq`. MLX Studio is a separate application outside this registry; no harness
  run drives it.

### What Does Not Work (Known Limitations)

- **Unsupported model types in stock MLX:** Architectures not yet implemented in the serving runtime's MLX backend cannot load. For example, `gemma-4-12B-it-qat` (`model_type: gemma4_unified`) is rejected by stock `mlx-lm 0.31.3`.
- **Non-MLX formats:** GGUF (`llama.cpp`), AWQ, GPTQ (CUDA), and EXL2 are not loadable by MLX runtimes.
- **Incomplete / omitted parameter weights:** Weights missing architecture-mandated tensor blocks will fail loadability (e.g. dense OptiQ weights missing the 297 vision parameter blocks required by multimodal runtimes like vMLX).
- **Speculative draft decoding on hybrid linear-attention:** Stock `mlx_lm.server --draft-model` refuses models using non-trimmable recurrent KV caches (e.g. hybrid linear-attention `ArraysCache`).
- **Non-macOS systems:** OhYesMLX requires macOS Apple Silicon unified memory and uses `/usr/bin/footprint -p <pid>` for true hardware memory residency. Linux and Windows are not supported.
- **Mid-run network downloads:** The harness explicitly prohibits downloading weights while a measurement is active. Network and NVMe disk contention silently corrupts cold load timings (`cold_load_s`) and TTFT latency.

## Horizon Roadmap (v3.1 / v4 Candidates)

We plan to expand the harness's scope in upcoming releases:
- **Non-MLX runtime adapters:** Adding `llama.cpp` server and `Ollama` runner adapters to enable rigorous, single-variable GGUF vs MLX cross-runtime evaluation.
- **Emerging architecture support:** Adapting to updated MLX backends (`gemma4_unified`), Vision-Language Models (VLMs), and native multi-token prediction (MTP) heads.
- **Automated evaluation suite integration:** Integrating zero-shot / thinking-off task accuracy suites directly into the pipeline alongside speed and memory reporting.

## Status

- **v1 — Small-Model Format Axis & Sweeps (v0.1.0):** Dense (`Qwen3.5-4B`) and MoE (`LFM2.5-8B-A1B`) format benchmarks across 4 runtimes, concurrency and prompt-length sweeps, and KV cache reuse.
- **v2 — The JANG Study & Task Accuracy Scoring (v0.2.0):** Single-variable evaluation of JANG proprietary quantizations, cross-runtime performance synthesis, and automated MMLU accuracy scoring via `lm-evaluation-harness`.
- **v3 — Large-Model Scaling, Context Dynamics & Public Release (v0.3.0):** 35B MoE scaling (`Qwen3.6-35B-A3B`), NVMe expert streaming under high memory pressure, multi-turn conversational dynamics, quantized KV caches (INT4/FP8), native Multi-Token Prediction (MTP) vs speculative draft decoding and zero-dependency distribution.

Key findings are published in `docs/research/`:
- [Dense format axis](docs/research/2026-09-16-phase5-joined-grid.md)
- [MoE format axis](docs/research/2026-09-16-moe-format-axis.md)
- [Prompt-length sweep](docs/research/2026-09-16-prompt-length-sweep.md)
- [Cold vs warm KV cache state](docs/research/2026-09-17-cache-state-split.md)
- [JANG Cross-Runtime Synthesis](docs/research/2026-09-17-jang-cross-runtime.md)
- [Accuracy vs Throughput Pareto Tradeoff](docs/research/2026-09-19-accuracy-pareto.md)
- [35B MoE Serving Benchmark](docs/research/2026-09-20-35b-moe-serving.md)
- [Expert Streaming under Memory Pressure](docs/research/2026-09-20-expert-streaming-high-memory-pressure.md)
- [Multi-Turn Conversation Dynamics](docs/research/2026-09-20-multiturn-conversation-sweep.md)
- [Quantized KV Caches (INT4 / FP8)](docs/research/2026-09-20-quantized-kv-caches.md)
- [Native MTP Acceleration](docs/research/2026-09-20-native-mtp-vmlx.md)
- [Speculative Draft Decoding Analysis](docs/research/2026-09-20-speculative-draft-decoding.md)

## License

MIT
