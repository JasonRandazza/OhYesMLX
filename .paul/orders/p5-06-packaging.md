# Order: plan 05-06 — the .app bundle, bundled Python, ad-hoc signing, SBOM, bundle checks (T5.6)

Execute `.paul/phases/v5-onboarding/05-06-PLAN.md` Tasks 1-2 (read it whole; AC-1..AC-5 and AC-7 are the bar;
AC-6 and the checkpoint are the coordinator's — do not attempt them, do not use sudo).
Packaging rules: `docs/threat-model.md` §10 (grep "## 10."). Launcher spec: `docs/interfaces/v5-app.md` "The launcher".

Files: exactly the plan's `files_modified`. Nothing in `ohyesmlx/` or `tests/`.
You MAY run `scripts/fetch_python_standalone.sh` (one 27 MB download, the plan's purpose; its sha256 is in the plan)
and `scripts/build_app.sh`. You may write `scripts/check_bundle.sh` but the coordinator runs it (it launches the GUI app).
No notarization, no Developer ID, no upload anywhere.
Suites: `cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test` (baseline 74);
test-venv pytest stays 1371.

Report: per AC the command and its output (codesign verify, the zip and sbom paths and sizes); the AC-7 test; what you
did not verify.
