#!/bin/sh
# Fetch the five LFM2.5-8B-A1B artifacts the MoE format axis needs (Phase 3, plan 03-02).
#
# 23.3 GB. Repo ids come from docs/research/2026-09-15-small-model-candidates.md, which
# verified that all of them declare num_experts 32 and num_experts_per_tok 4 -- the artifacts
# have to agree about the architecture or the column varies two things.
#
# v1 originally pinned "no new model download". That constraint's stated reason was 36 GiB of
# free disk; there are now 280 GiB, and Jason lifted it for what v1 needs on 2026-09-16.
#
# Do not run this while a grid is measuring. A 23 GB download competes for disk with the model
# loads that cold_load_s is timing.
set -eu
HF=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/hf
for repo in \
  mlx-community/LFM2.5-8B-A1B-MLX-4bit \
  stamsam/LFM2.5-8B-A1B-oQ4 \
  brainworkup/LFM2.5-8B-A1B-oQ4e \
  mlx-community/LFM2.5-8B-A1B-OptiQ-4bit \
  JANGQ-AI/LFM2.5-8B-A1B-JANG_2L
do
  echo "=== $repo $(date +%H:%M:%S)"
  "$HF" download "$repo" >/dev/null || echo "FAILED $repo"
done
echo "FETCHDONE $(date +%H:%M:%S)"
