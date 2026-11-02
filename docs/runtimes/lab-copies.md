# Lab copies — freezing each engine at its tested build

Written 2026-10-29 for v5.0 Phase 2.5 (Decision 135), plan
`.paul/phases/v5-onboarding/025-03-PLAN.md`. Scope: the five engines of Decision D2 — **Osaurus,
oMLX, OptiQ, mlx-lm, vMLX**. MTPLX is out of v5.0 and is not covered.

**Why this document exists.** Every published number in this repo belongs to one build. The
engines upgrade under us: on 2026-10-29 OptiQ and vMLX both moved to newer builds (vMLX to
1.6.82) without anyone choosing it
(`docs/research/2026-10-29-engine-install-paths.md` §6.3 and §8; `.paul/STATE.md` Decision 135).
A table measured across two builds is not a result, so the tested build has to stay available
after the daily-driver install has moved on, and a bump has to be *decided* rather than noticed.
This document is that procedure: where each frozen build lives, how to put it back, how the
harness finds it, and the ordered checklist for recording a bump.

**This document does not restate a version.** The one tested-versions table is
`ohyesmlx/engines-tested.json` (Decision 135, plan 025-01). Every claim below about "the tested
version" points at a key in that file rather than copying its value, because a second copy of a
version is a second place for it to go stale. Read it with:

```sh
jq -r 'to_entries[] | "\(.key)\t\(.value.version)\t\(.value.verified)"' ohyesmlx/engines-tested.json
```

**Evidence labels.** **VERIFIED** — read from a shipped file, a shipped binary's string table, or
measured on this machine, with the command or path given. **CLAIMED** — vendor documentation
only. **INFERRED** — follows from something VERIFIED but is not itself observed. **UNKNOWN** —
not established, and the probe that would settle it is named. A string-table reading proves a
literal exists in a shipped binary; it cannot prove control flow, and the difference is marked
wherever it matters (`docs/runtimes/osaurus.md` §0 makes the same distinction). **No engine in
this document is claimed to be unable to disable updates**: where the lever is not established,
the row says UNKNOWN and names the probe.

