# Order: OptiQ MTP depth check wording + artifact shape gate (v3.1)
Files you may touch: ohyesmlx/runtimes.py, tests/test_runtimes.py, docs/runtimes/optiq.md. Touch nothing else.
Context: docs/research/2026-09-25-mtp-depth-sweep.md §4 and Open questions 5-6. Logs:
results/logs/optiq-20260925T064114-21379.log (4B), results/logs/optiq-20260925T065802-34585.log (35B).
1. `Optiq.mtp_depth_missing`: when neither the ready line nor an attach-failure marker is present, the
   message says "it says nothing about why". If the log holds a Python traceback, quote its final
   exception line (e.g. `TypeError: 'NoneType' object is not subscriptable`) and its innermost
   `File ..., line N` frame; otherwise say "prints no line this check reads". Same window rules as today.
2. `optiq_mtp_refusal`: the 35B's sidecar loads but its head shapes do not fit the block
   (`(256, 512, 2048)` vs `(256, 512, 256)`). Read the sidecar's safetensors header with stdlib only
   (8-byte little-endian length + JSON) and refuse (N/A with the reason) when a head tensor's shape
   cannot fit what OptiQ's own loader expects. Derive the expected-shape rule from OptiQ's shipped
   source (installed mlx-optiq 0.5.13; cite file:line). If the rule depends on quantization packing
   you cannot determine from config + header, go BLOCKED with what you found -- do not guess.
   Check against both real artifacts: the 35B must refuse; the 4B (`mlx-community/Qwen3.5-4B-OptiQ-4bit`)
   must still pass the gate.
3. docs/runtimes/optiq.md: record both behaviours where the MTP gate is described.
Acceptance: tests per item with red-checks; suite green (verify-venv python -m pytest -q). No git, no
server starts. Report DONE or BLOCKED.
