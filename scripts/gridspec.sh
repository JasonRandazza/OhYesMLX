H=$HOME/.cache/huggingface/hub
S4="$H/models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"
Q4="$H/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
QE="$H/models--uingei--Qwen3.5-4B-oQ4e/snapshots/2e232d525d5df5e7a6eece4b03b17087e6b3c3ac"
OQ="$H/models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9"
JG="$H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775"

# One run per runtime column. --study format holds the runtime constant, which is exactly
# what each column is. The grid is the join of the five.
CELLS_mlxlm="stock4bit__mlxlm=$S4,oq4__mlxlm=$Q4,oq4e__mlxlm=$QE,optiq__mlxlm=$OQ"
CELLS_omlx="stock4bit__omlx=$S4,oq4__omlx=$Q4,oq4e__omlx=$QE,optiq__omlx=$OQ"
CELLS_optiq="stock4bit__optiq=$S4,oq4__optiq=$Q4,oq4e__optiq=$QE,optiq__optiq=$OQ"
CELLS_vmlx="stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE,jang4s__vmlx=$JG"
CELLS_osaurus="oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ,jang4s__osaurus=$JG"
