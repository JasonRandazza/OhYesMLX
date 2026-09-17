#!/bin/sh
# Fetch the non-hybrid model for Candidate 3 (repeat cache split on non-hybrid architecture).
#
# 4.73 GB. brainworkup/Llama-3.1-8B-oQ4 is a pure transformer (LlamaForCausalLM, model_type llama)
# using standard KVCache across all layers with is_trimmable() == True.
# Purpose: Test whether mlx-lm, OptiQ, and vMLX serve warm cache hits when not constrained
# by Qwen3.5-4B's hybrid ArraysCache.
#
# Do not run this while a grid or sweep measurement is running.
set -eu
HF=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/hf
for repo in \
  brainworkup/Llama-3.1-8B-oQ4
do
  echo "=== $repo $(date +%H:%M:%S)"
  "$HF" download "$repo" >/dev/null || echo "FAILED $repo"
done

# Ensure chat template is populated (brainworkup/Llama-3.1-8B-oQ4 is base Llama,
# which lacks a chat_template in tokenizer_config.json required by oMLX and vMLX).
"$HF" download mlx-community/Meta-Llama-3.1-8B-Instruct-4bit tokenizer_config.json >/dev/null
python3 -c "
import json, os
snap = os.path.expanduser('~/.cache/huggingface/hub/models--brainworkup--Llama-3.1-8B-oQ4/snapshots/a041336af01fe59ffe17c762d4c970564dcabc53')
it_cfg = os.path.expanduser('~/.cache/huggingface/hub/models--mlx-community--Meta-Llama-3.1-8B-Instruct-4bit/snapshots/241a666dad6cb93c8ff213d39a7f34a36bf26db4/tokenizer_config.json')
with open(it_cfg) as f:
    tmpl = json.load(f)['chat_template']
cfg = os.path.join(snap, 'tokenizer_config.json')
with open(cfg) as f:
    data = json.load(f)
data['chat_template'] = tmpl
if os.path.islink(cfg):
    os.unlink(cfg)
with open(cfg, 'w') as f:
    json.dump(data, f, indent=2)
with open(os.path.join(snap, 'chat_template.jinja'), 'w') as f:
    f.write(tmpl)
"
echo "FETCHDONE $(date +%H:%M:%S)"
