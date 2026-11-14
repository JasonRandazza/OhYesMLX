---
phase: 05-app
plan: 06
subsystem: packaging
tags: [app-bundle, python-build-standalone, codesign, sbom, gatekeeper]
requires: [{phase: 05-05, provides: complete app}]
provides: ["scripts/build_app.sh -> dist/OhYesMLX.app + zip + SBOM", "scripts/check_bundle.sh (P5-3/4/6/9)", "scripts/fetch_python_standalone.sh (pinned 3.14.10+20261026)", "docs/release/gatekeeper.md", "translocation guard"]
completed: 2026-11-14 (AC-6 pending Jason's sudoers step)
description: "T5.6: ad-hoc-signed OhYesMLX.app zip with a bundled CPython 3.14.10; every packaging rule checked on the shipped interpreter"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 06: Packaging — Summary

**`scripts/build_app.sh` produces `dist/OhYesMLX.app` (77 MB), `OhYesMLX-0.3.0.zip` (38 MB) and a 178 KB SBOM;
`scripts/check_bundle.sh` passes 9/9 on that bundle; `codesign --verify --deep --strict` passes before and after a
run from a read-only image.**

| AC | Result | Evidence |
|---|---|---|
| AC-1 pinned interpreter | PASS | sha256 `30a18bcb…5183a4` verified before unpack; wrong-pin red-check exits 1 |
| AC-2 bundle | PASS | plist `io.github.jasonrandazza.ohyesmlx` 0.3.0 (from `ohyesmlx.__version__`), inside-out ad-hoc signing, argv `-I -B` |
| AC-3 SBOM | PASS | interpreter, ohyesmlx commit + source sha256 (`measure._source_sha256`), Swift 6.4, 105 pinned packages; `--check` ok |
| AC-4 P5 checks | PASS (coordinator) | P5-3, P5-4 (huggingface 200, CERT_REQUIRED, system `/etc/ssl/cert.pem`), P5-6 (read-only UDRO image: backend up, `/hardware` served, signature intact), P5-9 (launchd PATH, no PYTHON*) |
| AC-5 Gatekeeper doc | PASS | Open Anyway flow, SBOM + sha256, what is written and how to remove it, notarization gated |
| AC-7 translocation | PASS | `testATranslocatedBundleAsksForApplicationsAndStartsNoJob`; doc says move to Applications first |
| P5-5 / P5-7 (extra) | PASS on this account | App Support `drwx------`; a second `open -n` focuses the first (1 app, 1 backend) |
| AC-6 clean-account smoke | **PENDING** | needs `/etc/sudoers.d/oymlxtest` re-added by Jason |

## Coordinator findings fixed during verification
1. **The signed bundle was being written to at runtime.** `-B` covered the backend only; its child interpreters (and
   any engine venv made from this interpreter, which shares the bundle's stdlib) wrote `email/__pycache__` etc. into
   the bundle, breaking the seal. Fix: the whole bundled tree is precompiled with `--invalidation-mode unchecked-hash`.
2. `check_bundle.sh` defects: `/var` vs `/private/var` in `mount` and argv matching; `lsof -p … -iTCP` without `-a`
   (ORed, read another process's port); its own Python steps now pass `-B`.

## Deviations
- The worker added `-B` to the SBOM step after its own verify caught a post-signing `.pyc` (same root cause as #1).
- Version is 0.3.0 because the plist reads `ohyesmlx.__version__` (one definition); bumping for v5.0 is Jason's call.
- Nothing published: no GitHub Release, no notarization (D7; outward-facing, Jason's call).

## Clean-account smoke (AC-6) — to run after Jason's step
Rule (045-03-SUMMARY Deviations 5): `jrazz ALL=(oymlxtest) NOPASSWD: ALL` in `/etc/sudoers.d/oymlxtest`; remove after.
