# Order: verify one Fable 5.2 finding (V step)

You verify one finding from a senior reviewer. Its report is a claim, not evidence. Your job is to prove it or refute it.

You run inside the `fable-verify` Orca worktree (branch `review/fable-verify`). Write exactly one report file:
`.paul/review/fable-5.2/verify/<FINDING-ID>.md`. If you can write a test, put it in a NEW file named after the finding
(`tests/test_fable_<finding-id>.py`, or `app/Tests/OhYesMLXKitTests/Fable<FindingId>Tests.swift`), so parallel
verifiers never edit the same file. Never fix the code.

Method:
1. Read the cited code (the ranges named) and its dossier entry. The dossiers live in the main checkout (read-only, absolute path):
   `/Users/jrazz/Dev/active/OhYesMLX/.paul/review/fable-5.2/dossier-S<n>.md`. Restate the claim in one line.
2. Try to reproduce it with the smallest failing test (pytest, or a swift test in app/Tests). Run only that test:
   `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q <file>::<name>` or
   `cd app && swift test --filter <name>`. A test that passes on the current code means the claim is not reproduced.
3. If no test is possible (a race needing real timing, a GUI-only path, packaging), give the concrete evidence instead:
   the exact code path with line numbers, or a command and its output.
4. End the file with exactly one verdict line:
   `VERDICT: CONFIRMED (test: <path::name>)` or `VERDICT: CONFIRMED (no test: <why>)` or `VERDICT: REFUTED (<evidence>)`
   and a line `SEVERITY-CHECK: agree | lower to <x> | raise to <x> — <why>`.
Never start a server, engine, model download or the app. Never edit code outside the one test you add.

---
FINDING:
 (BATCH) S6-F9 S6-F10 S6-F11

BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing
one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test
file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more
than about 40 lines. Do not spawn subagents. If tests/test_fable_<id>.py already exists (a killed earlier run), run and reuse it rather than rewriting it.

=== FINDING-ID: S6-F9 ===
### F9 — No gate runs the path every downloader takes: a quarantined zip
- Severity: Low
- Where: scripts/check_bundle.sh (whole), scripts/smoke_clean_account.sh (whole); app/Sources/OhYesMLXKit/AppModel.swift:255-257
- Failure scenario: `check_bundle` opens a locally built, never-quarantined bundle from a local disk image; the smoke runs a wheel (F5); the translocation guard is tested with an injected string. Nothing sets `com.apple.quarantine` on the zip, unpacks it with Archive Utility and launches the result, so three things are asserted without an observation: that the guard screen appears under real translocation, that after "Open Anyway" the app may exec the quarantined bundled `python3` and load its extension modules from `Contents/Resources`, and gatekeeper.md:45's "macOS asks again". If the second is false, the first public release shows "Couldn't start" on every Mac but the builder's.
- Evidence: no `xattr` or `quarantine` in any script in scope; `open "$MOUNT/OhYesMLX.app"` on an image made from `$APP`.
- Confidence: 90 that the path is untested; unknown whether it breaks, which is the reason to test it once.
- Fix direction: one manual-or-scripted release step, recorded in the summary: `xattr -w com.apple.quarantine "0083;$(printf %x $(date +%s));Safari;" OhYesMLX-<v>.zip`, unzip with Archive Utility, open from Downloads (expect the move screen), move, approve, open (expect a served `/hardware`).
- Test idea: the step above; its transcript is the evidence.


=== FINDING-ID: S6-F10 ===
### F10 — "Remove everything the app has added" leaves two things behind
- Severity: Low
- Where: docs/release/gatekeeper.md:71-87; ohyesmlx/engines.py:813-828; app/Sources/OhYesMLXKit/AppModel.swift:221, :235
- Failure scenario: the doc says the app "keeps three places on disk" and gives steps "to remove everything". The pip argv carries no `--no-cache-dir`, so each engine install fills `~/Library/Caches/pip` with the wheels of a 105-package closure (hundreds of MB for the MLX stack), and the app's `UserDefaults.standard` writes `~/Library/Preferences/io.github.jasonrandazza.ohyesmlx.plist` (the in-flight job record). Neither is listed, and a user who follows the steps to reclaim disk does not get the pip cache back. The table's third row (`~/Library/Caches/OhYesMLX`) exists only on a machine that built from source.
- Evidence: the pip `command=[…, "--isolated", "--no-input", "--disable-pip-version-check", "--require-hashes", "--only-binary", ":all:", "--no-deps", "-r", …]`; `defaults: UserDefaults = .standard`.
- Confidence: 80 (pip's default cache location is from pip's documented behaviour, not observed on the test account).
- Fix direction: add `--no-cache-dir` to the one pip argv (hash-checked wheels are fetched once per install anyway) and add the Preferences plist to the doc's table and steps.
- Test idea: extend the existing pip-argv test to require `--no-cache-dir`.


=== FINDING-ID: S6-F11 ===
### F11 — P5-4 reports a network outage as a packaging failure and cannot tell it from a TLS failure
- Severity: Low
- Where: scripts/check_bundle.sh:105-133
- Failure scenario: any `URLError` — DNS down, Hugging Face incident, an offline build machine — fails P5-4 with "the HTTPS GET failed", the same line a missing trust store would print, and the script exits 1. A release gate that goes red for the internet teaches people to rerun it until it is green, and a real certificate-verification regression then reads as "flaky network". The two assertions that are the actual property (`CERT_REQUIRED`, `check_hostname`) run only after the GET succeeds.
- Evidence: the heredoc asserts `verify_mode`/`check_hostname` after `urlopen(…)`; a raised `URLError` skips them and the shell prints `fail P5-4 "the HTTPS GET failed (see above)"`.
- Confidence: 85.
- Fix direction: assert the context properties and `ssl.get_default_verify_paths()` resolving to an existing CA file before any network call; catch `URLError` and print `FAIL P5-4 (certificate)` only when its reason is `ssl.SSLCertVerificationError`, otherwise `FAIL P5-4 (network unreachable; rerun)`.
- Test idea: run the P5-4 block with networking off; today the output does not say which of the two failed.

---

