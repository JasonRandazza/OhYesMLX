# Order: Phase 5 prototype gate — onboarding flow state model (logic prototype); one deliverable
Throwaway. Answers ONE question before Phase 5 is planned: **does the app's screen-flow state model handle every case the real backend produces?** Jason (non-developer reader) will click through it.
Write exactly one new file: `prototypes/phase5-onboarding-flow.prototype.html` (create the directory). Touch nothing else. No tests, no framework, no server, no external URL except an optional pinned Google Font; everything inline; opens by double-click.

## Ground truth (read, cite file:line in an HTML comment beside each backend fact)
docs/interfaces/v5-onboarding.md, docs/interfaces/v5-quickbench.md, docs/interfaces/v5-hardening.md, ohyesmlx/server.py (`_ENDPOINTS`, `_JOB_ARGS`, job states, refusal codes incl. busy/one-job-at-a-time, cancel), ohyesmlx/engines.py (plan kinds: pip vs guided app download + verify-after; `step_failed` with `payload.output_tail`), ohyesmlx/fetch.py (download refusals: busy, disk, integrity), ohyesmlx/quickbench.py (plan fields; cell outcomes PASS/FAIL/N/A/SKIPPED and their reasons: port in use "quit it first", Osaurus app running, `osaurus: false`, could not start; `not_evicted`), ohyesmlx/recommend.py (picks/excluded/unsupported_reason, `downloaded`, `measured_here`). Real responses from a clean account: `.paul/phases/v5-onboarding/045-03-evidence/run2-20261113T192854Z.json` (use for fixture values). Use graphify to locate code; read line ranges only. Any behaviour you cannot confirm in code: mark it "ASSUMED" in the UI.

## Structure (LOGIC prototype rules)
1. Top: title "OhYesMLX — onboarding flow (PROTOTYPE, throwaway)" and the question above in one plain paragraph.
2. A pure `<script>` module, no DOM access: `initialState(fixture)` and `reduce(state, action) -> state` (or an explicit machine), modelling: screen (launching, couldnt_start, unsupported, welcome, your_mac, engines, models, benchmark, results); the backend link (starting / up / gone); the ONE running job (none | install X | download R | evict R | quickbench R) with progress/events; per-engine status (installed, plan kind, last error + output tail); per-model status (not downloaded / downloading fraction / downloaded / excluded with reason); quickbench plan + per-engine cell outcomes; consent flags (install consent, Osaurus pin consent). Illegal actions (second job while one runs, quickbench before download, install without consent) return the state with a visible `refusal` naming the backend code, exactly as the backend would answer.
3. Current-state panel: labelled fields in plain words (not JSON), "what just changed" line after each click.
4. Free-play buttons, domain language ("Install OptiQ", "Download Qwen3-0.6B", "Start quick benchmark", "Backend crashes", "Quit app mid-download", "Relaunch", "Install fails", "User opens oMLX download page", "User says they installed it", etc.).
5. Guided walkthrough tabs (each resets state, each step a real button, one-line "watch for"): (a) happy path on a fresh Mac; (b) pip install fails, tail shown, retry; (c) try a download while an install runs (busy); (d) quickbench before the model is downloaded; (e) quickbench where one engine's port is busy and vMLX cannot start — cells skipped/N/A with reasons, run still completes; (f) unsupported Mac (Intel or <8 GB); (g) quit mid-download, relaunch, recovery; (h) a model too big for the disk is excluded with its reason; (i) Osaurus: user declines the pin.
6. Styling: restrained, one accent colour, readable at 400 px wide. Theme tokens on `:root` with a dark palette under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])` and again under `:root[data-theme="dark"]`; explicit body background. A `<title>` first. No `<html>/<head>/<body>` tags (it is published as a page fragment); it must still open by double-click.
7. A short "Open questions this surfaced" section at the bottom, filled in by you: each place the backend's behaviour forces a UI decision Phase 5 must make (e.g. what the app shows while the one job slot is taken).

Report: file size, the action list, the scenario list, every ASSUMED item, the open questions. Under 300 words. Do not commit.

## Retry note (attempt 1: API server error mid-way through ONE giant write, 68K output tokens lost)
Write in STAGES, each a separate tool call, the file growing each time; never one write over ~12 KB:
1. Skeleton: title, question, theme tokens/CSS, empty panels (write the file now, before reading more).
2. The pure state module (initialState + reduce + fixture) — append/edit.
3. Renderer + free-play buttons — append/edit.
4. Scenarios a–e, then f–i, then the open-questions section — one edit each.
Whole file ≤ 40 KB. Cite backend facts in short HTML comments (`<!-- server.py:653 -->`), not prose. Read only what you need: graphify first, line ranges only.