**Status of the harness side.** The machine-local reader this document describes
(`engines.lab_paths`, `engines.LAB_PATHS_FILE`, `engines.LAB_ENGINES`), the merge in
`runtimes._engine_env` and the detection preference in `engines.detect_all` are implemented in the
working tree as this is written (plan 025-03's second task); `docs/interfaces.md`'s v5.0 note is
the pinned shape. `scripts/lab-copies-wizard.sh` (the interactive steps only Jason can take) is the
same plan's checkpoint and is generated from this document — this document is its source, not its
summary. Nothing else here is enforced by code. A procedure a human performs is a procedure that
can be performed wrongly, which is why §8 ends in a committed record.

---

## 1. Two policies, and the one reason they differ

| Engine | Kind | Frozen as | Today |
|---|---|---|---|
| mlx-lm | Python package | a version-pinned venv, selected by a machine-local path | the harness already runs its own pinned venv |
| OptiQ | Python package | the same | the global install has drifted; the lab venv is the way back |
| Osaurus | macOS app bundle | an archived installer (DMG) plus automatic checks off | archive; never a second `.app` (§5.1) |
| oMLX | macOS app bundle | the same | archive |
| vMLX | macOS app bundle | the same | archive |

The difference is not taste. A Python package is a directory of files plus a console script whose
shebang names the interpreter beside it (`docs/runtimes/optiq.md` §1.1, VERIFIED from the
installed script) — so a venv is a complete, self-contained, selectable copy, and pointing a name
at it is one PATH entry. A macOS application is not: it is launched by identity, not by path
(§5.1), and a second copy with the same bundle identifier is not an isolated lab — it is a second
claimant to the same preferences, the same background-task entry and the same on-disk state. For
those, the reproducible artifact is the installer you can go back to.

Both policies answer the same question: *can this Mac still produce the build every table names,
after the daily-driver install has moved?* The canary (§8) answers the follow-up: *did the move
change the numbers?*

---

## 2. One version table, and how everything asks it

`ohyesmlx/engines-tested.json` is the only place a tested version is written. `engines.load_manifest`
reads and validates it (one entry per engine in `engines.ONBOARDING_ENGINES`, unknown keys
refused), `engines.MANIFEST` is the loaded file, and `engines.TESTED_VERSIONS` is the flat
`{engine: version}` view that the rest of the code asks. Each entry is:

```json
{ "version": "<tested build>", "verified": "<ISO date>", "lab_path": null,
  "canary": { "format": "...", "repo": "...", "workload": "decode",
              "decode_tok_s": 0.0, "ttft_s": 0.0,
              "measured": "<ISO date>", "version_measured": "<build the baseline came from>" } }
```

Three consequences worth stating because they are the mechanism, not the ceremony:

- **`lab_path` ships `null` on every entry, and that is deliberate.** A lab path is
  machine-specific; committing Jason's venv path would point every other Mac at a directory that
  does not exist there, and the refusal in §3 would then stop every start on every other Mac.
- **`tested` is a comparison, not a claim.** `engines.detect_all` sets
  `tested = version == TESTED_VERSIONS[name]`, so an engine that upgraded itself reports
  `tested: false` rather than being assumed equivalent. That flag is the tripwire: on 2026-10-29
  OptiQ and vMLX both read `tested: false` while the harness is written against the older builds
  (research §8, VERIFIED).
- **A row names the build it ran on.** Measured rows carry `runtime_version`, and a join across
  builds is refused — rows from different builds never share a table (§8, step 10).

The canary's baseline lives in the same entry (`canary.decode_tok_s`, `canary.ttft_s`) and records
the build it was measured on (`version_measured`). That field is what makes the canary a
build-to-build comparison rather than a session-to-session one, and `ohyesmlx canary --record`
writes it — and only it — while the tested `version` and `verified` stay a deliberate edit
(`ohyesmlx/canary.py`, `record()`'s docstring).

---

## 3. Where a lab copy lives, and who reads it

**The machine-local file.** `~/Library/Application Support/OhYesMLX/lab-paths.json`, shape
`{"<engine>": "<absolute or ~ bin directory>"}`. One function reads it — `engines.lab_paths(path=
LAB_PATHS_FILE)` — and one function derives its location, `engines._lab_paths_file(home)`. Missing
file means `{}` (no lab copies is the ordinary state of a machine that has not frozen anything).
Invalid JSON, a key that is not an onboarding engine, a non-string or empty value, and a key for
an app engine all raise `ValueError` naming the file and the entry: the alternatives are worse
than stopping, because an unknown key is a path nobody would read and a half-understood file
would measure a global install under a pinned version's label.

**Only two engines may name a lab path.** `engines.LAB_ENGINES = ("mlxlm", "optiq")`. An app
engine key is refused with "app engines are archived, not run from a lab path" — which is the
code-level statement of §5's policy, not a limitation to work around.

**Priority.** `runtimes._engine_env` takes the machine-local entry when there is one and the
manifest's `lab_path` otherwise:

```python
lab_path = local.get(name, entry["lab_path"])
```

so the committed manifest's `null` leaves the local file in charge, and a machine that commits its
own path still works. That function is **the one place a lab path becomes something a process
sees**: it prefixes each lab directory to `PATH` for `_spawn` and `_run`, and those are its only
two callers. Because five of the six start commands begin with a bare name (`mlx_lm.server`,
`optiq`, `vmlx`, `osaurus`, `omlx`), the prefix decides which copy the server, the version probe
and the stop command all reach — they cannot disagree, because they share one environment.

**A path that is not there is refused at start**, naming the engine, rather than skipped.
Falling back to the global install would measure a build nothing vouched for and record it under
the pinned version. Detection is the exception by design: `engines.detect_all` reports what it
finds at the named path and leaves the refusal to the start path.

**Detection looks in the lab copy first.** For `LAB_ENGINES` only, `detect_all` hands the lab path
to the detector, which reads the version from *that* venv rather than from the global install.
This is what makes a canary of a frozen build record the frozen build's version: the canary's row
takes its version from `detect_all`, so a lab copy that answered with the global install's version
would write the wrong number against the wrong build.

**The file is never the committed manifest.** The wizard writes `lab-paths.json` and prints it; it
never edits `engines-tested.json`. A lab path is a property of this Mac; a tested version is a
property of the project.

---

## 4. The pip engines: a version-pinned venv

Both pip engines install the same way, and the installer pins both the package and its dependency
set:

```sh
{python} -m venv ~/Library/Application\ Support/OhYesMLX/engines/<name>-<version>
~/Library/Application\ Support/OhYesMLX/engines/<name>-<version>/bin/python -m pip install \
    --no-input --disable-pip-version-check <distribution>==<manifest version> \
    -c ohyesmlx/constraints/<name>-<manifest version>.txt
```

(`engines._command_plan`, VERIFIED in the tree; `<python>` must be 3.11 or later — stock
`/usr/bin/python3` is 3.9.6 on this macOS, research §3.3 VERIFIED.) The two steps are the
installer's own `Plan`, and the install step applies the committed constraints file, so the
harness's "install" and this document's "freeze" are the same operation. The clean-install sizes
were measured by running exactly these commands on 2026-10-29 (research §8, VERIFIED): mlx-lm 472 MB
and OptiQ 612 MB per venv, with wall times of 177 s and 104 s. The older figures in research §3.2
and §4.2 (846 MB, 434 MB) came from environments that were not clean and are superseded by §8 for
planning disk.

**The constraints file is the other half of the pin.** A package pin alone does not pin the build:
the two lab venvs had already drifted apart at the same engine versions (mlx 0.32.4 vs 0.32.2,
transformers 5.12.1 vs 5.17.0), and `pip install mlx-optiq==<version>` leaves `mlx-lm` unpinned, so
pip resolved a server whose chat endpoint answered HTTP 404 (2026-10-30,
`docs/research/2026-10-30-optiq-0513-vs-078-canary.md`). `engines.constraints_path` is the one
definition of the file's name, one per pip engine per tested version:
`ohyesmlx/constraints/<name>-<TESTED_VERSIONS[name]>.txt`. `engines.install_plan` refuses with
`ValueError` naming that path when it is missing, so a version bump without a new freeze fails
before a venv is created.

**Freezing a venv into its constraints file.** The header is the three comment lines both committed
files carry — engine-version, venv root, interpreter — and the body is the venv's whole freeze:

```sh
{
  printf '# pip constraints for the <name>-<version> lab copy: its full dependency set, frozen <ISO date> (T2.5.5).\n'
  printf '# Venv: <venv root>\n'
  printf '# Interpreter: Python <X.Y.Z> (<arch>)\n'
  <venv>/bin/python -m pip freeze --all
} > ohyesmlx/constraints/<name>-<version>.txt
```

`--all` is not optional: without it `pip freeze` omits the toolchain (`pip` itself), and the freeze
would describe a different environment from the one that runs the server. Freeze the venv that was
just installed from the manifest's version, and commit the file in the same commit as the version it
names.

The venv root names are the ones `engines._app_engine_venvs` derives — `engines/<name>-<version>`
with a bare `engines/<name>` as the second candidate — so detection, install and this document
share one convention instead of three.

### 4.1 mlx-lm (`mlxlm`)

- **Tested version.** `engines-tested.json` → `mlxlm.version`.
- **How the tested build is obtained.** PyPI, pinned:
  `pip install mlx-lm==<version>` (source `https://pypi.org/project/mlx-lm/`). VERIFIED that the
  pinned form installs and reports the pinned version (research §8).
- **Lab copy.** The venv itself; `lab-paths.json` entry
  `{"mlxlm": "<Application Support>/OhYesMLX/engines/mlxlm-<version>/bin"}`. The harness's older
  convention — the versioned venv under `~/.local/share/ohyesmlx/` that
  `scripts/run_canary.sh` and `scripts/run_multiturn.sh` export — is a fallback, not a second
  authority: `_engine_env` *prefixes* the lab path, so the file wins over the runner's `export`.
- **How the version is read.** `engines._detect_mlxlm` finds `bin/mlx_lm.server` and reads
  `_version.py` from the same venv through `_venv_package_version`; the harness's own run-probe
  stays `python -m mlx_lm --version` (`docs/runtimes/mlx-lm.md` §1). Both are the same build as
  long as the lab path is what resolves.
- **Auto-update.** None to turn off: the package is not a service, and `pip install` is the only
  documented route (CLAIMED — README and PyPI page, research §4.1). The drift sources are a human
  running pip and an interpreter upgrade underneath the venv; neither is automatic.
- **What a lab copy does not protect against.** A shared Hugging Face cache (research §4.6) and a
  bare `python` on `PATH` that is a mise shim (research §6.2). The start command uses a bare
  `python`, so the lab venv's `bin` must be the first `python` the spawn sees — which is exactly
  what the PATH prefix does.

### 4.2 OptiQ (`optiq`)

- **Tested version.** `engines-tested.json` → `optiq.version`.
- **How the tested build is obtained.** PyPI, pinned: `pip install mlx-optiq==<version>` (source
  `https://pypi.org/project/mlx-optiq/`). VERIFIED (research §8).
- **Lab copy.** The venv; `lab-paths.json` entry `{"optiq": "<venv>/bin"}`. The interpreter chain
  is uv-managed (optiq.md §1.2), so moving or upgrading that CPython out from under the venv breaks
  it — freeze the interpreter with the package.
- **How the version is read.** `engines._detect_optiq` prefers `dist-info/METADATA` and, **for a
  venv named `.venv` only**, reads `pyproject.toml` beside it because that name is taken to mean an
  editable checkout (`engines._optiq_version`, whose `# ponytail:` names that ceiling). A lab venv
  must therefore **not** be named `.venv`; the app-managed `optiq-<version>` root cannot collide
  with that rule.
- **Auto-update.** None to turn off (same reasoning as mlx-lm; CLAIMED documented route).
- **What a lab copy does not isolate.** `~/.optiq/config.json` and every `OPTIQ_*` variable are
  read from the user's home, not from the venv (`docs/runtimes/optiq.md` §3.1–§3.2), so a frozen
  venv still inherits a stray settings file. Both were absent when last checked (2026-09-25,
  VERIFIED in optiq.md §3.1) and the check belongs in every run's provenance — `optiq config`
  prints every resolved value and its source, which is the recorded way to do it.

---

## 5. The app engines: archive the installer, do not parallel-install

### 5.1 Why a second `.app` is not a lab

The policy in this section is a decision, so its evidence is laid out. Every hazard below is
VERIFIED from a shipped bundle or from this repo's own code.

| Hazard | Evidence | What it means for a second copy |
|---|---|---|
| **One bundle identity** | Osaurus `com.dinoki.osaurus`, oMLX `app.omlx`, vMLX `net.vmlx.app` (`Info.plist`, research §1.4/§2.4/§5.4) | macOS resolves an app by identity, not by path. Two copies share the preferences domain, the notification identity, and LaunchServices' answer to "open this app". A lab copy that writes a preference writes it for the daily driver too. |
| **A login/background item already exists** | `sfltool dumpbtm` lists `com.dinoki.osaurus` (app, `[enabled, disallowed, notified]`), research §1.6; `LSUIElement` true (§1.4) | A second copy does not get a second entry — it shares the identity. Whichever copy launchd resolves is what starts at login, and the user has no way to tell them apart in the list. |
| **`osaurus mcp` relaunches the GUI app** | `docs/runtimes/osaurus.md` §1.2 (observed 2026-09-23) | Any MCP host that registers `osaurus mcp` relaunches `/Applications/osaurus.app/Contents/MacOS/osaurus --launched-by-cli` on session start. It resolves the *installed* app; a lab copy is neither chosen nor attributable. |
| **The harness's resident guard is path-literal** | `runtimes.OSAURUS_EXECUTABLE = /Applications/osaurus.app/Contents/MacOS/osaurus`; `_resident_osaurus_pids` compares `argv[0]` against it exactly; `scripts/run_canary.sh` sweeps `pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus"` | A lab copy at another path is **invisible to both**. It could hold ~900 MB and a port while a cell runs — the "one model resident at a time" violation that voids a run (AGENTS.md). This is the decisive argument: the harness cannot see a second Osaurus, so a second Osaurus is unsafe by construction, whatever the app itself does. |
| **Launchers hardcode `/Applications`** | `~/.omlx/bin/omlx` execs `/Applications/oMLX.app/Contents/MacOS/omlx-cli` (research §2.4, VERIFIED); `~/.local/bin/vmlx` execs `/Applications/vMLX.app/Contents/Resources/bundled-python/python/bin/vmlx` (§5.4, VERIFIED) | The CLI names the harness starts reach the installed bundle. Reaching a lab copy means rewriting those wrappers — a mutable, undocumented dependency that also changes what a recorded start command means. |
| **State lives outside the bundle and is shared** | `~/.osaurus/config` plus an 83 GB KV cache; `~/.omlx/settings.json` (one file, shared by any copy); `~/Library/Application Support/vMLX` (settings) plus a 22 GB block cache under `~/.cache/vmlx-engine` (research §1.2/§2.2/§5.2, `du`, VERIFIED) | A lab copy reads the same settings and caches, so it is not an isolated environment. The Osaurus drift gate tracks one settings file; two copies make "pinned" ambiguous. |

**Verdict.** Archive each tested DMG and return to it; do not install a parallel copy. The
residual is stated rather than hidden: none of this was tested by actually installing a second
copy, because that is outside this plan's boundaries. What *would* change the verdict is a lab
copy that is both reachable through a launcher the harness uses and visible to the resident guard
— today it is neither, and that is a code fact, not an opinion.

### 5.2 Osaurus

- **Tested version.** `engines-tested.json` → `osaurus.version`.
- **How the tested build is obtained.** A GitHub release asset, not a moving URL:
  `Osaurus-<version>.dmg` (the standard build — **not** the `~3.6 GB -full` one that bundles
  Raptor), on the release tagged for that version at
  `https://github.com/osaurus-ai/osaurus/releases`. The README's
  `releases/latest/download/Osaurus.dmg` is the *latest* build, which is precisely what must not be
  archived under a tested version's name. The cask (`brew install --cask osaurus`) installs the
  same app but is not a version-pinned artifact and installs under a different bundle spelling
  (`Osaurus.app`); prefer the tag's DMG. Sizes reported by the release API on 2026-10-29: 85.9 MB
  for the standard DMG, 208 MB installed (research §1.2, VERIFIED).
- **Lab copy.** The archive in `~/Library/Application Support/OhYesMLX/archives/osaurus-<version>/`
  (§6). Restoring means quitting the app, opening the DMG and replacing `/Applications/osaurus.app`,
  then reading the version back from the bundle's `Info.plist`. The harness starts `osaurus` from
  `PATH` and identifies the app by `/Applications`, so the restored bundle is exactly what a cell
  will use.
- **Auto-update.** The mechanism is Sparkle, and it is on:

  | Claim | Label | Evidence |
  |---|---|---|
  | Sparkle ships in the bundle; `SUFeedURL` is `https://osaurus-ai.github.io/osaurus/appcast.xml`; `SUEnableAutomaticChecks` is `true` | VERIFIED | `PlistBuddy` on `/Applications/osaurus.app/Contents/Info.plist`; `Sparkle.framework` present under `Contents/Frameworks` (2026-10-29) |
  | The app can replace itself between cells | VERIFIED (the mechanism: Sparkle + automatic checks on) + CLAIMED (vendor behaviour: it updates when opened) | `docs/runtimes/osaurus.md` §1.4, §7.6 |
  | The framework reads `SUEnableAutomaticChecks`, `SUAutomaticallyUpdate`, `SUFeedURL`, `SULastCheckTime`, `SUSkippedVersion`; it carries the standard strings "Check for updates automatically?" and "Automatically download and install updates" | VERIFIED (string table) | `strings -a …/Sparkle.framework/Versions/B/Sparkle` (2026-10-29) |
  | The app exposes an Updates settings section and an update channel; a `Check for Updates` command exists | VERIFIED (string table) | literals `settings.general.updates`, `Sparkle: update channel changed to %@`, `Check for Updates` in `Contents/MacOS/osaurus` (2026-10-29) |
  | An update dialog has been shown on this host; no automatic-check preference is stored | VERIFIED | `defaults read com.dinoki.osaurus` holds `NSWindow Frame SUUpdateAlert2` and no `SU*` key (2026-10-29) |
  | `defaults write com.dinoki.osaurus SUEnableAutomaticChecks -bool false` turns the automatic check off | INFERRED | the key literal is in Sparkle's binary and the plist sets the initial value; Sparkle stores the user's choice in the host app's defaults. **The GUI route (Settings → General → Updates, INFERRED from the identifier) may be simpler — use it if present.** |
  | Automatic *install* is not configured | INFERRED (absence of a key) | no `SUAutomaticallyUpdate` in `Info.plist`; an absent key is not proof of behaviour |
  | Whether an automatic-check toggle exists in the app's own settings | UNKNOWN | probe: open Settings → General → Updates, toggle any "automatically check" row, then `defaults read com.dinoki.osaurus \| grep -i '^ *SU'` and record the key. Confirm the effect by the absence of Sparkle's `didFindValidUpdate` / `didNotFindUpdate` log lines across two launches (`log stream --predicate 'process == "osaurus"'`) |

  **Never claim Osaurus cannot be told to stop checking.** What is established is that the check
  is on by default and one lever is available; the probe above settles the rest. Record the prior
  preference state before writing anything, so it can be restored byte-exact like the settings pin
  in `scripts/osaurus-pin.sh`.
- **Manifest field.** Nothing to set: `lab_path` stays `null`, and `engines.lab_paths` refuses an
  Osaurus entry by design (§3).
- **Hazards for a cell, beyond the version.** `osaurus stop` frees the port but leaves the app
  alive; `osaurus mcp` can relaunch it; the app's idle-residency setting unloads the model after a
  timeout unless pinned (`docs/runtimes/osaurus.md` §7.4). All three are handled by
  `scripts/run_canary.sh` and `scripts/osaurus-pin.sh`, not by this document.

### 5.3 oMLX

- **Tested version.** `engines-tested.json` → `omlx.version`.
- **How the tested build is obtained.** The release page, because there is **no stable asset URL**:
  each release publishes one DMG per macOS generation, named
  `oMLX-<version>-macos15-sequoia.dmg` or `oMLX-<version>-macos26-27.dmg`
  (`https://github.com/jundot/omlx/releases`, research §2.1 VERIFIED). Pick the generation this Mac
  runs (macOS 15 → `sequoia`, macOS 26/27 → `macos26-27`) and the *tag* whose version is the tested
  one. **Do not archive from `releases/latest`**: on 2026-10-29 the latest release was a release
  candidate that GitHub does not mark as a prerelease (research §2.1, VERIFIED), so "latest" would
  have handed over an rc. Sizes reported for the then-current assets: 837.8 MB (macOS 15) /
  875.2 MB (macOS 26-27); installed 1.7 GB (research §2.2).
- **Lab copy.** `~/Library/Application Support/OhYesMLX/archives/omlx-<version>/` (§6); restore by
  replacing `/Applications/oMLX.app`. Note the shim: `~/.omlx/bin/omlx` hardcodes
  `/Applications/oMLX.app/Contents/MacOS/omlx-cli` and the bundle's `omlx-cli` resolves its own
  location through `realpath` (research §2.4; `docs/runtimes/omlx.md` §1.2, VERIFIED) — so a
  restored bundle at `/Applications` is reachable, and a copy anywhere else is not.
- **Auto-update.** oMLX does not use Sparkle; it has its own updater, and this is more than the
  README claim the research could verify:

  | Claim | Label | Evidence |
  |---|---|---|
  | The app has an in-app updater | VERIFIED (string table; research §2.6 had it as CLAIMED from the README) | literals `AppUpdater`, `UpdateController`, `AvailableUpdate`, `oMLX/AppUpdater.swift`, `--omlx-update-worker`, `.oMLX-update.app`, `app.omlx.updater.` in `/Applications/oMLX.app/Contents/MacOS/oMLX` (2026-10-29) |
  | It discovers releases from GitHub | VERIFIED | literal `https://api.github.com/repos/jundot/omlx/releases?per_page=20` in the same binary |
  | It can stage and apply a build, not merely notify | VERIFIED (string table) | `Could not stage the update`, `Could not find the staged update. Try downloading again.`, `Could not start the updater launch agent`, `oMLX updater: signature verification failed`, `oMLX updater: could not clear quarantine` |
  | It has update channels | VERIFIED (string table) | `Display name for the Stable update channel`, `…Release Candidate…`, `…Dev…`, `Row label for selecting the app update channel` |
  | It has an automatic-update **notification** toggle | VERIFIED (string table) | `Row label for the automatic update notification toggle`, `Automatically Check` |
  | The stored preference key, and whether the toggle stops the *check* or only the *notification* | UNKNOWN | probe: no update key is stored today (`defaults read app.omlx \| grep -ic update` → 0, VERIFIED), so toggle the row in the app's settings and diff `defaults read app.omlx` to name the key; then, across two launches, confirm whether the GitHub releases request still happens (Console/`log stream` for the app, or the absence of `Checking for updates`) |
  | Whether the toolbar/menu offers a manual check | INFERRED | the string `Checking for updates` exists; its trigger is not observable from a string table |

  Because the updater verifies signatures and clears quarantine, an update it applies is a
  *signed* build — that is why the archive is a restore point rather than a defence against
  tampering. What the channel setting decides is which builds are offered at all; record the
  channel alongside the version, and prefer `Stable` on a machine that publishes tables.
- **Manifest field.** Nothing to set; `lab_path` stays `null` (§3).
- **Hazards for a cell.** `~/.omlx/bin/omlx-cluster-python` is rewritten on every start (do not
  treat it as stable); CLI flags are persisted into `~/.omlx/settings.json`
  (`docs/runtimes/omlx.md` §2.2); the SSD prefix cache survives restarts and is 69 GB on this host
  (research §2.6). The harness redirects the cache and passes `--no-cache` unless a cell pins
  `cache_state=on` — a lab copy does not get that protection if started by hand.

### 5.4 vMLX

- **Tested version.** `engines-tested.json` → `vmlx.version`.
- **How the tested build is obtained.** The release page: `jjang-ai/vmlx` and
  `jjang-ai/mlxstudio` publish the same assets, named
  `vMLX-<version>-sequoia-arm64.dmg` or `vMLX-<version>-tahoe-arm64.dmg`
  (`https://github.com/jjang-ai/vmlx/releases`, research §5.1, VERIFIED). Choose the asset that
  matches this Mac's macOS — the Tahoe build declares `LSMinimumSystemVersion 26.0.0`, so on
  macOS 15 it is the Sequoia asset. Sizes for the then-current assets: 579.0 MB (Sequoia) /
  604.5 MB (Tahoe); installed 2.0 GB (research §5.2). The PyPI package `vmlx` is the same engine
  without the app, but the onboarding route is the app (D2) and the harness starts the app's
  bundled CLI — archive the app.
- **Lab copy.** `~/Library/Application Support/OhYesMLX/archives/vmlx-<version>/` (§6); restore by
  replacing `/Applications/vMLX.app`. The wrapper `~/.local/bin/vmlx` is a real file that `exec`s
  the bundle path (research §5.4, VERIFIED), so the restored bundle is what the bare `vmlx` in
  the start command reaches.
- **Auto-update.** This one is fully readable, because the app is Electron and its main bundle is
  a plain `app.asar`:

  | Claim | Label | Evidence |
  |---|---|---|
  | 5 s after launch the app fetches two update manifests, picks the highest version, selects a macOS-specific download and tells the renderer (`app:updateAvailable`) | VERIFIED | `app.asar` contains `CHECK_DELAY_MS = 5e3`, `LATEST_URLS = ["https://raw.githubusercontent.com/jjang-ai/mlxstudio/main/latest.json", "https://mlx.studio/update/latest.json"]`, and `checkForUpdates(() => mainWindow, appVersion)` at startup (2026-10-29) |
  | The check is notify-only inside `checkForUpdates`: it ends at `win.webContents.send("app:updateAvailable", …)`; no download or install call is in that function | VERIFIED (function body) | same read; what the renderer does with the message is INFERRED |
  | It can be skipped: `VMLX_SKIP_UPDATE_CHECK=1` | VERIFIED | same function: `if (process.env.VMLX_SKIP_UPDATE_CHECK === "1") { console.log("[UPDATE] Skipping update check because VMLX_SKIP_UPDATE_CHECK=1"); return; }` |
  | It is not electron-updater | VERIFIED (absence of markers) | no `app-update.yml`, `latest-mac.yml`, `autoUpdater`, `setFeedURL`, `autoDownload` or `quitAndInstall` anywhere in `app.asar` |
  | An update has been applied on this host through this path | VERIFIED (observation) — mechanism INFERRED | the installed build moved from the tested one to 1.6.82 on 2026-10-29 (research §8); the check above is how a build is found. Whether the app installs on a single click is not established |
  | The env-var skip reaches a GUI-launched app | INFERRED | Finder/LaunchServices launches do not inherit a shell environment, and `Info.plist`'s `LSEnvironment` carries only `MallocNanoZone` (VERIFIED). `launchctl setenv VMLX_SKIP_UPDATE_CHECK 1` before launching does; `launchctl unsetenv` restores. A harness cell is unaffected either way: it starts `vmlx serve`, the bundled Python CLI, not the Electron app |
  | Whether the user-facing prompt can install without a second confirmation | UNKNOWN | probe: with a newer release available, launch the app and watch whether the prompt leads to a download or to a browser/DMG page; `grep` the asar for the `app:updateAvailable` handler on the renderer side (bounded read, not a whole-file scan) |
- **Manifest field.** Nothing to set; `lab_path` stays `null` (§3).
- **Hazards for a cell.** The installed bundle's Gatekeeper assessment currently fails
  (`spctl -a -vv` → "a sealed resource is missing or invalid"), while its signature is valid
  (research §5.6, VERIFIED) — record the assessment of a restored bundle, do not describe it as
  Gatekeeper-clean. The app's API gateway defaults to port 8080, which is OptiQ's harness port, and
  the block-disk cache under `~/.cache/vmlx-engine` turns itself on when batching and prefix
  caching are both active (the harness passes `--disable-block-disk-cache`).

---

## 6. Archiving an app build (the one procedure all three use)

Run this once per tested version, at archive time, with the machine otherwise idle. Nothing here
starts an engine; mounting a DMG read-only and reading a plist does not install anything. Never
overwrite an archive that already exists — a second version gets its own directory, and the old one
stays until no table names it.

```sh
# 0. Disk first: ~1.5 GB per macOS generation of archives plus ~1.1 GB per pip venv set (§7).
df -h ~

# 1. Resolve the tag and asset names from the release list, so the archive is a tag, not "latest".
#    (Swap the repo: osaurus-ai/osaurus, jundot/omlx, jjang-ai/vmlx.)
curl -s 'https://api.github.com/repos/osaurus-ai/osaurus/releases?per_page=20' \
  | jq -r '.[] | "\(.tag_name)\t\(.assets[] | "\(.name) \(.size)")"'

# 2. Download the asset whose name carries the tested version, into its own directory.
mkdir -p ~/Library/Application\ Support/OhYesMLX/archives/<engine>-<version>
cd ~/Library/Application\ Support/OhYesMLX/archives/<engine>-<version>
curl -L -o <asset>.dmg 'https://github.com/<org>/<repo>/releases/download/<tag>/<asset>.dmg'

# 3. Size, digest, and the disk image's own assessment.
du -h <asset>.dmg
shasum -a 256 <asset>.dmg | tee <asset>.dmg.sha256
spctl -a -t open --context context:primary-signature <asset>.dmg || true

# 4. The version inside the image must be the manifest's version before this counts as archived.
hdiutil attach -readonly -nobrowse <asset>.dmg
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Volumes/<volume>/*.app/Contents/Info.plist
codesign -dv --verbose=2 /Volumes/<volume>/*.app 2>&1 | head -12
hdiutil detach /Volumes/<volume>
```

What to record, and where: the digest sidecar stays beside the DMG. The size reflects the asset as
published, and `Plan.size_bytes_estimate` is by definition the download at plan time (research
§6.3) — so a size that no longer matches is information, not an error. The signature and
assessment belong in the record because "the app is signed" is a claim this project has already
had to walk back once (§5.4's Gatekeeper finding).

Restoring: quit the engine, open the archived DMG, drag the app to `/Applications` (replacing),
then confirm the version with the detector's own probe for that engine (`PlistBuddy` on
`Info.plist` for Osaurus and oMLX; the `__version__` read for vMLX —
`engines._detect_vmlx`). A restore that does not read back as the manifest's version has not
finished.

---

## 7. Disk

| Item | Size | Source |
|---|---|---|
| Osaurus standard DMG | 85.9 MB | research §1.2 (release API, VERIFIED) |
| oMLX DMG, one macOS generation | 837.8 MB (macOS 15) / 875.2 MB (macOS 26-27) | research §2.2 |
| vMLX DMG, one macOS generation | 579.0 MB (Sequoia) / 604.5 MB (Tahoe) | research §5.2 |
| **Archives, one generation** | **≈1.50 GB** (macOS 15) / **≈1.57 GB** (macOS 26+) | sum of the above |
| mlx-lm venv | 472 MB | research §8 (clean install, VERIFIED) |
| OptiQ venv | 612 MB | research §8 (clean install, VERIFIED) |
| **One lab venv per pip engine** | **≈1.08 GB** | sum of the above |
| **Total for one tested version set** | **≈2.6 GB** | archives + venvs |

This is what plan 025-03's disk check is sized against (2–5 GB): about 2.6 GB for one macOS
generation, and up to ~3.1 GB of archives alone if both generations are kept. None of it is model
weights — the shared Hugging Face cache and the engine-native caches are separate and much larger
(research §6.5: 177 GB HF cache, 83 GB Osaurus KV cache, 69 GB oMLX cache, 22 GB vMLX block cache
on this host). The wallet is the download; the disk after use is the caches.

The wizard checks free space before it downloads anything and stops with the number if the machine
is short, rather than half-archiving. It never deletes an existing archive and never touches
`/Applications`.

---

## 8. Version-bump checklist

An engine has a new version. The ordering matters: nothing is adopted before a canary says
whether the numbers moved, and no table gains a row from a build nobody chose.

**The quiet-machine rule, which is not a suggestion.** Nothing else runs on this machine while a
cell is measured — not a test suite, not a git operation, not a download, not "lightweight"
background work. The harness cannot detect contention, so the rule holds without enforcement
(AGENTS.md). The canary reads the 1-minute load average around each engine's cell; above
`canary.LOAD_NOISY` (4.0 on this 12-core host) the engine is marked **noisy** and `--record`
refuses its baseline unless `--allow-noisy` says the number is wanted anyway. The reason is on
record: the 2026-09-16 grid published a 40.6% drift that was contention, not a runtime.

1. **Note the new version in STATE.** One row: which engine, from which build to which, dated, and
   that it is untested until step 7. `.paul/STATE.md` is the only state store — there is no second
   place a version decision is recorded.
2. **Run the canary for that engine.** `ENGINES=<engine> scripts/run_canary.sh`. The runner sweeps
   the harness ports and stale Osaurus app processes, pins and restores the Osaurus settings
   (`scripts/osaurus-pin.sh`, byte-exact `cmp`), runs `ohyesmlx canary --yes --engines <engine>`,
   and logs to `results/canary/runner-<timestamp>.log`. One engine is enough for the question "did
   this bump move the number"; `ENGINES` unset runs all five.
3. **Read the verdict line for that engine.** `ohyesmlx/canary.py` prints one line per engine:
   `no effect on our tables`, `moved <±N%>: re-run the grids containing <runtime>`,
   `no baseline recorded: --record writes one`, or `FAIL: <reason>`. The comparison is
   `decode_tok_s` and `ttft_s` against the manifest's `canary` block, and the floor is 5% — a
   change on the floor is "no effect", because below ~5% two sessions of the same cell on this host
   are one reading (`canary.NOISE_FLOOR`, Decision 131).
4. **A `FAIL` is not a verdict.** A cell that failed the coherence gate or never started has no
   number to compare; fix the cell or the host settings and re-run. Nothing is adopted from a
   failed cell.
5. **`no baseline recorded`** means the manifest has no baseline yet — record one on the current
   build with `RECORD=--record ENGINES=<engine> scripts/run_canary.sh`. `--record` writes the
   `canary` block's four numbers and nothing else; it never changes `version` or `verified`.
6. **`no effect on our tables` → adopt.** Adopt by editing `ohyesmlx/engines-tested.json`:
   `version` becomes the new build and `verified` the date of the canary run. That edit is the
   decision; `--record` is not, which is why it is a separate step and a separate commit reason.
7. **`moved ±N%` → re-run the named grids**, on a quiet machine, on the new build, before
   adopting. Report the drift in STATE with the canary's number. A grid re-run under a new build is
   a new column/table with its own version recorded.
8. **Re-record the baseline on the adopted build.** `RECORD=--record ENGINES=<engine>
   scripts/run_canary.sh` after the adopt, so the baseline's `version_measured` equals the
   manifest's `version`. A baseline left on the old build makes the *next* bump a comparison across
   two builds — exactly the confound the canary exists to avoid.
9. **Move the frozen copy, and keep the old one.** A new tested version is a new venv
   (`engines/<name>-<new>`) or a new archive directory; the old one stays until no table names it.
   Update the machine-local `lab-paths.json` entry if the pip engine's lab path moves — the file,
   never the committed manifest. For a pip engine, freeze the new venv with
   `<venv>/bin/python -m pip freeze --all`, prefixed by the three header lines §4 shows, into
   `ohyesmlx/constraints/<name>-<new>.txt`: **a bump is not done until its constraints file is
   committed**, and `install_plan` refuses the install until it exists.
10. **Rows from different builds never share a table.** A row records `runtime_version`; the join
    guard refuses to join across builds, and this is a rule about tables, not only about joins.
    If a table must show both, they are two columns that each name their build.
11. **Commit.** The manifest edit, the pip engine's constraints file, the STATE row, the doc change
    if the procedure changed. The commit message says which build was adopted and what the canary
    said.

**Osaurus standing authorisation, from AGENTS.md (Jason, 2026-10-29).** Any test, canary or run
may pin Osaurus (idle 900, caches off, baseline re-recorded) provided his own settings (idle
residency 30) are restored and verified byte-exact with `cmp`, and the report says so.
`scripts/run_canary.sh` is the pattern: it sources `scripts/osaurus-pin.sh`, installs a restoring
trap, and calls `osaurus_restore_check` whether the run succeeded or not. Anything that pins
Osaurus outside that runner owes the same restore and the same statement in its report.

---

## 9. What is not established

Everything here is a probe named where the claim is made; this is the index, so the list cannot
quietly shrink.

| Engine | Question | Probe |
|---|---|---|
| Osaurus | Is there an automatic-update toggle in the app's settings, and which defaults key does it write? | Settings → General → Updates → toggle; diff `defaults read com.dinoki.osaurus`; confirm by the absence of Sparkle's `didFindValidUpdate`/`didNotFindUpdate` lines across two launches |
| Osaurus | Does the app install an update without a user accepting it? | absence of `SUAutomaticallyUpdate` is evidence, not proof; watch a release cycle: the version must not change while the app is open and untouched |
| oMLX | Which defaults key is the automatic-update notification toggle, and does it stop the check or only the notification? | toggle the row, diff `defaults read app.omlx` (0 update keys today); watch for the GitHub releases request on the next launch |
| oMLX | Is the update channel selectable, and what is selected on this host? | the string table says the row exists; read it in the app's settings and record it with the version |
| vMLX | Does the `app:updateAvailable` prompt install without further consent? | trigger a prompt against a newer release and observe; read the renderer's handler with a bounded asar read |
| vMLX | Does `VMLX_SKIP_UPDATE_CHECK=1` reach a Finder-launched app? | `launchctl setenv`, launch from Finder, check the app's log for the skip line; `launchctl unsetenv` afterwards |
| all three | Is a second copy genuinely unsafe, or merely unreachable? | not testable inside this plan's boundaries (no parallel install); the argument in §5.1 is from code and bundle facts, and says what would change it |
| mlx-lm, OptiQ | Can a `pip` or interpreter upgrade reach a lab venv unintended? | `uv python` can move the interpreter (optiq.md §1.2); re-run each engine's version probe after any toolchain upgrade, and treat a changed version as a bump (§8) |

---

## 10. Cross-references

- `ohyesmlx/engines-tested.json` — the only tested-versions table; `engines.load_manifest`,
  `engines.MANIFEST`, `engines.TESTED_VERSIONS`, `engines.detect_all`.
- `ohyesmlx/engines.py` — `lab_paths`, `LAB_PATHS_FILE`, `LAB_PATHS_NAME`, `LAB_ENGINES`,
  `_lab_paths_file`, `_app_engine_venvs`, `_engines_dir`, `_command_plan`, `install`.
- `ohyesmlx/runtimes.py` — `_engine_env` (the one consumer that turns a lab path into `PATH`),
  `OSAURUS_EXECUTABLE`, `_resident_osaurus_pids`.
- `ohyesmlx/canary.py` — `verdict`, `verdict_line`, `record`, `NOISE_FLOOR`, `LOAD_NOISY`.
- `scripts/run_canary.sh` — the runner; `scripts/osaurus-pin.sh` — the Osaurus settings pin and
  byte-exact restore.
- `docs/research/2026-10-29-engine-install-paths.md` — install routes, sizes, detection paths,
  §5.6 vMLX Gatekeeper, §6.3 version drift, §8 the pinned pip installs and their clean sizes.
- `docs/runtimes/osaurus.md` (§0.1 `--help` is not read-only, §1.2 MCP relaunch, §1.4 Sparkle,
  §7.6 automatic checks), `docs/runtimes/omlx.md` (§1.2 the shim, §2.2 persisted flags, §3 the
  settings surface), `docs/runtimes/vmlx.md` (§1.1 the wrapper, §1.4 the GUI composes the CLI),
  `docs/runtimes/mlx-lm.md` (§1 start command), `docs/runtimes/optiq.md` (§1.1 shebang, §3
  settings outside the venv).
- `docs/interfaces.md` — the pinned shapes; the v5.0 note on `lab_path` is the contract this
  document's §3 implements.
- `AGENTS.md` — one model resident at a time; nothing else runs during a cell; never infer a
  capability from the absence of a flag; the Osaurus standing authorisation.
