# UAT: Phase 5 (SwiftUI app and packaging)

**Tested:** 2026-11-18 and 2026-11-19, on macOS 27.2.1, M2 Max, 64 GB.
**Build:** `dist/OhYesMLX-0.3.0.dmg` (05-14) for the final round. The quarantine round used the 05-13 zip.
**Tester:** Jason, using the installed app by hand. The coordinator ran the automated gates and recorded the results.

## Results

| # | Check | Result |
|---|---|---|
| 1 | Quarantined download: the zip carried the Safari quarantine flag and was unpacked by Archive Utility | Pass, with an Issue (UAT-002). macOS blocks the app with "Move to Trash / Done" first, and the doc had the steps in the wrong order. Fixed in 05-14. |
| 2 | Open Anyway, then the in-app move screen appears when opening from Downloads | Pass |
| 3 | Install by dragging from the DMG to Applications (05-14) | Pass |
| 4 | Your Mac shows this Mac's chip and memory, so `/hardware` was served from the bundle | Pass |
| 5 | Models: download a model, pause it, resume immediately from the partial, remove it | Pass. The wording issue (UAT-003, "Cancel" → "Pause") was fixed in 05-14. |
| 6 | Models: the Free disk bar fills to show used/total and shows the space a download still needs | Pass after 05-14. UAT-004: the bar was always empty before 05-14. |
| 7 | Benchmark: Stop now during a quick benchmark ends the run as stopped | Pass |
| 8 | Clean-account smoke against the bundle, run as `oymlxtest` (automated) | Pass, 21/21. Jason's account was verified unchanged. |
| 9 | `check_bundle.sh` on the release build (automated) | Pass, all checks |

## Not exercised in this UAT (carried to the open list)

- Installing an engine from the Engines screen. The installer is covered by tests and by the 045-03 clean-account smoke, but not by a live UI run this round.
- Results → Export, and a full quick benchmark finishing through stage B in the UI. Stage B ran end to end in the clean-account smoke (API), not in the UI.
- The "Couldn't start" → Relaunch path, and "Check again" on Engines.

## Issues

| ID | Issue | Status |
|---|---|---|
| UAT-002 | gatekeeper.md described the move screen before approval; macOS blocks before any code runs | Fixed in 05-14 |
| UAT-003 | The download control read "Cancel" but keeps the partial | Fixed in 05-14 ("Pause") |
| UAT-004 | The Free disk bar was always empty: it was filled by a download's share of free space | Fixed in 05-14 (used/total, with `disk_total_bytes`) |
| UAT-005 | No drag-to-Applications installer | Fixed in 05-14 (DMG replaces the zip, Jason's call) |
