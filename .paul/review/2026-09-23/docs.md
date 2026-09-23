Scope: Compared README.md, docs/interfaces.md, docs/runtimes/*.md, AGENTS.md, and CLI implementation/help text against ohyesmlx/*.py; suite baseline/current: 497 passed.

### F1 [high] The interface contract defines a different record/workload schema than the code
Where: docs/interfaces.md:127-159, 193-199, 271-272
Evidence:
>     status: str                    # "PASS" | "FAIL" | "N/A"
>     observations: list[Observation]   # EVERY raw sample. Never truncated.
>     batch_spans: list[float]       # one per measured batch; [] for a sequential cell (06-01b)
>     warmup_plateau: bool | None
>     lost_visit_reason: str | None  # a planned visit that never measured. See the short-window section.
>     cold_load_after_lost_visit: bool
>     measured_pin: int | None       # the run's batch pin; not written to the record
>     cold_load_s: float | None
>     first_request_workload_id: str | None   # which shape made it. See below.
>     memory: dict                   # the sample.py result dict
>     runtime_version: str | None
>     disk_bytes: int | None
>     id: str                  # "chat" | "prefill" | "decode" — the column key in every report
> Line 1 of the file is the **run header**: the pins (`temperature`, `seed`, `max_tokens`,
> `warmup`, `measured`, `cooldown_s`, `workload`). Every line after it is one cell.
Failure: The contract omits `CellResult.workload_id` and describes required per-record `batch_spans`/`measured_pin` although the record writes spans only when present and never writes measured_pin; it also calls `max_tokens` a run-level header pin rather than a workload field. Implementers/readers following it construct incompatible records and misread concurrency records.
Fix: Replace these snippets with the actual workload-keyed cell record and header shape, including optional-record keys.

### F2 [high] README says the format-study runtime is oMLX and omits vMLX from its runtime-axis CLI
Where: README.md:39-42
Evidence:
> | **A — Runtime axis** | the quantization format | `mlx_lm.server`, Osaurus, oMLX, `optiq serve` | Does the *server* matter? Swift vs Python overhead, continuous batching, prefix and KV caching. |
> | **B — Format axis** | the runtime (oMLX, which loads the most formats) | mlx-lm 4-bit, oQ, OptiQ, JANG | Does the *quantization* matter? |
Failure: The actual CLI supports five runtimes including vMLX, and its format axis pins any single selected runtime; the documented oMLX-only choice is not a constraint in `_check_axis`. Following the table unnecessarily excludes vMLX and misstates what format-axis runs can select.
Fix: List vMLX among runtime-axis choices and describe format-axis runtime as caller-selected, not fixed to oMLX.

### F3 [high] The interface spec says all formulas require two content deltas, but one-delta gating is performed only in report
Where: docs/interfaces.md:288-307
Evidence:
> # DOMAIN: all three require content_event_count >= 2.
> Outside that domain all three are `None` and the row says why — they are never computed and
> clamped, and no epsilon is added to the window.
> `ttft_s` itself stays a real number in that case, but it measures **time-to-completion, not
> time-to-first-token**, and the row must label it.
Failure: `measure.decode_tps` and `measure.itl_s` compute directly without checking event count; `measure.prefill_tps` also computes for one event. `report._per_request` applies the two-delta guard to summary values, but the public formula functions themselves do not return `None` as the contract states. Callers using those functions directly can publish a value outside the specified domain.
Fix: Clarify that the two-delta domain is enforced by report summaries, or change the code contract/functions consistently.

### F4 [high] README claims the benchmark pins sampling parameters that CLI does not send
Where: README.md:70-73; docs/runtimes/optiq.md:739-752
Evidence:
> Every run pins temperature 0, a fixed seed, a fixed chat template, a fixed output length,
> and records every runtime version. Runtimes ship different default `top_p` and
> `repetition_penalty`; silently different defaults are the most common way these
> comparisons get faked.
> The fix is one flag: pass `--temp 0 --top-p 1 --top-k 0 --min-p 0` explicitly, which makes
> `already` true and short-circuits the injection.
Failure: `Optiq.start_command` does not pin sampler flags and `transport.chat` sends temperature 0 and seed but no top_p or repetition_penalty. OptiQ can therefore inject artifact `generation_config.json` sampling values despite the documented claim; output can differ across artifacts for reasons besides quantization.
Fix: Pin/record supported sampler fields in the runtime command/request, or narrow the README claim to the parameters actually pinned.

### F5 [medium] README's JANG runtime list includes removed/unsupported MLX Studio and omits vMLX accurately only as a current candidate
Where: README.md:51, 135
Evidence:
> | JANG / JANGTQ | **no** — needs the JANG_Q runtime | MLX Studio, Osaurus, oMLX |
> - **JANG / JANGTQ (`JANG_4S`, `JANG_2L`):** Proprietary quantized format; requires JANG-aware runtimes (vMLX, Osaurus, MLX Studio). Not loadable in stock `mlx_lm.server` or `optiq serve`.
Failure: `RUNTIMES` currently has vMLX, Osaurus and oMLX as JANG-capable benchmark targets; MLX Studio is not in the registry and cannot be selected as a run runtime. The first table omits the registered vMLX and calls the runtime "JANG_Q" as though it were a selectable name.
Fix: Distinguish external JANG-capable applications from the five registered runtime IDs and list vMLX in the latter.

### F6 [medium] The interfaces document claims “content-delta” fields even when timings/count come from reasoning
Where: docs/interfaces.md:17-25, 41-53
Evidence:
>     ttft_s: float | None            # send -> first delta of the OUTPUT stream (see below)
>     last_content_s: float | None    # send -> final content delta
>     content_event_count: int        # deltas of the OUTPUT stream, not always the content channel
> In both, the reasoning deltas are the output stream and supply `ttft_s`, `last_content_s` and `content_event_count`.
Failure: `Observation.text` remains the content channel and `reasoning_text` remains separate, while the timing named `last_content_s` and `content_event_count` can describe reasoning-only streams. Consumers relying on field names/comments to count visible content or derive TTFT semantics may misinterpret them.
Fix: Name/document these as output-stream timing/count fields, or make the field semantics consistently content-only.

### F7 [medium] Runtime interface omits vMLX and Handle fields present in the implementation
Where: docs/interfaces.md:79-101
Evidence:
>     name: str                      # "mlxlm" | "osaurus" | "omlx" | "optiq"
>     first_request_s: float | None  # the cold visit's FIRST warmup latency. See below.
>     def stop(self) -> None: ...    # must not return until the port is free
> RUNTIMES: dict[str, Runtime]       # keyed by name
Failure: `RUNTIMES` includes `vmlx`; `Handle` additionally has `serving_pid`, `stop_command`, `scratch`, and `api_key`, while `first_request_s` is not a Handle field at construction/use—measurement writes it to CellResult after warmup. Consumers conforming to this “contract” use an incomplete interface and expect a field on the wrong object.
Fix: Update the runtime names and distinguish `Handle` lifecycle fields from `CellResult` first-request measurements.

### F8 [medium] README advertises “all MLX runtimes” for quant formats without matching current support
Where: README.md:46-51, 131-135
Evidence:
> | mlx-lm 4bit/8bit (affine) | yes | all MLX runtimes |
> | oQ / oQe / oQ+ | **yes** — plain mlx-lm safetensors | all MLX runtimes |
> - **Standard MLX 4-bit / 8-bit (`mlx-lm` affine):** Loads in all MLX runtimes (`mlx_lm.server`, Osaurus, oMLX, `optiq serve`, vMLX).
> - **oQ / oQe / oQ+:** Plain MLX safetensors; loads in all MLX runtimes.
Failure: “all MLX runtimes” includes MLX Studio/other serving runtimes not implemented by this package and is contradicted by the later explicit list and architecture constraints. The benchmark itself cannot exercise every external runtime, so this broad compatibility guarantee is unsupported by the cited in-repo code.
Fix: Limit the compatibility statement to the five registered runtimes and qualify it by model/format support evidence.

### F9 [medium] Interfaces document says every visit starts each cell twice, while the last visit may be omitted
Where: docs/interfaces.md:237-244
Evidence:
> `run_cells` stops the current runtime and confirms its port is free before starting the next.
> Cell order is **interleaved**, never config order — otherwise thermal drift aliases
> perfectly onto runtime identity. Persist after every cell.
Failure: The implementation skips zero-quota visits when `measured < VISIT_ROUNDS`; it does not universally visit every cell twice. With one measured batch, the second visit is dropped, invalidating statements that depend on two visits/paired interleaving.
Fix: State the two-visit plan is conditional on nonzero quotas and document the one-batch case.

### F10 [low] README labels the released package as a prototype at version 0.0.1
Where: README.md:27-34
Evidence:
> | Version | 0.0.1 |
> | Status | Prototype |
> | Last Updated | 2026-09-14 |
Failure: The package metadata and `ohyesmlx.__version__` are 0.3.0; installation/status claims now describe a different release state and date.
Fix: Update the status table to the packaged version and current release state/date.

### F11 [low] Runtime capability docs embed implementation line citations that point to stale harness locations
Where: docs/runtimes/optiq.md:141; docs/runtimes/vmlx.md:1562-1565; docs/runtimes/vmlx.md:1583-1587
Evidence:
> `optiq --version` is the harness's `version_command` (`ohyesmlx/runtimes.py:720`) and prints
> `vMLX is not in RUNTIMES` (`ohyesmlx/runtimes.py:733-738`), which currently holds
> **Port.** The CLI default is `8000`, which is **free** in the current registry — `optiq` is 8080
> and `mlxlm` is 8081, so `--port 8000` collides with nothing.
Failure: Current `runtimes.py` places the registry around lines 1165-1171 and vMLX is included. Stale line citations can direct maintainers to unrelated definitions and conceal that vMLX is already integrated.
Fix: Refresh in-repository citations and mark the “subclass would need” section historical or remove it.

### F12 [low] Rationale for one-definition/one-rationale rules is repeated with inconsistent counts
Where: AGENTS.md:57-58; docs/interfaces.md:257-263
Evidence:
> A formula, a guard, a size or a constant lives in exactly one place and every caller asks it. Two copies drift: `report.py` and `measure.py` once carried two decode-rate formulas that disagreed on edge cases, and two disk-size walks, one of which miscounted HF-cache snapshots.
> Each rationale is written once, where the thing it explains is defined. Callers point at it; they do not restate it. A rule restated in seven docstrings has seven places to go stale.
> `measure.py` owns `results.jsonl`, and is the only thing that writes it. The
> serializer (`write_jsonl`, and the per-cell record it builds) lives in `measure.py`
> alongside `CellResult`, which owns the shape. `run_cells` calls it after every cell so a
> run that dies still has its completed cells on disk; `report.py` imports it if it needs
> it, and never defines a second one.
Failure: The same rationale is restated across AGENTS.md and the interface document; the interfaces text says “after every cell”, while the implementation writes after every visit. The duplicated rationale has already drifted into a materially different persistence cadence.
Fix: Keep the rationale at the owning implementation/standards location and make the interface description point to it while correcting “cell” to “visit”.

Unverified suspicions:
- README claims of arbitrary architecture and broad quantization compatibility likely exceed what the runtime registry guarantees; verify each listed family/format against actual runtime source and artifacts before treating as a supported compatibility matrix.
- README promotional claims such as “sub-20ms inter-token latency” and “in an afternoon” are not guaranteed by code or the provided documentation; I did not treat them as falsifiable interface claims.
