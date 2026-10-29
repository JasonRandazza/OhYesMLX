# Order: Phase 2 research -- how a fresh Mac user installs each engine (v5.0, no code)
Why: Phase 2 builds engine detection and a consented installer. Plans must be data (`Plan` in docs/interfaces.md, "v5.0 -- Onboarding shapes").
Deliverable: ONE new file docs/research/2026-10-29-engine-install-paths.md. Touch nothing else (no code, no git, no downloads, no installs, no server starts).
Engines: Osaurus, oMLX, OptiQ, mlx-lm, vMLX. (MTPLX is out of scope.)
For each engine answer, labelling every claim VERIFIED (read from primary source or this machine) / CLAIMED (vendor docs only) / INFERRED:
 1. Official install route for a user with no dev tools: GUI app (dmg/cask/release URL) or command (pip/pipx/uv/brew)? Exact URL or command.
 2. Download size and disk after install (this machine has them installed: measure with `du`, read paths from docs/runtimes/<name>.md and ohyesmlx/runtimes.py).
 3. Prerequisites: Python version, Xcode CLT, Homebrew, admin password, macOS minimum.
 4. How to detect "installed" without launching a server, and how to read its version, from files/binaries only (cite the path/command that works on this machine).
 5. How the harness finds it today (ohyesmlx/runtimes.py: binary path, venv, app bundle) -- the detector must reuse that, not copy it.
 6. Risks: login items, relaunch behaviour, background daemons, anything that touches the user's system beyond the install (see AGENTS.md hazards for Osaurus and oMLX).
Search tools (use them; they are registered for you): `searxng` (self-hosted on Omarchy, free, use FIRST for every search and
`web_url_read` to read pages), `tavily` (extraction when a page is JS-heavy or garbled; basic depth, 3-5 results, one targeted query),
`exa` (semantic discovery, e.g. finding a project's real repo or release page; free tier, make each call count). Tavily and Exa are quota-limited.
Primary sources: each project's repo/README/releases and the installed bundles on this machine. A negative claim ("cannot install via X") needs source evidence, not absence of a flag (AGENTS.md).
End with a table: engine | kind (guided_download|command) | source | size | needs_admin | detect | version probe.
Acceptance: all five engines, every row of the table filled or marked UNKNOWN with why. Report DONE or BLOCKED.
