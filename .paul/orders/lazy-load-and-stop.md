GOAL: three fixes, all found by live probes today. A lazy loader's cost must be recorded, a
stopped Osaurus must actually be gone, and the Osaurus doc must carry the repo-name rule.

FILES YOU MAY EDIT: ohyesmlx/measure.py, ohyesmlx/report.py, ohyesmlx/runtimes.py,
tests/test_measure.py, tests/test_report.py, tests/test_runtimes.py,
docs/runtimes/osaurus.md.

## FIX 1 — first_request_s (the important one)

Contract is pinned in docs/interfaces.md, section "cold_load_s alone cannot be compared across
runtimes". Read it and implement exactly that.

`CellResult` gains `first_request_s: float | None` — the latency of the FIRST WARMUP request of
the COLD VISIT. Same visit that sets cold_load_s, None on later visits. Follow how cold_load_s
already decides "this is the cold visit"; do not invent a second rule.

MEASURED, no warmups, same artifact, three requests each:

    mlx-lm  ready 3.32s | 0.47 0.40 0.41 | hides 0.07
    oMLX    ready 3.12s | 3.93 0.42 0.42 | hides 3.51   <-- lazy loader
    optiq   ready 4.14s | 0.31 0.27 0.27 | hides 0.04
    vMLX    ready 9.09s | 0.51 0.43 0.41 | hides 0.10

Confirmed on two further artifacts: oMLX hid 3.85s and 3.08s.

report.py: surface it as its own column, and add a row note when
`first_request_s` exceeds the median measured request latency by a wide margin — that gap is a
load the runtime deferred, and a reader must not read it as warm-up noise. YOU choose the
threshold, state it as a named constant, and justify the number in your report. Do not fold it
into cold_load_s and do not invent a combined metric column; the contract says a comparison
uses the sum, it does not say the harness publishes the sum.

## FIX 2 — Osaurus.stop() leaks the process

`osaurus stop` frees port 1337, `_shutdown` sees the port free and returns — and the app
process survives. A 5-format probe plus two manual tests left SEVEN
`/Applications/osaurus.app/Contents/MacOS/osaurus --launched-by-cli` processes resident for
~50 minutes. A full grid run would leak about ten mid-run, each holding weights, contending for
the unified memory the harness is trying to measure. The project's rule is that exactly one
runtime holds weights at any moment; a freed port satisfies its letter and breaks its substance.

Make Osaurus's stop verify the PROCESS is gone, not only the port. Read how `_shutdown` and
`await_port_free` work and extend that path rather than bolting a second mechanism beside it.
Only ever terminate a process this harness started — never sweep by name, because
`osaurus mcp` is a long-running user process on this machine and killing it would be
unacceptable. SIGTERM is ignored by these instances; SIGKILL works.

## FIX 3 — docs/runtimes/osaurus.md

Add the repo-name rule: Osaurus serves from its own catalogue and names models after the repo,
lowercased, so an HF-cache path ending in a commit hash never resolves. Live `/v1/models`
returned `qwen3.5-4b-4bit, qwen3.5-4b-oq4, qwen3.5-4b-oq4e, qwen3.5-4b-optiq-4bit,
qwen3.5-4b-jang_4s`. Note also that Osaurus discovers the Hugging Face cache on its own — all
five appeared without being copied into ~/MLXModels — and that it LISTS `qwen3.5-4b-4bit` and
then answers "not installed or registered with any provider" when asked to serve it.

## ACCEPTANCE

pytest -q green from a 305 baseline, no regressions. Tests must cover: first_request_s is the
cold visit's first warmup and None on later visits; a cell with no warmups records None; the
deferred-load note fires above the threshold and not below; Osaurus stop does not return while
its process lives. Red-check every fix and report that you did.

Do not start a server, load a model, or send a request. Do not touch transport.py,
coherence.py, token_counter.py, cli.py.
