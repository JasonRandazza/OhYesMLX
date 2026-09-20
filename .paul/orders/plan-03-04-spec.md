GOAL: Specify Plan 03-04 (Multi-Turn Conversation Sweep: 1 to 10 Turns) study design and probe script.

CONTEXT:
Milestone v3 Phase 2 addresses Context Scaling & Conversational Dynamics on Apple Silicon using Qwen3.6-35B-A3B (~19.03 GiB 4-bit weights).
In realistic conversational workloads, chat interactions are multi-turn: each subsequent request appends previous user turns and assistant responses to context history.
Under standard non-cached serving, prefill time (TTFT) scales linearly with cumulative sequence length as every past token is re-embedded and re-attended from token 0.
Under prefix-cached serving (e.g. Osaurus, oMLX), prior KV states are retained across requests, collapsing prefill to the incremental delta of new tokens.
Furthermore, as conversational context expands from ~100 to >1,500 tokens, decode throughput (tok/s) and inter-token latency (ITL / TPOT) may experience degradation due to expanding KV cache memory traffic and attention operations.

Plan 03-04 evaluates multi-turn conversational dynamics from 1 to 10 turns across serving runtimes (omlx, osaurus, vmlx, mlxlm) on Qwen3.6-35B-A3B-4bit, quantifying:
1. Turn-by-turn TTFT progression and prefix cache retention speedup.
2. Turn-by-turn ITL / TPOT stability and decode throughput scaling.
3. KV cache physical memory footprint growth across successive turns.
4. Semantic coherence and conversational consistency across all 10 turns.

DELIVERABLES:
1. docs/research/2026-09-20-v3-phase2-plan-03-04-study-design.md
   - Pre-registered single-variable study design with hypotheses H1–H5.
   - Pinned 10-turn dialogue sequence with cumulative context expansion.
   - Evaluation protocol across candidate runtimes (omlx, osaurus, vmlx, mlxlm).
2. scripts/probe_multiturn_sweep.py
   - Automated probe executing 10-turn sequential conversations.
   - Turn-by-turn measurement of TTFT, ITL, decode throughput, token counts, and memory footprint.
   - Live coherence verification on every assistant completion.
3. results/plan-03-04/multiturn_results.json
   - Full raw empirical observations across all turns and runtimes.
4. docs/research/2026-09-20-multiturn-conversation-sweep.md
   - Comprehensive research report analyzing H1–H5 against empirical data.
