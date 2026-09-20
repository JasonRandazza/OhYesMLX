# Plan 03-04 Study Design: Multi-Turn Conversation Sweep (1 to 10 Turns)

**Status:** PRE-REGISTERED  
**Date:** 2026-09-20  
**Phase:** Milestone v3 Phase 2 (Context Scaling & Conversational Dynamics)  
**Author:** Antigravity (Coordinator)  
**Target Hardware:** Apple Silicon M2 Max (12 CPU cores, 38 GPU cores, 64 GB unified memory, 400 GB/s bandwidth)  
**Subject Model:** `mlx-community/Qwen3.6-35B-A3B-4bit` (40 layers, 256 experts, 8 active per token, hybrid attention: linear attention with full attention every 4th layer, 19.03 GiB safetensors)  

---

## 1. Abstract & Scope

In production LLM deployments, interactions predominantly occur as multi-turn conversations rather than isolated single-shot queries. Across successive conversation turns ($k = 1, \dots, 10$), the prompt length submitted to `/v1/chat/completions` expands monotonically as prior user turns and assistant responses accumulate in the conversation history:
$$\text{PromptTokens}_k = \sum_{i=1}^{k-1} (\text{UserTokens}_i + \text{AssistantTokens}_i) + \text{UserTokens}_k$$

Under naive serving architectures without cross-request prefix caching, the prefill phase must recompute attention and linear-attention states across the entire sequence from token 0, causing Time to First Token (TTFT) to scale linearly $O(\text{PromptTokens}_k)$. In contrast, runtimes equipped with persistent prefix caching or stateful session KV retention (e.g. Osaurus prefix cache, oMLX paged SSD/RAM cache) can reuse the KV cache of past turns, reducing the prefill workload to only the incremental delta ($\text{AssistantTokens}_{k-1} + \text{UserTokens}_k$).

Simultaneously, as the KV cache expands across turns from ~50 tokens to ~1,500+ tokens, two runtime performance dimensions come under pressure:
1. **Decode Throughput & ITL:** Does expanding the active KV cache degrade token generation throughput (tok/s) or increase Inter-Token Latency (ITL / TPOT) on Apple Silicon unified memory?
2. **Physical Memory Footprint:** How much unified memory does the growing KV cache consume under Apple's `phys_footprint`, and do different runtime allocation strategies lead to memory bloat or fragmentation?

This study is the single-variable benchmark evaluating conversational dynamics across successive conversational turns (1 to 10) on a 35B MoE class model (`Qwen3.6-35B-A3B-4bit`) across four candidate runtimes: `omlx`, `osaurus`, `vmlx`, and `mlxlm`.

---

## 2. Pre-Registered Hypotheses

### H1: Prefix Cache Retention & TTFT Decoupling
In runtimes with active prefix caching (Osaurus with `cache.prefix.enabled=true`, oMLX with `--paged-ssd-cache` / default cache enabled), TTFT from Turn 2 through Turn 10 will decouple from total dialogue length and remain virtually flat (within $\pm20\%$ of Turn 1 TTFT), evaluating only the incremental turn delta (~50–80 tokens). Conversely, in runtimes without cross-request prefix caching for hybrid architectures (stock mlx-lm, vMLX), TTFT will scale linearly $O(K)$ with cumulative prompt length, growing 5× to 10× between Turn 1 (~50 tokens) and Turn 10 (~1,500 tokens).

### H2: Decode Throughput Invariance to Context Length ($\le 5\%$ Variation)
On Apple Silicon M2 Max, decode throughput (tok/s) on `Qwen3.6-35B-A3B-4bit` will remain invariant within $\le 5\%$ from Turn 1 to Turn 10 across all runtimes. Because model weights (19.03 GiB) dominate the memory bus at batch size 1 (transferring ~1.98 GB of active expert and backbone weights per token), reading a 1,500-token KV cache adds negligible memory bandwidth demand ($<0.5\%$ increase in bytes moved per step), leaving decode throughput bandwidth-saturated rather than compute-saturated.

### H3: Inter-Token Latency (ITL / TPOT) Stability ($< 1.0\text{ ms}$ Jitter)
Mean Inter-Token Latency (ITL / TPOT) will exhibit exceptional stability across turns, with per-turn mean ITL deviating by less than $1.0\text{ ms}$ from Turn 1 through Turn 10 within each runtime (e.g. ~14–17 ms/token for 60–70 tok/s). This confirms that attention computation does not bottleneck generation at conversational context lengths ($<2\text{k}$ tokens).

