# S6 findings — Packaging and release

Reviewer: Fable 5.2 final pass, 2026-11-15. Scope: `dossier-S6.md`. Nothing in the dossier's
"Already known" list is repeated. No code was edited and nothing was run; evidence is source
text plus read-only file listings of `dist/OhYesMLX.app` and `~/Library/Caches/OhYesMLX/build`.

Lock-open failure reported as "already running" (`BackendLauncher.swift:260-269`) was seen again
here and is already S3 F14; a pip engine that is "installed" yet unstartable with no repair path
is S4 F2. F4 below is a new route into S4 F2's dead end, not a restatement of it.

No finding is High: nothing here publishes a wrong number or damages user data. Eight are Medium
because each one either ships something the release evidence says cannot ship, or is a gate that
cannot fail.

---

### F1 — The bundle ships timestamp pycs for the stdlib modules the build itself imported, so the "unchecked-hash everywhere" fix for the sealed-bundle writes is incomplete
- Severity: Medium
- Where: scripts/build_app.sh:33-34 (no `-B`), :55 (`ditto` of the cache tree), :76-77 (`compileall` without `-f`), :78 (the only assertion)
- Failure scenario: `build_app.sh:33` runs the *cache* interpreter without `-B` to read `__version__`; `ohyesmlx/__init__.py` imports `json`, `tempfile`, `pathlib`, so default (timestamp) pycs are written into `~/Library/Caches/OhYesMLX/build/…/python/lib/python3.14/**/__pycache__`. `:55` copies them into the bundle with mtimes preserved. `compileall` without `-f` skips any source whose existing pyc header is `magic + flags 0 + source mtime`, so those modules keep timestamp pycs. A timestamp pyc is revalidated against the source mtime on every import. Any transfer that does not reproduce mtimes to the second (`cp -R` without `-p`, an unarchiver that restores DOS times, a sync tool) makes them stale; the first child interpreter that is not `-B` (`{python} -I -m venv`, `engines.py:797`; pip; every engine server in a venv, which shares the bundle's stdlib) then rewrites them inside `/Applications/OhYesMLX.app` and the code seal breaks — the 05-06 finding #1 again, for exactly the modules (`shutil`, `tempfile`, `fnmatch`, `random`, `functools`, `types`, …) that venv and pip import first.
- Evidence: cache listing shows `json/__pycache__/{__init__,decoder,scanner,encoder}.cpython-314.pyc` (precisely `import json`'s closure) and 29 top-level pycs including `tempfile`, `shutil`, `random`, `fnmatch`, `glob`, `weakref`, `ssl`, `socket`, `threading`, `base64`. The bundle's `json/__pycache__` holds those four plus `tool` and `__main__` (the two `compileall` added). Bundled `compileall.py:228-236`: `if not force:` … `expect = struct.pack('<4sLL', importlib.util.MAGIC_NUMBER, 0, mtime & 0xFFFF_FFFF)` … `if expect != actual: break` / `else: return True`. The build comment at :71-75 claims "a copy, a zip or a read-only volume can never make one look stale". `:78` asserts only that one pyc exists under `ohyesmlx`.
- Confidence: 80 that timestamp pycs are in the shipped bundle (I could not read the flag word: binary reads were not available). 100 with `python3 -c` over `dist/OhYesMLX.app` counting pycs whose bytes 4-8 are `00 00 00 00`. 50 that a normal Archive Utility unzip makes them stale; that needs one unzip-and-stat.
- Fix direction: `-B` at :33; `-f` on the `compileall` at :76 (or delete every `__pycache__` under `Resources/python` first); replace the :78 assertion with a walk that fails on any pyc whose flags are not `1` and on any `.py` without one. The existing cache on this Mac is already polluted, so `-B` alone does not fix the next build.
- Test idea: build, then assert zero pycs under `Contents/Resources/python` have a zero flags word. Fails today.

### F2 — The unpacked interpreter tree is reused without verification, and it has already diverged from the tarball the SBOM names
- Severity: Medium
- Where: scripts/fetch_python_standalone.sh:70 (reuse test), :50-68 (the gate covers the tarball only); scripts/build_app.sh:55; scripts/make_sbom.py:137-144
- Failure scenario: the tarball's sha256 is re-verified on every run, but the tree that is actually copied into the bundle is `"$UNPACKED/python"`, reused whenever `bin/python3` is executable. It lives in a user-writable cache and is mutated by ordinary use (F1; the `ssl`/`socket`/`base64`/`threading` pycs there were written by some run no build step performs). A `pip install` into that interpreter, an edited stdlib file, or a planted `.pth` is copied, ad-hoc signed and zipped; the SBOM states the tarball's url and sha256 for a tree that is no longer that tarball's, and lists no bundled package at all. Hotspot 1 names "a cache trusted without re-verification" as the thing the gate exists to stop; the gate stops it one step too early.
- Evidence: `if [ ! -x "${UNPACKED}/python/bin/python3" ]; then … tar -xzf …; fi`; `ditto "$PYTHON_ROOT" "$CONTENTS/Resources/python"`; SBOM `interpreter.sha256` is the pin constant passed through `--interpreter-sha256`.
- Confidence: 90 on the mechanism (cache contents observed). What is unproven is only whether anything worse than pycs is in the tree today.
- Fix direction: unpack the verified tarball into a fresh temp directory on every build (seconds, ~100 MB) and delete it afterwards; keep only the tarball cached. That also removes F1's source.
- Test idea: touch a marker file into `$UNPACKED/python/lib/python3.14/site-packages/`, build, assert the marker is absent from the bundle. Fails today.

### F3 — check_bundle's P5-6 signature check cannot fail for the defect it was written for
- Severity: Medium
- Where: scripts/check_bundle.sh:143-158 (read-only image), :186-198 (the only request), :252-254 (the verify)
- Failure scenario: the regression P5-6 guards is "a child interpreter writes bytecode into the signed bundle". The check runs the app from a `UDRO` image, where a write cannot land (Python ignores a failed pyc write), then verifies the signature of that immutable copy — a comparison of the image with itself. It also never causes a child interpreter to run: the one request is unauthenticated `GET /hardware`, answered 401 before any handler, and both `200` and `401` pass. F1 therefore passes this gate, and so would a build with no precompile at all. The threat-model row cites this check as the evidence that "`codesign --verify --deep --strict` still passes".
- Evidence: `hdiutil create … -format UDRO`; `case "$CODE" in 200 | 401) break` and `401) pass P5-6 "GET /hardware was served…"`; `codesign --verify --deep --strict "$MOUNT/OhYesMLX.app"`; threat-model.md:603.
- Confidence: 85. Raised by building with the `compileall` step removed and observing "all checks PASS".
- Fix direction: keep the read-only run for "works where it cannot write", and add the missing half: copy the bundle to a writable temp dir without preserving mtimes, run `Contents/Resources/python/bin/python3 -I -m venv <tmp>` and one `-I -c "import email, json, tempfile, ssl"` from it (no `-B`, as the app's children run), then verify the signature and assert no file under the bundle is newer than the copy.
- Test idea: the mtime-stripped writable copy plus a child `import json`; `codesign --verify` afterwards. Expected to fail today on F1.

### F4 — Moving the app after installing engines leaves them "installed" and unstartable, and the recovery gatekeeper.md gives is refused by the app
- Severity: Medium
- Where: ohyesmlx/engines.py:797 and :1173 (venv from `sys.executable`), :265-279 (version read from files only), :1242-1245 (`already_installed`); docs/release/gatekeeper.md:21-24; app/Sources/OhYesMLXKit/AppModel.swift:255-257
- Failure scenario: an engine venv's `bin/python` is a symlink to `<bundle>/Contents/Resources/python/bin/python3`. The translocation guard catches only `/AppTranslocation/`; a copy run from `~/Downloads` or `~/Desktop` without the quarantine flag (unzipped in Terminal, fetched with `curl`, built locally) is not translocated, so engines install against that path. The user then moves the app, as the doc tells them to. Detection reads `pyvenv.cfg` and a version file and stats the console script, all regular files, so the row still reads installed and tested. Every start fails on a dangling shebang interpreter, which surfaces as "No such file" for the script. The doc's fix — "open the Engines screen and install mlx-lm and OptiQ again" — returns `already_installed; nothing was overwritten`, and the backend has no uninstall. The only way out is deleting `~/Library/Application Support/OhYesMLX/engines` by hand, which the doc does not say. A later release bundling a different Python minor breaks the same venvs the same way without any move.
- Evidence: `command=["{python}", "-I", "-m", "venv", root]`; `python=sys.executable`; `_venv_package_version` → `_read_or_none(env, os.path.join(root, "pyvenv.cfg"))`; `"already_installed", f"{engine} is already installed; nothing was overwritten"`; grep for `uninstall|remove_engine|repair` in `ohyesmlx/*.py` finds nothing; `bundlePath.contains("/AppTranslocation/")`.
- Confidence: 75. I did not read detection at :526-563 and rely on S4 F2's quotation of it. Raised by a fixture whose venv `bin/python` symlink dangles: assert `/engines` still says installed.
- Fix direction: make "installed" for an app-managed venv require that `bin/python` resolves to an existing executable; treat a dangling one as an incomplete install that `install` removes and redoes (the same repair S4 F2 asks for). Then the doc's sentence becomes true.
- Test idea: fixture engines dir with a venv whose `bin/python` points at a missing path; assert `detect_all` reports not installed, or `install` does not refuse.

### F5 — The clean-account smoke that is meant to close P5-5 runs a wheel in a Homebrew-Python venv, not the bundle
- Severity: Medium
- Where: scripts/smoke_clean_account.py:843-855; scripts/smoke_clean_account.sh (`PY=/opt/homebrew/bin/python3.14`, the `uv build` + `pip install --no-deps --no-index` setup)
- Failure scenario: 05-06 AC-6 asks for the built app's backend "via the bundled interpreter, exactly the launcher's argv and env". The committed smoke spawns `<venv>/bin/ohyesmlx app` — a console script, no `-I`, no `-B`, the client's inherited environment, Homebrew's CPython, and a package tree built from `git archive HEAD` rather than the `ditto` of the working tree that ships. Engine venvs it creates descend from Homebrew's interpreter. Once the sudoers step lands and the smoke goes green, the threat-model's "clean account pending" will be closed with evidence about an artifact no user receives; none of P5-3, P5-6, P5-9 or the bundled OpenSSL/trust-store path is exercised on the clean account. The scripts have no flag to point at a bundle.
- Evidence: `binary = os.path.join(sys.prefix, "bin", "ohyesmlx")`; `Popen([binary, "app"], stdin=PIPE, stdout=PIPE, stderr=log)`; launcher argv `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` (BackendLauncher.swift:185).
- Confidence: 90 on what the script runs; the open part is intent, which 05-06-PLAN AC-6 states.
- Fix direction: give the client one `--python <path>` option that spawns `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` under the launcher's four-entry environment, and have the driver copy `dist/OhYesMLX.app` into the test account and pass its interpreter. Record in the results which artifact was run.
- Test idea: a unit test on the spawn-argv builder asserting `-I -B -m ohyesmlx.cli app` when `--python` is given. No such builder exists today.

### F6 — The SBOM can name a commit that does not contain the shipped code, and its source digest is taken from the repository, not from the bundle
- Severity: Medium
- Where: scripts/make_sbom.py:94-113; ohyesmlx/measure.py:436-440; scripts/build_app.sh:68 and :111; docs/release/gatekeeper.md:59
- Failure scenario: the build copies the working tree (`ditto "$ROOT/ohyesmlx"`, untracked and modified files included) and never checks it is clean; the SBOM stamps `git rev-parse HEAD`. A release built with one uncommitted edit publishes "the git commit it was built from" for code that commit does not hold, and nothing in the document says so. Separately, `source_sha256` is computed minutes after the copy, over `$ROOT/ohyesmlx/*.py`, by whichever `python3` runs the script — so an edit between :68 and :111 yields a digest of code that did not ship. The digest covers top-level `*.py` only: `catalog.json` (which models are offered and downloaded), `engines-tested.json` and `longtext.md` ship unhashed.
- Evidence: `["git", "-C", str(repo), "rev-parse", "HEAD"]` with no `status --porcelain`; `from ohyesmlx.measure import _source_sha256` after `sys.path.insert(0, str(REPO_ROOT))`; `for path in sorted(Path(__file__).parent.glob("*.py")…)`; gatekeeper.md:59 "the git commit it was built from".
- Confidence: 90 (all three are direct readings). The Q3 experiment in the dossier would make it 100.
- Fix direction: refuse to build, or write `"git_dirty": true` and no commit, when `git status --porcelain -- ohyesmlx app` is non-empty; compute the digest by running the *bundled* interpreter's `ohyesmlx.measure._source_sha256()` with `-I -B`, so it hashes what shipped; add the package's data files to a second digest rather than widening the harness's definition.
- Test idea: `make_sbom` unit test with a fake repo where `git status --porcelain` is non-empty; assert the document does not carry a bare `git_commit`. Fails today.

### F7 — check_bundle's P5-9 environment check contradicts its own recorded evidence, and its PATH match is a substring
- Severity: Medium
- Where: scripts/check_bundle.sh:209-231; docs/threat-model.md:606; AGENTS.md ("`scripts/check_bundle.sh dist/OhYesMLX.app` all PASS")
- Failure scenario: the script's comment says that on macOS 27.2.1 `ps eww`, `ps -E` and `KERN_PROCARGS2` return no environment block, and in that case the `*)` branch counts a FAIL ("needs a decision here"). This Mac runs Darwin 27.2. Either the gate cannot print "all checks PASS" on the release machine — so the packaging gate in AGENTS.md is unmeetable and the threat-model's "P5-9 Met … check_bundle P5-9: the backend's PATH is launchd's default" was not observed by this check — or the comment is false. One of the two published statements is wrong and the decision the message asks for was never recorded. When the block is readable, `*"PATH=/usr/bin:/bin:/usr/sbin:/sbin"*` also accepts `PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin` and `MANPATH=/usr/bin:/bin:/usr/sbin:/sbin`, and only `PYTHONPATH=`/`PYTHONHOME=` are looked for, so the message "carries no PYTHON* variable" is broader than the test.
- Evidence: comment at :209-212; `*) fail P5-9 "macOS $(sw_vers -productVersion) prints no environment for another process … needs a decision here"`; threat-model.md:606.
- Confidence: 55 on which side is wrong (not runnable under this review's rules); 90 that the two cannot both be true as written. Settled by one `ps eww -p <own pid> -o command=` on this OS.
- Fix direction: make the withheld case a printed `SKIP P5-9 (env not readable; pinned by LauncherTests.testArgvEnvironmentAndDirectory)` that does not count as a failure, and correct the threat-model evidence cell to cite what actually established it. Match PATH as a whole space-delimited token and test `PYTHON[A-Z]*=`.
- Test idea: feed the env-matching `case` a fixture string `… PATH=/usr/bin:/bin:/usr/sbin:/sbin:/tmp/x` and assert FAIL. Passes (wrongly) today.

### F8 — The release's integrity story is unbacked: no step produces the promised sha256, and the doc credits the ad-hoc signature with tamper evidence it does not give
- Severity: Medium
- Where: scripts/build_app.sh:8 and :124-129; docs/release/gatekeeper.md:30-31, :52-56; scripts/make_sbom.py:128-147
- Failure scenario: gatekeeper.md tells users "A sha256 is published next to the zip" and to compare it; the build prints three paths and computes no digest (its header lists `shasum` among the tools it uses; it never calls it). The promise depends on someone remembering at release time, and the SBOM carries no digest of the zip, the Swift binary or the bundled tree, so an SBOM cannot be tied to the zip it sits beside. The same doc says the ad-hoc signature means "macOS can tell the files have not been changed since they were built". An ad-hoc signature has no identity: anyone who alters the zip re-signs it with `codesign --force --sign -` and it verifies. For an unnotarized download the sha256 is the only integrity anchor, and it is the one with no producing step.
- Evidence: `printf '%s\n' "$APP" "$ZIP" "$SBOM"` is the script's last line; no `shasum` in `build_app.sh` or `make_sbom.py`; gatekeeper.md:30-31 and :52-53 as quoted.
- Confidence: 90.
- Fix direction: after the zip, write `OhYesMLX-$VERSION.zip.sha256` with `shasum -a 256` and print it as a fourth path; reword :30-31 to say the signature only lets macOS run the code and that the published sha256 is what shows the download is unaltered.
- Test idea: a shell check that `build_app.sh`'s output lists a `.sha256` file whose content matches `shasum -a 256` of the zip. Fails today.

### F9 — No gate runs the path every downloader takes: a quarantined zip
- Severity: Low
- Where: scripts/check_bundle.sh (whole), scripts/smoke_clean_account.sh (whole); app/Sources/OhYesMLXKit/AppModel.swift:255-257
- Failure scenario: `check_bundle` opens a locally built, never-quarantined bundle from a local disk image; the smoke runs a wheel (F5); the translocation guard is tested with an injected string. Nothing sets `com.apple.quarantine` on the zip, unpacks it with Archive Utility and launches the result, so three things are asserted without an observation: that the guard screen appears under real translocation, that after "Open Anyway" the app may exec the quarantined bundled `python3` and load its extension modules from `Contents/Resources`, and gatekeeper.md:45's "macOS asks again". If the second is false, the first public release shows "Couldn't start" on every Mac but the builder's.
- Evidence: no `xattr` or `quarantine` in any script in scope; `open "$MOUNT/OhYesMLX.app"` on an image made from `$APP`.
- Confidence: 90 that the path is untested; unknown whether it breaks, which is the reason to test it once.
- Fix direction: one manual-or-scripted release step, recorded in the summary: `xattr -w com.apple.quarantine "0083;$(printf %x $(date +%s));Safari;" OhYesMLX-<v>.zip`, unzip with Archive Utility, open from Downloads (expect the move screen), move, approve, open (expect a served `/hardware`).
- Test idea: the step above; its transcript is the evidence.

### F10 — "Remove everything the app has added" leaves two things behind
- Severity: Low
- Where: docs/release/gatekeeper.md:71-87; ohyesmlx/engines.py:813-828; app/Sources/OhYesMLXKit/AppModel.swift:221, :235
- Failure scenario: the doc says the app "keeps three places on disk" and gives steps "to remove everything". The pip argv carries no `--no-cache-dir`, so each engine install fills `~/Library/Caches/pip` with the wheels of a 105-package closure (hundreds of MB for the MLX stack), and the app's `UserDefaults.standard` writes `~/Library/Preferences/io.github.jasonrandazza.ohyesmlx.plist` (the in-flight job record). Neither is listed, and a user who follows the steps to reclaim disk does not get the pip cache back. The table's third row (`~/Library/Caches/OhYesMLX`) exists only on a machine that built from source.
- Evidence: the pip `command=[…, "--isolated", "--no-input", "--disable-pip-version-check", "--require-hashes", "--only-binary", ":all:", "--no-deps", "-r", …]`; `defaults: UserDefaults = .standard`.
- Confidence: 80 (pip's default cache location is from pip's documented behaviour, not observed on the test account).
- Fix direction: add `--no-cache-dir` to the one pip argv (hash-checked wheels are fetched once per install anyway) and add the Preferences plist to the doc's table and steps.
- Test idea: extend the existing pip-argv test to require `--no-cache-dir`.

### F11 — P5-4 reports a network outage as a packaging failure and cannot tell it from a TLS failure
- Severity: Low
- Where: scripts/check_bundle.sh:105-133
- Failure scenario: any `URLError` — DNS down, Hugging Face incident, an offline build machine — fails P5-4 with "the HTTPS GET failed", the same line a missing trust store would print, and the script exits 1. A release gate that goes red for the internet teaches people to rerun it until it is green, and a real certificate-verification regression then reads as "flaky network". The two assertions that are the actual property (`CERT_REQUIRED`, `check_hostname`) run only after the GET succeeds.
- Evidence: the heredoc asserts `verify_mode`/`check_hostname` after `urlopen(…)`; a raised `URLError` skips them and the shell prints `fail P5-4 "the HTTPS GET failed (see above)"`.
- Confidence: 85.
- Fix direction: assert the context properties and `ssl.get_default_verify_paths()` resolving to an existing CA file before any network call; catch `URLError` and print `FAIL P5-4 (certificate)` only when its reason is `ssl.SSLCertVerificationError`, otherwise `FAIL P5-4 (network unreachable; rerun)`.
- Test idea: run the P5-4 block with networking off; today the output does not say which of the two failed.

---

Coverage:

Hotspots
1. fetch_python_standalone.sh:58-68 sha256 gate — covered (gate sound for the tarball; F2 for what it does not cover)
2. fetch_python_standalone.sh:70-81 unpack / `rm -rf` — covered (paths are fixed strings under `set -eu`; reuse test is F2)
3. build_app.sh:45-52 `rm -rf "$APP"` / plist — covered (no finding; deletion is confined to `dist/OhYesMLX.app`, empty VERSION is guarded)
4. build_app.sh:59-63 `sys.prefix` assertion — covered (no finding)
5. build_app.sh:71-78 unchecked-hash precompile — covered (F1)
6. build_app.sh:88-108 signing loop — covered (no finding; see Q1)
7. build_app.sh:110-122 SBOM-after-sign ordering — covered (re-verify present; F6 for what the SBOM reads)
8. make_sbom.py:29-60 `parse_requirements` — covered (no finding; correct for the committed `pin \` + `--hash` shape, fails closed otherwise)
9. make_sbom.py:94-113 provenance split — covered (F6)
10. check_bundle.sh:138-156 read-only image setup — covered (F3)
11. check_bundle.sh:172-198 port and `/hardware` — covered (F3; port is taken from the backend's own pid, no finding there)
12. check_bundle.sh:201-231 P5-9 argv and env — covered (F7)
13. smoke_clean_account.sh:36-42 `as_test_user` — covered (no finding)
14. smoke_clean_account.sh:181-243 sweep — covered (no finding; every listing carries `-u $TEST_USER`)
15. smoke_clean_account.sh:285-302 teardown — covered (no finding)
16. smoke_clean_account.py:825-917 spawn and shutdown — covered (F5; the `finally` shutdown is sound)
17. smoke_clean_account.py:444-465 `read_launch_line` — covered (no finding)
18. BackendLauncher.swift:158-233 spawn path — covered (no new finding)
19. BackendLauncher.swift:243-274, :380-398 App Support, lock, quit — covered (no new finding; lock conflation is S3 F14)
20. AppModel.swift translocation guard — covered (F4, F9; the relaunch door at :386-389 was taken from the dossier, not re-read)

Open questions
- Q1 unsigned code under a verified bundle — covered, no finding: `--deep --strict` treats a Mach-O under `Resources` as a sealed resource and would not flag an unsigned one, so :107 is not the net; the per-file sign-and-verify loop is, and arm64 refuses unsigned code at load. No file `file -b` would misclassify is executed. Not verified by running `codesign`.
- Q2 moved app — covered (F4)
- Q3 SBOM vs what ships — covered (F6)
- Q4 gatekeeper promises — covered: (a) F8; (b) no finding — the only egress in the served modules is `fetch.HF_BASE` and pip, `runtimes.py:1431/1454` are engine-local calls, and the `github.com`/`pypi.org` URLs are opened in the browser as the doc says; (c) F9; removal steps F10
- Q5 P5-9 env branch — covered (F7)
- Q6 smoke artifact — covered (F5)
- Q7 `compileall` coverage — covered (F1: every `.py` under `lib` is compiled, but pre-existing timestamp pycs are not replaced)
- Q8 P5-4 and the network — covered (F11)

Coverage: 28/28 (20 hotspots, 8 questions). Limits: nothing was executed, so F1's flag word, F7's `ps` behaviour and Q1's `codesign` behaviour are argued from source and listings, with the single command that settles each named in the finding.
