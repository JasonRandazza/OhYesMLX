# The 35B MoE column set: Qwen3.6-35B-A3B (35.95 B total, 256 routed experts, 8 routed/tok, hybrid attention).
#
# Formats:
#   stock4bit: mlx-community/Qwen3.6-35B-A3B-4bit
#   optiq:     mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit
#   oq4:       Jundot/Qwen3.6-35B-A3B-oQ4
#   jangtq4:   JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4
#
# Study design: docs/research/2026-09-19-v3-phase1-35b-study-design.md
H=$HOME/.cache/huggingface/hub
S4="$H/models--mlx-community--Qwen3.6-35B-A3B-4bit/snapshots"
OQ="$H/models--mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit/snapshots"
Q4="$H/models--Jundot--Qwen3.6-35B-A3B-oQ4/snapshots"
JG="$H/models--JANGQ-AI--Qwen3.6-35B-A3B-JANGTQ4/snapshots"

# Resolve snapshot paths
for v in S4 OQ Q4 JG; do
  eval "d=\$$v"
  eval "$v=\$(ls -d \"\$d\"/*/ 2>/dev/null | head -1 | sed 's:/$::')"
done

# Fallback for OptiQ if flat layout directory is used:
if [ -z "$OQ" ] && [ -d "$H/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit" ]; then
  OQ="$H/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit"
fi

# Candidate cell sets per runtime (filtered by loadability probe verdicts before running)
CELLS_mlxlm="stock4bit__mlxlm=$S4,oq4__mlxlm=$Q4,optiq__mlxlm=$OQ"
CELLS_omlx="stock4bit__omlx=$S4,oq4__omlx=$Q4,optiq__omlx=$OQ"
CELLS_optiq="stock4bit__optiq=$S4,oq4__optiq=$Q4,optiq__optiq=$OQ"
CELLS_vmlx="stock4bit__vmlx=$S4,oq4__vmlx=$Q4,optiq__vmlx=$OQ,jangtq4__vmlx=$JG"
CELLS_osaurus="stock4bit__osaurus=$S4,oq4__osaurus=$Q4,optiq__osaurus=$OQ"
