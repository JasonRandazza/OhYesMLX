# The MoE column set: LFM2.5-8B-A1B, 8 B total / 1 B active, 32 experts, top-4.
#
# Same shape as the dense grid in gridspec.sh -- one run per runtime, --study format holding
# the runtime constant -- so the two grids are read the same way and neither is a special case.
#
# STANDING CAVEAT, carried in every table this column produces: 32 experts is eight times
# fewer than the 256-expert checkpoint stock mlx-lm turns into token salad. A clean result
# here validates the machinery on MoE and does NOT exonerate stock mlx-lm on high-expert-count
# MoE. That question is Phase 4's, and it is answered there.
H=$HOME/.cache/huggingface/hub
S4="$H/models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/snapshots"
Q4="$H/models--stamsam--LFM2.5-8B-A1B-oQ4/snapshots"
QE="$H/models--brainworkup--LFM2.5-8B-A1B-oQ4e/snapshots"
OQ="$H/models--mlx-community--LFM2.5-8B-A1B-OptiQ-4bit/snapshots"
JG="$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots"

# One snapshot per repo; resolve the hash rather than pinning it, since nothing downloaded it yet.
for v in S4 Q4 QE OQ JG; do
  eval "d=\$$v"
  eval "$v=\$(ls -d \"\$d\"/*/ 2>/dev/null | head -1 | sed 's:/$::')"
done

CELLS_mlxlm="stock4bit__mlxlm=$S4,oq4__mlxlm=$Q4,oq4e__mlxlm=$QE,optiq__mlxlm=$OQ"
CELLS_omlx="stock4bit__omlx=$S4,oq4__omlx=$Q4,oq4e__omlx=$QE,optiq__omlx=$OQ"
CELLS_optiq="stock4bit__optiq=$S4,oq4__optiq=$Q4,oq4e__optiq=$QE,optiq__optiq=$OQ"
CELLS_vmlx="stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE,jang2l__vmlx=$JG"
CELLS_osaurus="oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ,jang2l__osaurus=$JG"
