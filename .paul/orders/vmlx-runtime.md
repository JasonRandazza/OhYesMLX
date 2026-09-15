GOAL: add vMLX 1.6.59 as the fifth runtime, so JANG has two independent implementations and can
be studied with one variable moving.

FILES YOU MAY EDIT: ohyesmlx/runtimes.py, tests/test_runtimes.py ONLY.

READ FIRST: `docs/runtimes/vmlx.md` — a 1,900-line capability reference written from vMLX's own
shipped source. It already answers the start command, the readiness signal, auth, the model-id
question, and the environment surface. Do not re-derive what it states; cite it and use it. If
it is silent or ambiguous on something you need, say so in your report rather than guessing.

WHAT TO BUILD: a `Vmlx(Runtime)` subclass beside `Omlx` and `Optiq`, registered in `RUNTIMES`
on a port no other runtime uses (mlxlm 8081, osaurus 1337, omlx 8100, optiq 8080). Implement
`start_command`, `stop_command`, `version_command`/`parse_version`, `model_id_candidates`,
`api_key`, and `build_command` if it needs a scratch tree the way `Omlx` does.

FOUR THINGS THE AUDIT FLAGS THAT YOU MUST HANDLE:

1. **There is no `--version` flag.** `vmlx --version` errors. The base class returns a readable
   "unknown: ..." string rather than raising when a version cannot be had — read how, and pick
   the most honest available provenance. §9.4 of the audit covers this.
2. **The CLI on PATH is a wrapper.** `~/.local/bin/vmlx` execs the bundled console script in
   place, because those scripts resolve python3 relative to their own directory and a symlink
   breaks them. Use the PATH name.
3. **438 VMLX_*/VMLINUX_* environment variables are read from the source and appear in no start
   command.** The audit says the ambient environment must be treated as part of the start
   command. You cannot pin 438 variables; say in your report what you think the right mechanism
   is (the `Osaurus.check_host_state` baseline-capture pattern is the existing precedent) and
   implement NOTHING beyond your two files.
4. **Readiness comes from the log, never the port.** Read how `Omlx` and `MlxLm` do it and
   follow that. `/health` needs no API key; `/v1/models` does.

ACCEPTANCE: pytest -q green from a 243 baseline, no regressions. Tests must follow the existing
per-runtime patterns in tests/test_runtimes.py — start command shape, model-id candidate order,
version parsing including the no-version-flag path, and scratch cleanup if you build one. Do not
start a server, load a model, or send a request. Do not touch measure.py, report.py, cli.py,
transport.py, coherence.py.
