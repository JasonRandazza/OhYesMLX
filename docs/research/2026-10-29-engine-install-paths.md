# How a fresh Mac user installs each engine — v5.0 Phase 2 research

Written 2026-10-29 for Phase 2 (`engines.detect_all`, `engines.install_plan`). Scope: **Osaurus, oMLX,
OptiQ, mlx-lm, vMLX**. MTPLX is out of scope for v5.0 (Decision D2).

No code was written, no engine was installed or downloaded, and no server was started for this document.
Every fact below was read from a primary source (the project's repo/README/release assets, PyPI metadata)
or measured on this machine. Commands used are listed in §7 so each claim can be reproduced.

**Evidence labels.**

- **VERIFIED** — read from a primary source or measured on this machine; the command or URL is given.
- **CLAIMED** — asserted by vendor documentation only; not reproducible here without an install.
- **INFERRED** — follows from something VERIFIED but is not itself observed.

**This machine.** macOS 27.2 (build 26B123), arm64 (`sw_vers`, VERIFIED). App bundles are at
`/Applications`, user data under `$HOME`. Installed versions on 2026-10-29: Osaurus 0.25.28, oMLX 0.7.2,
OptiQ 0.5.13, mlx-lm 0.31.3, vMLX 1.6.59.

**The shapes this feeds.** `EngineStatus` and `Plan` are pinned in `docs/interfaces.md:1361-1381`; the
decision that the three app engines are guided downloads is D2 in `.paul/phases/v5-onboarding/PLAN.md:15`.
One conflict between those two documents is recorded in §6.1 and is **not** resolved here.

---

## 1. Osaurus

Native Swift app; the bundle contains no Python at all (`docs/runtimes/osaurus.md` §0 — the only `.py` in
the bundle is a vendored font script, VERIFIED from that doc's bundle inspection).

### 1.1 Install route

**GUI app (guided download), or the same cask.** Both are vendor-documented:

- `brew install --cask osaurus` — CLAIMED (README install block; `brew info --cask osaurus` on this
  machine reports version 0.25.28, "Not installed", artifacts `Osaurus.app` and
  `/Applications/Osaurus.app/Contents/Helpers/osaurus`, requirements arm64 and macOS >= 15 — VERIFIED
  from Homebrew's local metadata).
- Direct DMG: `https://github.com/osaurus-ai/osaurus/releases/latest/download/Osaurus.dmg` — the
  README's own download button; the release API lists `Osaurus.dmg` and `Osaurus-0.25.28.dmg` at
  85.9 MB each (VERIFIED, GitHub releases API).

Two builds ship per release (CLAIMED — README and `docs.osaurus.ai/installation`):

| Build | Size | Notes |
|---|---|---|
| `Osaurus-<version>.dmg` | 85.9 MB (release asset) | Standard; pick/download a model during onboarding |
| `Osaurus-<version>-full.dmg` | ~3.6 GB (docs) / ~4 GB (README) | Raptor 0.6 bundled; first launch installs it into `~/MLXModels` |

On this machine the app was **not** installed by the cask: `brew info --cask osaurus` says "Not
installed" while `/Applications/osaurus.app` exists, and `pkgutil --pkgs` has no Osaurus receipt
(VERIFIED). The installed spelling is lowercase `osaurus.app`; the cask artifact is `Osaurus.app`
(VERIFIED) — see §1.4.

### 1.2 Size on disk

- Download: **85.9 MB** (0.25.28 standard DMG; VERIFIED from the release API).
- Installed app: **208 MB** (`du -sh /Applications/osaurus.app`; VERIFIED). Breakdown: MacOS 138 MB,
  Resources 42 MB, Helpers 25 MB, Frameworks 3 MB.
- After first launch: `~/.osaurus/config` is 100 KB (VERIFIED). Everything else under `~/.osaurus/` is
  user data. On this machine the directory totals **86 GB**, of which `cache/kv_v2` is **83 GB** — a
  persistent KV cache — and downloaded models live separately in `~/MLXModels` (**128 GB** here)
  (VERIFIED, `du`). None of that is install size, but it is what the disk actually does after use.

### 1.3 Prerequisites

- **Apple Silicon** — required (README; CLAIMED).
- **macOS minimum** — three sources disagree: README says 15.5+, the Homebrew cask declares
  `macOS >= 15`, and the installed bundle's `LSMinimumSystemVersion` is `15.0` (VERIFIED). The strictest
  figure that has a primary source is 15.5 (vendor docs), but the shipped bundle declares 15.0.
- **Python / Xcode CLT / Homebrew** — not needed for the DMG route. Homebrew is needed only for the cask
  route.
- **Admin password** — none for the drag-install. `/Applications` is writable by this account
  (`test -w /Applications` → yes, VERIFIED) and there is no installer package (`pkgutil` shows no
  receipt, VERIFIED). `spctl` accepts the app as "Notarized Developer ID" (VERIFIED). A standard
  non-admin account would install to `~/Applications` instead; that is a macOS rule, not this app's.

### 1.4 Detecting "installed", and reading the version, without launching anything

- **App bundle:** `/Applications/osaurus.app` (installed here) or `/Applications/Osaurus.app` (the cask's
  artifact name). The CLI itself searches for both spellings (`docs/runtimes/osaurus.md` §1.3), and
  `doctor` has a `duplicateBundles` verdict for the case both exist. A detector must check **both**
  spellings: on a case-insensitive volume they are one file, on a case-sensitive volume they are not.
- **CLI on PATH:** `~/.local/bin/osaurus` → `/Applications/osaurus.app/Contents/Helpers/osaurus`
  (VERIFIED, `ls -l`) and `/opt/homebrew/bin/osaurus` → the same target (VERIFIED), even though the cask
  is not installed here.
- **Version from a file, no process started:**
  `/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/osaurus.app/Contents/Info.plist`
  → `0.25.28` (VERIFIED). `CFBundleIdentifier` is `com.dinoki.osaurus` (VERIFIED).
- **Do not probe with flags.** The project's own record shows that on most Osaurus subcommands an
  unrecognised flag is not rejected: `osaurus serve --help` **started the server**, `osaurus stop --help`
  **stopped a running one**, and `osaurus pull --help` began a download (`docs/runtimes/osaurus.md` §0.1,
  observed 2026-09-15). The documented version command is `osaurus --version` / `osaurus version`
  (CLAIMED — `docs.osaurus.ai/installation`, §2.1 of the runtime doc); it was **not** run for this
  document, because that CLI's flags are not reliably read-only.

### 1.5 What the harness has today (`ohyesmlx/runtimes.py`)

- Registry: `RUNTIMES["osaurus"]`, port **1337** (`runtimes.py:3391-3398`).
- Start: `("osaurus", "serve", "--port", "1337", "--yes")` — a bare PATH name, no absolute path
  (`runtimes.py:2110`). The app decides the model and every tuning value from `~/.osaurus/config`.
- Version: `("osaurus", "doctor", "--json", "--redact")`, parsed from `apps[].version` with a preference
  for the running bundle (`runtimes.py:2187`, `:2253-2270`). This is the harness's run provenance, not a
  detector: `doctor` is documented as diagnosing server startup and model storage, so it is heavier than
  a file read.
- Absolute path constant: `OSAURUS_EXECUTABLE = "/Applications/osaurus.app/Contents/MacOS/osaurus"`
  (`runtimes.py:126`), used by `_resident_osaurus_pids` to refuse a start while a stray app is alive —
  matched by **full executable path**, never by the name `osaurus`, because `osaurus mcp` is a
  long-running user process (AGENTS.md; `docs/runtimes/osaurus.md` §1.2).

**Reuse for the detector:** presence = `shutil.which("osaurus")` or either bundle spelling or
`OSAURUS_EXECUTABLE`'s parent; version = `CFBundleShortVersionString` (file read), falling back to the
existing `Osaurus.version()` only when the harness's own probe is acceptable. Do not copy the path
literals into `engines.py` — they are already in `runtimes.py`.

### 1.6 Risks beyond the install

- **Sparkle auto-update.** `SUFeedURL = https://osaurus-ai.github.io/osaurus/appcast.xml` and
  `SUEnableAutomaticChecks = true` in the installed bundle (VERIFIED, `Info.plist`). Vendor docs say the
  app updates itself when opened; the runtime doc records this as a version-drift hazard under a running
  benchmark.
- **Menu-bar accessory.** `LSUIElement` is `true` (VERIFIED), so it has no dock icon and is easy to miss.
  There is also a Background Task Management entry: `sfltool dumpbtm` lists `com.dinoki.osaurus`, type
  app, disposition `[enabled, disallowed, notified]`, last use 2026-10-29 09:49 (VERIFIED). That is a
  login/background item surface the onboarding screen should mention.
- **Relay through MCP.** `osaurus mcp` is a stdio client of the GUI app; any MCP host that registers it
  relaunches the app on session start, with launchd as parent (`docs/runtimes/osaurus.md` §1.2,
  AGENTS.md). This is why the harness scans for resident app processes by executable path.
- **Stop does not quit.** `osaurus stop` frees port 1337 but leaves the app alive at ~900 MB (AGENTS.md;
  `docs/runtimes/osaurus.md`). A stale instance then blocks the harness's next start.
- **Telemetry.** Anonymous usage analytics via Aptabase are described as on (README); Sentry crash
  reporting is **opt-out, on by default** (README). Not measured here.
- **Disk after use** is dominated by `~/.osaurus/cache/kv_v2` (83 GB here) and `~/MLXModels` (128 GB),
  not by the 208 MB app (VERIFIED, `du`).

---

## 2. oMLX

Native Swift/SwiftUI menubar app that ships its own CPython 3.11.10 and MLX site-packages inside the
bundle (`docs/runtimes/omlx.md` §1.1, VERIFIED from the installed bundle).

### 2.1 Install route

**GUI app (guided download), or Homebrew, or source — all three are documented** (README install
section):

- DMG: download from `https://github.com/jundot/omlx/releases`, drag to Applications. The app installs a
  `~/.omlx/bin/omlx` CLI shim (CLAIMED — README).
- Homebrew: `brew tap jundot/omlx https://github.com/jundot/omlx` then
  `brew install jundot/omlx/omlx` (`--with-custom-kernel` needs full Xcode) — CLAIMED.
- Source: `git clone`, `make install` (or `make install-no-kernels`) — CLAIMED.

**There is no single stable DMG URL.** Each release publishes one DMG per macOS generation:

| Release | Asset | Size |
|---|---|---|
| v0.7.2 (the version installed here) | `oMLX-0.7.2-macos15-sequoia.dmg` | 837.8 MB |
| v0.7.2 | `oMLX-0.7.2-macos26-27.dmg` | 875.2 MB |
| v0.7.3rc1 (currently `/releases/latest`) | `oMLX-0.7.3rc1-macos15-sequoia.dmg` | 839.6 MB |
| v0.7.3rc1 | `oMLX-0.7.3rc1-macos26-27.dmg` | 868.0 MB |

(VERIFIED, GitHub releases API.) Two consequences for the Plan: `source_url` must be the **releases
page**, not a fixed asset, and the app must pick the asset from the user's macOS. The current "latest"
is a release candidate that GitHub marks `prerelease: false` (VERIFIED), so a guided download today
would hand a new user an rc.

### 2.2 Size on disk

- Download: **837.8 MB** for the installed 0.7.2 Sequoia build (VERIFIED; 875.2 MB for the macOS 26-27
  build).
- Installed app: **1.7 GB** (`du -sh /Applications/oMLX.app`; VERIFIED). Resources alone are 1.6 GB —
  the bundle's Python and MLX framework; MacOS is 31 MB, signature 17 MB.
- After first launch: `~/Library/Application Support/oMLX` is 4.3 MB and `~/.omlx` holds
  `settings.json`, `model_settings.json`, `global_templates.json`, `bin`, `logs` (VERIFIED). The
  measured `~/.omlx/cache` is **69 GB** of paged SSD KV cache (VERIFIED, `du`), which is state the
  server writes during use, not install size.

### 2.3 Prerequisites

- **Apple Silicon** and **macOS 15.0+** (README requirements; the installed bundle's
  `LSMinimumSystemVersion` is `15.0`, VERIFIED).
- **Python 3.11–3.13** only for the Homebrew/source routes (README); the DMG route needs none — the
  bundle carries CPython 3.11.10 (VERIFIED by running it).
- **Xcode** only for native custom kernels: full Xcode with the Metal toolchain, or
  `make install-no-kernels` / plain `brew install` without `--with-custom-kernel` (CLAIMED — README).
  Without them GLM-5.2/MiniMax M3/Qwen3.5 silently use slower generic paths (CLAIMED).
- **Admin password** — none for the DMG (notarized; `spctl` accepts it as "Notarized Developer ID",
  VERIFIED; no pkg receipt). Homebrew itself needs an admin password to install, once.

### 2.4 Detecting "installed", and reading the version, without launching anything

- **App bundle:** `/Applications/oMLX.app` (VERIFIED; `CFBundleIdentifier` `app.omlx`,
  `LSMinimumSystemVersion` `15.0`).
- **CLI shim:** `~/.omlx/bin/omlx` — a 304-byte `sh` script that reads
  `~/Library/Application Support/oMLX/base-path` if present and `exec`s
  `/Applications/oMLX.app/Contents/MacOS/omlx-cli` (VERIFIED, file contents). `which -a omlx` finds it
  because `~/.omlx/bin` is on this user's PATH (VERIFIED). `docs/runtimes/omlx.md:71` also records
  `/opt/homebrew/bin/omlx` → `~/.omlx/bin/omlx`; **that symlink does not exist on this machine today**
  (VERIFIED, `ls`), so the runtime doc is stale on that point.
- **Version from a file:** `PlistBuddy -c 'Print :CFBundleShortVersionString'
  /Applications/oMLX.app/Contents/Info.plist` → `0.7.2` (VERIFIED).
- **Version from the CLI, no server:** `omlx --version` → `0.7.2` (VERIFIED). The shim `exec`s the
  bundle's `python -m omlx.cli --version`, which prints and exits; it does not start the server.
- The shim hardcodes `/Applications/oMLX.app`, so a moved or renamed bundle leaves it pointing at
  nothing, with no error beyond `exec` failing (`docs/runtimes/omlx.md` §1.2, VERIFIED reasoning from
  the file itself).

### 2.5 What the harness has today (`ohyesmlx/runtimes.py`)

- Registry: `RUNTIMES["omlx"]`, port **8100** (`runtimes.py:3391-3398`).
- Start: `("omlx", "serve", "--model-dir", <token>, ... "--port 8100" ... "--no-cache")` — bare PATH
  name (`runtimes.py:2331-2353`). The model directory is a per-run catalog token that `OmlxScratch`
  materialises; the detector must not reproduce that scratch logic.
- Version: `("omlx", "--version")` (`runtimes.py:2389`).
- There is no absolute oMLX path constant in `runtimes.py`.

**Reuse for the detector:** `shutil.which("omlx")`, then the absolute candidate
`~/.omlx/bin/omlx` whether or not PATH finds it (a fresh user may not have `~/.omlx/bin` exported).
Version from that same command or the plist.

### 2.6 Risks beyond the install

- **A server can outlive the install window.** The menubar app manages a server with auto-restart on
  crash (README, CLAIMED); `omlx start` on a Homebrew install delegates to `brew services`, i.e. a
  **launchd service that restarts on crash** (README, CLAIMED). Either can leave a process holding its
  port before the onboarding app asks to measure anything.
- **Port default differs from the harness.** oMLX's own zero-config default is port **8000** (README,
  CLAIMED); the harness always passes 8100.
- **SSD prefix cache survives restarts.** `~/.omlx/cache` is **69 GB** here (VERIFIED) and the harness
  explicitly puts the cache under per-run scratch and passes `--no-cache` unless the cell pinned
  `cache_state=on` (AGENTS.md; `runtimes.py:2345-2353`). Anything outside the harness does not get that
  protection.
- **Rewritten bootstrap file.** The server rewrites `~/.omlx/bin/omlx-cluster-python` on every start
  (`docs/runtimes/omlx.md` §1.3, VERIFIED from the installed file's own comment). A detector that reads
  files under `~/.omlx/bin` must not treat that as a stable artifact.
- **In-app auto-update** (README, CLAIMED). No Sparkle keys exist in `Info.plist` (VERIFIED absent), so
  the mechanism is the app's own, not Sparkle.
- **Bundle move breaks the shim** (§2.4). Reinstalling to a different path is the trigger.

---

## 3. OptiQ

A Python package, installed and documented as PyPI only (CLAIMED — install page). Nothing is installed as
an app bundle on this machine; the CLI is a console script in a venv (`docs/runtimes/optiq.md` §1.1,
VERIFIED).

### 3.1 Install route

**Command — PyPI is the only documented install surface:**

```sh
pip install mlx-optiq
```

(CLAIMED — `mlx-optiq.com/docs/install` and the PyPI project page.) The docs recommend an isolated
environment and give `uv venv .venv && source .venv/bin/activate && uv pip install mlx-optiq` and the
stock-`venv` equivalent (CLAIMED). Current PyPI version is **0.7.8**, wheel 1.8 MB (VERIFIED, PyPI
JSON API).

On this machine OptiQ is **0.5.13** in a venv at `~/Dev/tools/mlx-optiq/.venv`, reached through
`~/.local/bin/optiq` → `.venv/bin/optiq` (VERIFIED, `ls -l`; `optiq --version` → `mlx-optiq, version
0.5.13`).

### 3.2 Size on disk

- Download: **1.8 MB** wheel (0.7.8; VERIFIED). The sdist is 2.1 MB.
- Installed: **UNKNOWN for a clean install.** The vendor claims "~80 MB on disk including all
  dependencies" (CLAIMED). The venv here is **846 MB** (VERIFIED, `du -sh .venv`), but it contains
  packages outside mlx-optiq's declared dependencies — mlx 208 MB, pyarrow 106 MB, scipy 70 MB,
  transformers 50 MB, duckdb 43 MB, pandas 40 MB — so 846 MB is an upper bound for this environment,
  not the size of a clean install. The discrepancy is unexplained and must not be published as either
  number.
- Models are not part of the install: OptiQ downloads into the shared Hugging Face cache
  (`~/.cache/huggingface/hub`, CLAIMED docs; **177 GB** here, shared with mlx-lm — VERIFIED `du`).

### 3.3 Prerequisites

- **Python ≥ 3.11** — `requires_python: >=3.11` on PyPI and the install page (VERIFIED both).
- **Apple Silicon** for local inference; `optiq code` / `optiq lab` also run on Linux/Windows against a
  remote endpoint (CLAIMED — install page). macOS 14 (Sonoma)+ for local work (CLAIMED).
- **Xcode CLT / Homebrew** — not required by the package. `uv`/`pipx` are suggested, not required;
  Homebrew is only how the docs suggest getting `uv` (CLAIMED).
- **Admin password** — none for a venv, `uv tool`, or `pip --user`. Installing into a system Python
  would need one, but the docs steer away from that (CLAIMED).
- On a fresh Mac, stock `/usr/bin/python3` is **3.9.6** (VERIFIED), below the 3.11 floor, so the plan's
  steps must include obtaining a Python ≥ 3.11 before `pip install mlx-optiq` can succeed.

### 3.4 Detecting "installed", and reading the version, without launching anything

- **CLI on PATH:** `shutil.which("optiq")`. On this machine it resolves to
  `~/.local/bin/optiq` → `~/Dev/tools/mlx-optiq/.venv/bin/optiq` (VERIFIED). The console script's
  shebang is an absolute path into that venv, so the entry point breaks if the venv is moved
  (`docs/runtimes/optiq.md` §1.1, VERIFIED from the script).
- **File evidence of a specific version:** `<venv>/lib/python3.12/site-packages/mlx_optiq-0.5.13.dist-info/METADATA`
  with `Version: 0.5.13` (VERIFIED, read on this machine). This is the only file that survives the venv
  moving without the console script.
- **Version:** `optiq --version` → `mlx-optiq, version 0.5.13` (VERIFIED). The harness strips the
  `..., version ` prefix (`runtimes.py:2680-2696`).
- A `uv tool install` would place the script under `~/.local/bin` too (INFERRED from uv's tool layout;
  not installed that way on this machine).

### 3.5 What the harness has today (`ohyesmlx/runtimes.py`)

- Registry: `RUNTIMES["optiq"]`, port **8080** (`runtimes.py:3391-3398`).
- Start: `("optiq", "serve", "--model", <artifact>, ...)` — bare PATH name (`runtimes.py:2516-2559`).
- Version: `("optiq", "--version")` (`runtimes.py:2561`), parsed by `Optiq.parse_version` (`:2680`).
- No absolute path constant.

**Reuse for the detector:** `shutil.which("optiq")`, report the resolved real path (after symlinks) in
`EngineStatus.path`, and read the version with the same command.

### 3.6 Risks beyond the install

- **No daemon, no login item, no auto-update documented.** The install page documents pip/venv only
  (CLAIMED); this is a statement about the documented surface, not a proof that no other route exists.
- **`optiq lab` runs a local web server and `optiq cloud login` writes credentials** under `~/.optiq`
  (CLAIMED — install page). Neither is part of the harness's use of the package, but both are surfaces
  the app could accidentally advertise.
- **Interpreter indirection:** venv `python3` → `python` → uv-managed CPython 3.12.13; a `uv python`
  upgrade can move the interpreter out from under the venv (`docs/runtimes/optiq.md` §1.2, VERIFIED).
- **Port 8080 is also vMLX's app-gateway default** — see §6.4.

---

## 4. mlx-lm

The measurement control: a Python package that provides `mlx_lm.server` (README, CLAIMED). No app bundle
is part of its documented install, and none is installed for it on this machine (VERIFIED — the only
`/Applications` entries matching `mlx` are `oMLX.app` and `vMLX.app`, and `~/Applications` is empty).

### 4.1 Install route

**Command:**

```sh
pip install mlx-lm
```

(CLAIMED — README; the PyPI page repeats it. `conda install -c conda-forge mlx-lm` is the documented
alternative.) Current PyPI version is **0.32.2**, wheel 0.5 MB (VERIFIED, PyPI JSON API: `requires_python
>=3.11`, deps `mlx`, `numpy`, `transformers`, `sentencepiece`, `protobuf`, `pyyaml`, `jinja2`).

This machine does not use a global install: the harness keeps its own venv at
`~/.local/share/ohyesmlx/mlx-lm-0.31.3` (VERIFIED; `bin/mlx_lm.server` exists, `python --version` →
3.14.7).

### 4.2 Size on disk

- Download: **0.5 MB** wheel (0.32.2; VERIFIED).
- Installed env: **434 MB** (`du -sh ~/.local/share/ohyesmlx/mlx-lm-0.31.3`; VERIFIED). Top packages:
  mlx 203 MB, transformers 116 MB, numpy 34 MB, pip 13 MB, tokenizers 9.5 MB.
- Models: shared Hugging Face cache only; no private store (VERIFIED — the harness passes an artifact
  directory).

### 4.3 Prerequisites

- **Python ≥ 3.11** — `requires_python` on PyPI (VERIFIED). The harness venv runs 3.14.7 (VERIFIED), so
  the current release range is not limited to 3.11–3.13.
- **Apple Silicon** — MLX is an Apple framework (README, CLAIMED).
- **macOS 15.0+** only for the "large models" wired-memory optimisation (README note, CLAIMED). It runs
  on this macOS 27.2 machine (VERIFIED).
- **Xcode CLT / Homebrew** — not required by the package; the mesh/`mx.distributed` paths may need more,
  which is out of scope here.
- **Admin password** — none for a venv; a system-wide pip might need one, but nothing documents that as
  the route.

### 4.4 Detecting "installed", and reading the version, without launching anything

There is no app and no stable global location; detection means "a Python that can import `mlx_lm`, and
which one".

- **Console scripts:** the package installs `mlx_lm`, `mlx_lm.server`, `mlx_lm.generate`,
  `mlx_lm.convert`, … (VERIFIED, `bin/` listing in the harness venv). `mlx_lm.server` is the one the
  harness starts.
- **On this machine:** `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin/mlx_lm.server` (VERIFIED) and
  `.../lib/python3.14/site-packages/mlx_lm/_version.py` containing `__version__ = "0.31.3"` (VERIFIED).
- **Version:** `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin/python -m mlx_lm --version` → `0.31.3`
  (VERIFIED). It imports the package, so it is a command rather than a pure file read; the file read
  above is the pure one.

### 4.5 What the harness has today (`ohyesmlx/runtimes.py`)

- Registry: `RUNTIMES["mlxlm"]`, port **8081** (`runtimes.py:3391-3398`).
- Start: `("python", "-m", "mlx_lm.server", "--model", <artifact>, "--port", "8081", ...)` — a bare
  `python`, no path (`runtimes.py:2008-2017`).
- Version: `("python", "-m", "mlx_lm", "--version")` (`runtimes.py:2050`).
- **`runtimes.py` carries no mlx-lm location at all.** The venv convention lives only in
  `scripts/run_multiturn.sh:21` (`export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"`) and
  in `docs/runtimes/mlx-lm.md:12-13`. This is the one real detection gap: `EngineStatus.path` has no
  source for mlx-lm unless Phase 2 decides that the harness venv convention is the answer, or that the
  detector asks the PATH. A second copy of the venv path in `engines.py` would be exactly the drift
  `AGENTS.md` forbids.

**Reuse for the detector:** ask the same `python -m mlx_lm --version` the runtime uses, with the
interpreter resolved from the harness convention — and put that convention in one place in
`runtimes.py` rather than a second copy in `engines.py`. Bare `python` is not safe: on this machine it is
a mise shim that errors out with no pinned version (VERIFIED, §6.2).

### 4.6 Risks beyond the install

- **No app, and no daemon documented.** The package's documented install is a Python environment, not a
  service (CLAIMED — README); no app bundle exists for it here (§4 intro, VERIFIED). Absence of a
  launch agent is a reading of what is installed, not a proof about every install, so it is not claimed.
  Installing it changes a Python environment and the Hugging Face cache.
- **The shared HF cache is large and shared** — 177 GB here, also used by OptiQ (VERIFIED). Deleting
  "mlx-lm's models" and "OptiQ's models" is the same operation.
- **Wrong-interpreter hazard** — `python -m mlx_lm` from the wrong environment reports a different
  version or nothing (VERIFIED via the mise shim failing).

---

## 5. vMLX

Two products share one engine: the **vMLX.app** desktop bundle (what the harness starts) and the
**PyPI package** `vmlx` (the same server without the app). The app is branded "MLX Studio" in the
README but the DMG installs **vMLX.app** (`jjang-ai/mlxstudio` releases and `jjang-ai/vmlx` releases
publish the same `vMLX-<version>-{sequoia,tahoe}-arm64.dmg` assets — VERIFIED from both release APIs).

### 5.1 Install route

**GUI app (guided download) — the route D2 names.**

- `https://github.com/jjang-ai/vmlx/releases/latest` (the app's README points desktop users at
  `https://github.com/jjang-ai/mlxstudio/releases/latest`; both publish the same assets — VERIFIED).
- Two builds per release: `vMLX-1.6.82-sequoia-arm64.dmg` **579.0 MB** and
  `vMLX-1.6.82-tahoe-arm64.dmg` **604.5 MB** (VERIFIED, release API). No fixed asset URL exists, so
  `source_url` is the releases page and the app must choose by macOS version.

**Command (alternative, not the planned kind).**

```sh
brew install uv
uv tool install vmlx
```

or `pipx install vmlx`, or a venv with `pip install vmlx` (CLAIMED — README quickstart). PyPI version
**1.6.82**, wheel 3.5 MB, `requires_python >=3.11,<3.15` (VERIFIED, PyPI JSON API).

### 5.2 Size on disk

- Download: **579.0 MB** (Sequoia) / **604.5 MB** (Tahoe) for 1.6.82 (VERIFIED).
- Installed app: **2.0 GB** (`du -sh /Applications/vMLX.app`; VERIFIED). Resources 1.7 GB (bundled
  Python + engine source), Frameworks 286 MB (Electron), MacOS 52 KB, signature 11 MB.
- The vendor says ~500 MB for the app (CLAIMED — MLX Studio README). Measured is 2.0 GB; the two numbers
  are not comparable without knowing whether the vendor is counting the DMG or the expanded bundle.
- Python-package install size: **UNKNOWN** — the wheel is 3.5 MB, but it pulls `mlx`, `mlx-lm`,
  `mlx-vlm`, `transformers`, `dflash`, `tokenizers` and more (PyPI metadata, VERIFIED), and it is not
  installed that way on this machine.
- After first launch: `~/Library/Application Support/vMLX` is 18 MB (settings in SQLite, CLAIMED
  settings location from `docs/runtimes/vmlx.md` §3.2). `~/.cache/vmlx-engine/block-cache` is **22 GB**
  here (VERIFIED, `du`) — the engine's block-disk cache, written during use.

### 5.3 Prerequisites

- **App:** Apple Silicon. The installed 1.6.59 build is the **Tahoe** build and declares
  `LSMinimumSystemVersion = 26.0.0` (VERIFIED, `Info.plist`). The Sequoia build is the macOS 15
  alternative (asset name, VERIFIED); its exact minimum is **not measured**. The MLX Studio README's
  "macOS 14.0 Sonoma or later" (CLAIMED) conflicts with the 26.0.0 plist and is not resolved here.
- **Bundled Python 3.12.12** — the app needs no system Python (VERIFIED by running the bundled
  interpreter).
- **PyPI route:** Python ≥ 3.11 and < 3.15 (VERIFIED), macOS 14+ (CLAIMED), and `uv`/`pipx`/a venv
  because bare `pip install` is refused as externally-managed on macOS 14+ (CLAIMED — README note).
- **Xcode CLT / Homebrew** — none for the DMG (bundled). Homebrew only to get `uv`/`pipx` for the pip
  route.
- **Admin password** — none for drag-install; the app is signed by "Developer ID Application:
  ShieldStack LLC" (VERIFIED, `codesign`), but see the Gatekeeper finding in §5.6.

### 5.4 Detecting "installed", and reading the version, without launching anything

- **App bundle:** `/Applications/vMLX.app` (VERIFIED; `CFBundleIdentifier` `net.vmlx.app`,
  `CFBundleName` `vMLX`).
- **CLI wrapper:** `~/.local/bin/vmlx` — a real 265-byte file (not a symlink) that `exec`s
  `/Applications/vMLX.app/Contents/Resources/bundled-python/python/bin/vmlx` (VERIFIED, contents). The
  bundle's console script resolves `python3` relative to `$0`, which is why a symlink into
  `~/.local/bin` would break it (`docs/runtimes/vmlx.md` §1.1, VERIFIED).
- **Engine source in the bundle:**
  `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/__init__.py` (VERIFIED; it
  is `VMLX_ENGINE_INIT` in `runtimes.py:380-383`).
- **Version:** `sed -n 's/^__version__ = "\([^"]*\)".*$/\1/p' <that file>` → `1.6.59` (VERIFIED — the
  same probe the harness runs). **`vmlx --version` is not a flag:** it exits **2** with
  `unrecognized arguments: --version` (VERIFIED); the error text does print `vmlx_engine version is
  1.6.59`, but a detector must not parse an error. There is no version subcommand
  (`docs/runtimes/vmlx.md` §9.4; `runtimes.py:2893-2898`).

### 5.5 What the harness has today (`ohyesmlx/runtimes.py`)

- Registry: `RUNTIMES["vmlx"]`, port **8000** (`runtimes.py:3391-3398`).
- Start: `("vmlx", "serve", <artifact>, "--host", "127.0.0.1", "--port", "8000", ...)`
  (`runtimes.py:2814-2858`, which includes `--disable-block-disk-cache` at `:2846`). For an MTP-depth
  cell the tuple is prefixed with
  `("env", "VMLX_NATIVE_MTP_AR_SAFETY=0", ...)` (`runtimes.py:2809`), so `start_command()[0]` is not
  always the executable — a detector must not take element 0 blindly.
- Version: `("sed", "-n", VMLX_VERSION_SED, VMLX_ENGINE_INIT)` (`runtimes.py:2893-2898`).
- Absolute constants: `VMLX_ENGINE_INIT` (`:380-383`); the app-bundle path is in that constant, the
  wrapper is not.

**Reuse for the detector:** bundle presence + `~/.local/bin/vmlx`, and the existing `VMLX_ENGINE_INIT` /
`VMLX_VERSION_SED` pair for version. Do not add a second repository of those strings.

### 5.6 Risks beyond the install

- **Gatekeeper fails on the installed bundle here.** `spctl -a -vv /Applications/vMLX.app` →
  `a sealed resource is missing or invalid` (VERIFIED). The signature itself is valid
  ("Developer ID Application: ShieldStack LLC", `codesign` VERIFIED), and the app has been in use since
  2026-09-15, so the likely cause is something added or removed inside the bundle after signing — the
  cause was **not** investigated. Do not describe this install as Gatekeeper-clean.
- **API gateway port 8080 by default.** The desktop app runs an API gateway on port 8080 (CLAIMED —
  vMLX README, "default 8080"). The harness starts OptiQ on **8080** too (`runtimes.py:3395`), so a
  running vMLX app can collide with an OptiQ cell. The onboarding app must not assume ports are free.
- **`vmlx serve` from PyPI defaults to `0.0.0.0:8000`** (CLAIMED — README quickstart), i.e. network
  exposure unless `--host 127.0.0.1` is passed. The harness always passes it
  (`runtimes.py:2821-2824`); a plan that tells a user to run `vmlx serve` by hand does not.
- **Block-disk cache turns itself on.** When continuous batching and prefix caching are both active, the
  engine enables the SSD block cache without a flag, writing to `~/.cache/vmlx-engine/block-cache`
  (`runtimes.py:2774-2780`, citing `cli.py:661-701`). Measured **22 GB** here (VERIFIED). It survives
  restarts and is not the run's scratch. The harness passes `--disable-block-disk-cache`
  (`runtimes.py:2846`) precisely because a cache hit would publish as prefill throughput; a user who
  starts `vmlx serve` by hand gets the cache.
- **Electron app, menu bar, bundled toolchain.** 286 MB of Frameworks and 144 console scripts in
  `bundled-python/python/bin` (`docs/runtimes/vmlx.md` §1.3, VERIFIED). The app is a full desktop
  product, not a launcher.
- **Updater.** Release notes mention an "updater manifest" (`vMLX 1.6.81 updater manifest`, VERIFIED
  from the release body), so an update mechanism exists (INFERRED); no Sparkle keys are present
  (`Info.plist`, VERIFIED absent).

---

## 6. Cross-engine: what Phase 2 must decide, and what it must not copy

### 6.1 One naming conflict, and it is in the pinned shapes

`docs/interfaces.md:1375` enumerates `EngineStatus.name` as `"osaurus|omlx|optiq|mlx-lm|vmlx"`, and the
same section says names come from `runtimes.py`. `runtimes.py:3392` keys the control as **`"mlxlm"`**,
not `"mlx-lm"`. The detector cannot satisfy both strings; whichever is chosen, one pinned document must
change.

There is a second, related trap in the same place: `RUNTIMES` has **six** entries including `mtplx`
(`runtimes.py:3391-3398`), while the pinned `EngineStatus.name` enum and this order name **five** (D2
keeps MTPLX out until its branch lands; PLAN T2.1 meanwhile says "six engines"). A detector that
iterates `RUNTIMES` will emit an engine the shape does not name. Both are findings for T2.1, not
something this research resolves.

### 6.2 PATH is not evidence of absence

Four engines are found by a bare name in `start_command` (`osaurus`, `omlx`, `optiq`, `vmlx`) and those
names live in directories a fresh Mac does not put on `PATH` by default (`~/.omlx/bin`, `~/.local/bin`).
On this machine all four resolve only because the shell PATH was extended (VERIFIED). A detector that
only calls `shutil.which` can report "not installed" for an engine that is installed.
Conversely, `/opt/homebrew/bin/osaurus` exists here while the cask is not installed — a stale link that
`which` would happily report. `EngineStatus.path` should therefore be the resolved **real** path, and
detection should check the known absolute candidates as well as PATH.

### 6.3 Version drift: what a plan installs is not what the harness pins

| Engine | Installed here | Latest on 2026-10-29 | Source |
|---|---|---|---|
| Osaurus | 0.25.28 | 0.25.28 | GitHub release API |
| oMLX | 0.7.2 | 0.7.3rc1 | GitHub release API |
| OptiQ | 0.5.13 | 0.7.8 | PyPI JSON |
| mlx-lm | 0.31.3 | 0.32.2 | PyPI JSON |
| vMLX (app) | 1.6.59 | 1.6.82 | GitHub release API |

Every one of these is VERIFIED. The harness's start commands and refusals are written against the
**installed** versions (citations name `mlx-lm 0.31.3`, `optiq/cli.py` at 0.5.13, `vmlx` 1.6.59). An
onboarding install takes the latest, so a user can end up on a build whose flag surface the harness has
never read. `Plan.size_bytes_estimate` is also a moving target: it must be the download size at plan
time, and the doc's per-engine numbers are dated for that reason.

### 6.4 Ports, and the one-model-resident rule

Harness ports (`runtimes.py:3391-3398`): Osaurus 1337, mlx-lm 8081, oMLX 8100, OptiQ 8080, vMLX 8000.
Engine defaults diverge for oMLX (8000) and for the vMLX **app gateway** (8080, colliding with OptiQ).
AGENTS.md's rule that exactly one model is resident at a time applies to the onboarding app as much as
to the grid: an app-managed server left running is both a port hazard and a memory contaminant.

### 6.5 The install is small; the use is huge

Measured on this machine (VERIFIED, `du`): Osaurus app 208 MB **vs** 83 GB `~/.osaurus/cache/kv_v2`;
oMLX app 1.7 GB **vs** 69 GB `~/.omlx/cache`; vMLX app 2.0 GB **vs** 22 GB block cache; 177 GB Hugging
Face cache shared by mlx-lm and OptiQ; 128 GB in `~/MLXModels`. `Plan.size_bytes_estimate` can only
mean the download, and the UI must not let "install" imply the whole disk cost.

### 6.6 Admin and Gatekeeper

No route documented here needs `sudo` for an admin user: the DMGs are drag-install, the Python packages
go into user-space environments, no `pkgutil` receipts exist for any engine, and `spctl` accepts Osaurus
and oMLX as notarized. vMLX's installed bundle currently fails assessment (§5.6). Homebrew itself is the
only step in any documented route that needs an admin password, and only if the user chooses the cask,
tap or `brew install uv` route.

### 6.7 What I could not determine

1. **Clean-install disk size for OptiQ** (vendor says ~80 MB; the only measured environment is 846 MB
   and contains undeclared extras). Same for the **PyPI install of vMLX**.
2. **The Sequoia build's exact minimum macOS for vMLX** — only the Tahoe build is installed, and its
   plist says 26.0.0; the vendor's app README says 14.0.
3. **Whether `osaurus doctor` starts or merely probes a server.** It is documented as diagnosing "server
   startup", so the detector was specified around the plist instead of running it.
4. **Whether oMLX's "latest" being a release candidate is intended**, and whether the guided download
   should pin a stable tag instead.
5. **Whether vMLX.app updates automatically**, and **why its Gatekeeper assessment fails here**.
6. **Whether any engine has an install route beyond its documented one.** The install pages and release
   assets were read; no exhaustive search for unofficial routes was made. No negative claim here should
   be read as more than "the vendor documents only this".

---

## 7. Reproduction

Commands run for the VERIFIED claims above (all read-only; no server, no install):

```sh
sw_vers
du -sh /Applications/osaurus.app /Applications/oMLX.app /Applications/vMLX.app
du -sh ~/.local/share/ohyesmlx/mlx-lm-0.31.3 /Users/jrazz/Dev/tools/mlx-optiq/.venv
du -sh ~/.osaurus ~/.omlx ~/.cache/vmlx-engine ~/.cache/huggingface ~/MLXModels
ls -l ~/.local/bin/{osaurus,optiq,vmlx} /opt/homebrew/bin/{osaurus,omlx} ~/.omlx/bin/omlx
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' <app>/Contents/Info.plist
omlx --version                       # 0.7.2
optiq --version                      # mlx-optiq, version 0.5.13
~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin/python -m mlx_lm --version   # 0.31.3
sed -n 's/^__version__ = "\([^"]*\)".*$/\1/p' \
  /Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/__init__.py  # 1.6.59
vmlx --version                       # exits 2
codesign -dv --verbose=2 <app>; spctl -a -vv <app>
sfltool dumpbtm | grep -A10 'Name: Osaurus'
brew info --cask osaurus
curl -s https://api.github.com/repos/{osaurus-ai/osaurus,jundot/omlx,jjang-ai/vmlx}/releases/latest
curl -s https://pypi.org/pypi/{mlx-lm,mlx-optiq,vmlx}/json
```

Sources read: `github.com/osaurus-ai/osaurus` (README), `docs.osaurus.ai/installation`,
`github.com/jundot/omlx` (README), `github.com/ml-explore/mlx-lm` (README), `github.com/jjang-ai/vmlx`
(README + latest release), `github.com/jjang-ai/mlxstudio` (README), `mlx-optiq.com/docs/install`,
`pypi.org/project/{mlx-lm,mlx-optiq}`, plus this repo's `docs/runtimes/*.md`, `docs/interfaces.md` and
`ohyesmlx/runtimes.py`.

---

## Table: what `engines.install_plan` needs

`kind` follows Decision D2. `size` is the **download** a fresh user fetches; installed/after-use figures
are above. `needs_admin` is for the documented route on an admin account (§6.6). `detect` names the
files to test, not a copy of `runtimes.py`'s internals; the harness-side source for each engine's name,
port and start command is `runtimes.py:3391-3398` and the per-class `start_command`.

| engine | kind | source | size | needs_admin | detect | version probe |
|---|---|---|---|---|---|---|
| **Osaurus** | `guided_download` | `https://github.com/osaurus-ai/osaurus/releases/latest` (`Osaurus.dmg`); cask `brew install --cask osaurus` | 85.9 MB (standard DMG; full ~3.6 GB, model bundled) | no | `/Applications/osaurus.app` **or** `/Applications/Osaurus.app`; CLI `~/.local/bin/osaurus` or `/opt/homebrew/bin/osaurus` → `Contents/Helpers/osaurus` | `/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' <app>/Contents/Info.plist` → `0.25.28`; `osaurus --version` is claimed by the docs but was not run (flags can act) |
| **oMLX** | `guided_download` | `https://github.com/jundot/omlx/releases` — asset chosen by macOS: `oMLX-<ver>-macos15-sequoia.dmg` or `-macos26-27.dmg` | 837.8 MB (0.7.2, macOS 15) / 875.2 MB (macOS 26-27) | no | `/Applications/oMLX.app`; `~/.omlx/bin/omlx` (shim, hardcodes the bundle) | `omlx --version` → `0.7.2`; or `CFBundleShortVersionString` (`0.7.2`) |
| **OptiQ** | `command` | `pip install mlx-optiq` — `https://pypi.org/project/mlx-optiq/` | 1.8 MB wheel (0.7.8); clean install size **UNKNOWN** (vendor claims ~80 MB; measured env 846 MB includes extras) | no (venv / `uv` / `pipx`) | `shutil.which("optiq")` (here `~/.local/bin/optiq` → `.venv/bin/optiq`); `mlx_optiq-*.dist-info/METADATA` | `optiq --version` → `mlx-optiq, version 0.5.13` (harness strips the prefix) |
| **mlx-lm** | `command` | `pip install mlx-lm` — `https://pypi.org/project/mlx-lm/` | 0.5 MB wheel (0.32.2); 434 MB installed env here | no (venv) | a Python whose `bin/mlx_lm.server` exists — here `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin/mlx_lm.server` (no path in `runtimes.py`; convention is `scripts/run_multiturn.sh:21`) | `<that python> -m mlx_lm --version` → `0.31.3`; file-only: `site-packages/mlx_lm/_version.py` |
| **vMLX** | `guided_download` | `https://github.com/jjang-ai/vmlx/releases/latest` (same DMGs as `jjang-ai/mlxstudio`): `vMLX-<ver>-sequoia-arm64.dmg` / `-tahoe-arm64.dmg`; command alternative `uv tool install vmlx` | 579.0 MB (Sequoia) / 604.5 MB (Tahoe) for 1.6.82; PyPI wheel 3.5 MB, env size **UNKNOWN** | no | `/Applications/vMLX.app`; `~/.local/bin/vmlx` (real wrapper → bundle's `bundled-python/.../vmlx`) | `sed -n 's/^__version__ = "\([^"]*\)".*$/\1/p' /Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/__init__.py` → `1.6.59`; **`vmlx --version` exits 2** |

---

## 8. Smoke test of the pinned pip plans (2026-10-29, closes §6.7 item 1 for mlx-lm and OptiQ)

The two `command` plans from `engines.install_plan` were run verbatim (venv created by Python 3.14.7, then `pip install --no-input --disable-pip-version-check <pkg>==<tested>`) into a scratch directory, then deleted. Nothing outside the scratch directory was touched. VERIFIED:

| engine | pinned install | wall time | clean venv size on disk | `--version` |
|---|---|---|---|---|
| mlx-lm | `mlx-lm==0.31.3` | 177 s | 472 MB | `0.31.3` |
| OptiQ | `mlx-optiq==0.5.13` | 104 s | 612 MB | `mlx-optiq, version 0.5.13` |

`detect_all` found both in the app-managed venv path with the right versions and `tested: true` (OptiQ's version read from `dist-info/METADATA`, not `__init__`). The 612 MB figure replaces the vendor's "~80 MB" for a clean OptiQ install. Also observed the same day: vMLX self-updated from 1.6.59 to 1.6.82 on this host and now reads `tested: false`.
