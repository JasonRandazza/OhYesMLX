GOAL: two runtime defects the live grid probe found. Osaurus cannot be driven at all, and oMLX
reports a cold load for a model that never loaded.

FILES YOU MAY EDIT: ohyesmlx/runtimes.py, tests/test_runtimes.py ONLY.

DEFECT 1 — Osaurus model ids. Every Osaurus cell fails with "osaurus exited before it served
'osaurus/stock4bit'". Osaurus serves from its own catalogue and names models after the REPO,
lowercased. Measured live today, `GET /v1/models` on a running Osaurus returns:

    qwen3.5-4b-4bit, qwen3.5-4b-oq4, qwen3.5-4b-oq4e, qwen3.5-4b-optiq-4bit,
    qwen3.5-4b-jang_4s, nanbeige4.2-3b-jang_6m, ornith-1.0-35b-jang_4m, foundation

`Osaurus.model_id_candidates` builds from `name_forms(artifact_dir)`. In Hugging Face cache
layout the artifact dir is `.../models--<org>--<name>/snapshots/<commit-hash>`, so name_forms
yields the COMMIT HASH — never a name Osaurus answers to. Derive the repo name from the
`models--<org>--<name>` directory above `snapshots/`, lowercased, and put it at the front of
the candidate list. Keep every existing candidate after it; a non-cache path must still work
exactly as it does today. Read `name_forms` before changing anything and prefer extending it
over special-casing Osaurus if other runtimes would benefit — say which you chose and why.

Verified live: with the right id, Osaurus served oQ4, oQ4e, OptiQ and JANG_4S, all coherent.
Only `qwen3.5-4b-4bit` failed, and it failed differently — see defect 2's theme.

DEFECT 2 — a cold load for a model that never loaded. oMLX was given a JANG artifact it cannot
read. It bound its port, listed the model in /v1/models, satisfied `await_ready`, and returned
`cold_load_s = 2.15`. Only the chat request revealed the truth:

    HTTP 409: Model '<hash>' failed to load: VLM load failed ...; LLM fallback also failed:
    Expected shape (248320, 640) but received shape (248320, 320)

runtimes.py's own docstring already says readiness is not the port, and for mlx_lm.server not
the model list either. This is the third runtime with that disease: Osaurus also LISTS
`qwen3.5-4b-4bit` in /v1/models and then answers "not installed or registered with any
provider" when asked to serve it. **Every runtime here advertises models it cannot serve.**

Strengthen readiness so a runtime that lists a model it cannot serve fails to start rather than
reporting a load time. Read how `MlxLm` readiness already combines the model id with a log
scan, and follow that shape. Do NOT send a chat completion from inside readiness — a measured
request must not be preceded by an unmeasured one that warms a cache or shifts a timer. If you
conclude readiness genuinely cannot distinguish these without a request, say so plainly and
implement the log-scan half only; a BLOCKED finding here is more valuable than a guess.

ACCEPTANCE: pytest -q green from a 294 baseline. Tests must cover: an HF-cache path yields the
lowercased repo name first for Osaurus; a plain directory path is unchanged; a runtime whose log
shows a load failure does not return a handle even when /v1/models lists the id. Red-check both
and report that you did. Do not start a server or load a model.