### H4: Monotonic KV Cache Memory Footprint Trajectory ($\le 250\text{ MB}$ Growth)
Process physical memory footprint (`phys_footprint_mb`) will grow monotonically across turns by $\le 250\text{ MB}$ total across 10 turns. For `Qwen3.6-35B-A3B` (40 layers, 2 GQA key-value heads, head dimension 128, BF16), 1,500 tokens consume approximately $40 \times 2 \times 2 \times 128 \times 2 \text{ bytes} \times 1,500 \approx 61.4\text{ MB}$ of raw KV tensors. Total footprint growth will reflect this theoretical allocation plus allocator page alignment, with zero memory leakage or swap activity.

### H5: Dialogue Coherence and Semantic Consistency Floor (100% PASS)
All four runtimes will maintain 100% coherence (0 token salad failures, 0 repetition collapse, clean English prose) across all 10 turns on `Qwen3.6-35B-A3B-4bit`. Output tokens will remain directly responsive to each turn's query while incorporating contextual facts from prior dialogue history.

---

## 3. Experimental Design & 10-Turn Dialogue Protocol

### 3.1 Pinned Dialogue Sequence
To eliminate conversational variance, the study pins a structured 10-turn technical dialogue sequence covering distributed systems and consensus architecture:

- **Turn 1:** "What are the core differences between monolithic and microservice software architectures?"
- **Turn 2:** "Considering those differences, how does service discovery work in a microservice setup?"
- **Turn 3:** "How does client-side service discovery compare to server-side service discovery in terms of load balancing?"
- **Turn 4:** "What consensus algorithms (like Raft or Paxos) are typically used by service registries like Consul or etcd?"
- **Turn 5:** "Explain the leader election phase in Raft in detail."
- **Turn 6:** "What happens if a network partition splits the Raft cluster into two equal halves?"
- **Turn 7:** "How do vector clocks help detect concurrent updates during network partitions in distributed key-value stores?"
- **Turn 8:** "Can you provide a simple concrete example of two conflicting vector clock states?"
- **Turn 9:** "How does Dynamo-style eventual consistency resolve such vector clock conflicts using Last-Write-Wins or CRDTs?"
- **Turn 10:** "Summarize the key architectural lessons learned from these ten discussion points into three golden rules."

### 3.2 Message Construction
At turn $k \in \{1, \dots, 10\}$, the request payload to `/v1/chat/completions` contains:
```python
messages = []
for i in range(1, k):
    messages.append({"role": "user", "content": QUESTIONS[i]})
    messages.append({"role": "assistant", "content": ASSISTANT_RESPONSES[i]})
messages.append({"role": "user", "content": QUESTIONS[k]})
```
Where `ASSISTANT_RESPONSES[i]` is the actual generated text emitted by the runtime in turn $i$, preserving live context dependency.

### 3.3 Candidate Runtimes & Port Allocations
Each runtime is evaluated independently in complete process isolation:

| Runtime | Version | Port | Startup Flags / Configuration |
|:---|:---:|:---:|:---|
| **`mlxlm`** | 0.31.3 | 8081 | `python -m mlx_lm.server --model <artifact> --port 8081` |
| **`omlx`** | 0.6.4 | 8100 | `omlx serve --model-dir <catalog> --port 8100 --max-concurrent-requests 1 --memory-guard off` |
| **`osaurus`** | 0.25.5 | 1337 | `osaurus serve --port 1337 --yes` (`modelIdleResidencyPolicy.seconds=900`, `cache.prefix.enabled=true`) |
| **`vmlx`** | 1.6.59 | 8000 | `vmlx serve <artifact> --port 8000 --stream-interval 1 --continuous-batching --no-jit --disable-native-mtp` |

---

## 4. Controlled Parameters & Standing Rules

1. **Vary One Thing at a Time:** Model checkpoint (`Qwen3.6-35B-A3B-4bit`), sampling parameters, and conversation dialogue sequence are held strictly identical; only the serving runtime varies across cells, and turn index varies within each cell.
2. **Fixed Sampling Parameters:** `temperature = 0.0`, `seed = 0`, greedy decoding, `max_tokens = 64`.
3. **Quiet Machine Rule:** Exactly one serving runtime process resident at any time. No background downloads, compiles, or test suites.
4. **Port Sweep & Verification:** Ports 8000, 8080, 8081, 8100, 1337 swept and verified clean before and after every runtime run.
5. **Memory & Coherence Disciplines:**
   - Physical memory sampled via `sample.phys_footprint_mb(pid)` after every turn.
   - Text output validated via `coherence.is_coherent()` on every completion.

---

## 5. Artifacts & Deliverables

1. **Order Specification:** `.paul/orders/plan-03-04-spec.md`
2. **Study Design:** `docs/research/2026-09-20-v3-phase2-plan-03-04-study-design.md`
3. **Probe Script:** `scripts/probe_multiturn_sweep.py`
4. **Raw Benchmark Data:** `results/plan-03-04/multiturn_results.json`
5. **Research Report:** `docs/research/2026-09-20-multiturn-conversation-sweep.md`
