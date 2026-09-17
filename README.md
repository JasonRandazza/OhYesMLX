# OhYesMLX

**Honest benchmarks for local LLM serving on Apple Silicon.**

> On a Mac, for the *same model*, does the serving runtime and its quantization format
> actually change how fast it runs, how much memory it eats, and how smart it stays?

Nobody has published a clean answer. The numbers that circulate mix two variables at
once — a different runtime *and* a different quantization — and then credit the
difference to whichever one the author is promoting.

OhYesMLX measures one variable at a time.

## The two studies

The matrix is **ragged, not square.** Not every quantization format loads in every
runtime, so a full cross-product is impossible and a diagonal tells you nothing about
either axis in isolation. Instead:

| Study | Held constant | Varied | Answers |
|---|---|---|---|
| **A — Runtime axis** | the quantization format | `mlx_lm.server`, Osaurus, oMLX, `optiq serve` | Does the *server* matter? Swift vs Python overhead, continuous batching, prefix and KV caching. |
| **B — Format axis** | the runtime (oMLX, which loads the most formats) | mlx-lm 4-bit, oQ, OptiQ, JANG | Does the *quantization* matter? |

What loads where, as of today:

| Format | Stock `mlx-lm` can load it? | Runtimes |
|---|---|---|
| mlx-lm 4bit/8bit (affine) | yes | all MLX runtimes |
| oQ / oQe / oQ+ | **yes** — plain mlx-lm safetensors | all MLX runtimes |
| OptiQ | mostly | `optiq serve`, likely others |
| JANG / JANGTQ | **no** — needs the JANG_Q runtime | MLX Studio, Osaurus, oMLX |
| GGUF | no | llama.cpp, LM Studio |

Anything that varies both axes at once is a press release, not a benchmark.

## What gets measured

- **TTFT** — request sent → first *content* token. Includes prefill.
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

Every run pins temperature 0, a fixed seed, a fixed chat template, a fixed output length,
and records every runtime version. Runtimes ship different default `top_p` and
`repetition_penalty`; silently different defaults are the most common way these
comparisons get faked.

Raw observations are never discarded, so every summary stays recomputable.

## Status

v1 benchmarks complete across dense and MoE format axes, prompt-length sweeps, and KV cache reuse.
Key findings are published in `docs/research/`:
- [Dense format axis](docs/research/2026-09-16-phase5-joined-grid.md)
- [MoE format axis](docs/research/2026-09-16-moe-format-axis.md)
- [Prompt-length sweep](docs/research/2026-09-16-prompt-length-sweep.md)
- [Cold vs warm KV cache state (hybrid baseline)](docs/research/2026-09-17-cache-state-split.md)
- [Cold vs warm KV cache state (non-hybrid control)](docs/research/2026-09-17-cache-state-split-nonhybrid.md)
- [vMLX 32k prefill watchdog diagnosis and resolution](docs/research/2026-09-17-vmlx-32k-chunked-prefill.md)
- [Memory footprint accounting across runtimes](docs/research/2026-09-16-footprint-is-not-one-quantity.md)

## License

MIT
