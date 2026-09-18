GOAL: Author scripts/probe_accuracy_spike.py to execute the Plan 02-01 Harness Spike and local endpoint validation protocol defined in docs/research/2026-09-17-v2-track2-accuracy-study-design.md §6.2.

FILES YOU MAY EDIT:
scripts/probe_accuracy_spike.py only. Touch nothing else.

STYLE & METHOD:
- Python 3.11+, stdlib first, flat and concise (~100-150 lines).
- Directly utilize ohyesmlx.runtimes for lifecycle management (start/stop/base_url).
- Strictly adhere to the defining rule: "Vary one thing at a time."
- Do NOT start servers or load models during authoring (coordinator will execute the script).

REQUIREMENTS FOR scripts/probe_accuracy_spike.py:
1. Target Artifact & Runtime:
   - Target runtime: "vmlx" on port 8000.
   - Target artifact: Qwen3.5-4B stock4bit at ~/.cache/huggingface/hub/models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c.
   - Cache state pinned: cache_state="off".

2. Canary Validation:
   - Issue a direct POST request to /v1/chat/completions with:
     {"messages": [{"role": "user", "content": "What is 2+2? Answer with just the number."}], "temperature": 0.0, "max_tokens": 16}
   - Inspect the response structure:
     * Check if answer text is in `choices[0].message.content` or `choices[0].message.reasoning_content`.
     * Record verbatim response text and channel used.

3. lm-eval Command Invocation via subprocess:
   - Run via isolated uv environment:
     /Users/jrazz/.local/bin/uv run --isolated --with "lm-eval[ifeval]==0.4.13" lm_eval \
       --model local-chat-completions \
       --model_args "base_url=http://127.0.0.1:8000/v1,model={model_id},think_end_token=</think>" \
       --tasks gsm8k \
       --limit 2 \
       --output_path results/spike-eval/ \
       --log_samples
   - Ensure results/spike-eval/ directory exists.
   - Capture returncode, stdout, and inspect output JSON file.

4. Cleanup Invariant:
   - Always stop runtime handle in `finally` block and verify port is released.

5. Reporting:
   - Print structured JSON report containing:
     * uv_version
     * lm_eval_version
     * runtime_version
     * canary_channel (content vs reasoning_content)
     * canary_text
     * lm_eval_returncode
     * gsm8k_sample_score
     * seconds_per_item

REPORT:
Return path to scripts/probe_accuracy_spike.py and summary of implementation.
