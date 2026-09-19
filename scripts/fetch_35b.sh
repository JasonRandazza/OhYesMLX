#!/bin/bash
# Fetch the four Qwen3.6-35B-A3B artifacts Plan 03-01 measures (Milestone v3 Phase 1: the
# 35B MoE class on Apple Silicon).
#
# 85.96 GB / 80.05 GiB across the four, against 186 GiB free on this host (df, 2026-09-19).
#
# The four repo ids are pinned here because the study's four cells are one architecture and four
# quantizations. Verified from each repo's own config.json on 2026-09-19 -- all four declare
# qwen3_5_moe_text, 40 layers, 256 routed experts, 8 routed per token, hidden_size 2048,
# moe_intermediate_size 512, full_attention_interval 4, mtp_num_hidden_layers 1, vocab 248320.
# The artifacts have to agree about the architecture or the column varies two things, and a
# disagreement there would be invisible in every table it produced.
#
# Sizes below are the current revision's file sum from the HF API (?blobs=true), sidecar files
# included -- which is what ohyesmlx.measure.artifact_bytes records as a cell's disk_bytes:
#   mlx-community/Qwen3.6-35B-A3B-4bit         20,429,169,263  (19.03 GiB)
#   mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit   24,693,956,069  (23.00 GiB, incl. optiq/ sidecars)
#   Jundot/Qwen3.6-35B-A3B-oQ4                 21,125,808,699  (19.68 GiB)
#   JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4           19,707,916,875  (18.35 GiB)
#
# A flat-layout copy of the OptiQ artifact already exists at
# ~/.cache/huggingface/hub/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit (24,693,961,658 bytes,
# byte-complete against the revision above). `hf download` writes the hub layout instead, so
# this script leaves a second ~23 GiB copy of that one artifact on disk. Point the OptiQ cell at
# the existing directory, or skip that repo, if the duplication is not wanted.
#
# Do not run while a benchmark is measuring. An 86 GB download competes for the disk
# cold_load_s is timing, and the harness cannot detect the contention.
set -eu
HF=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/hf
for repo in \
  mlx-community/Qwen3.6-35B-A3B-4bit \
  mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit \
  Jundot/Qwen3.6-35B-A3B-oQ4 \
  JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4
do
  echo "=== $repo $(date +%H:%M:%S)"
  if "$HF" download "$repo" >/dev/null; then
    echo "OK $repo $(date +%H:%M:%S)"
  else
    echo "FAILED $repo $(date +%H:%M:%S)"
  fi
done
echo "FETCHDONE $(date +%H:%M:%S)"
