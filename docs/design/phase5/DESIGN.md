---
description: "OhYesMLX app (v5.0 Phase 5) — design direction, SwiftUI token mapping, and the fixes the comps need before they become screens"
type: Design
about: "OhYesMLX"
---

# OhYesMLX app — design direction (plan 05-03, 2026-11-13)

The comps are in `comps.html` (open it in a browser). Open Design generated them on 2026-11-13 with its
`frontend-design` and `apple-hig` skills (project `ohyesmlx-phase-5-app-397c`, run `547de4b9`), from a brief
that carried this Mac's real backend data. The coordinator then reviewed them with the `impeccable` critique
pass. `results-light-dark.png` is a capture of the Results frames.

This file is the design authority for plans 05-04 and 05-05. Where a comp disagrees with this file, this file
wins. Where either disagrees with `docs/interfaces/v5-app.md` (behaviour) or the backend shapes, those win:
the design never invents a capability or a number.

## 1. Direction

**An honest instrument, native to the Mac.** The audience owns a Mac and has never opened Terminal. The
app should look like something Apple could have shipped in System Settings, with one thing it says more
plainly than any other tool: what was *estimated* and what was *measured on your Mac*. Expression lives in
precise details, not decoration: tabular figures, the two labels, the consent sheet that lists exactly what
will run, and a sidebar that ticks off each step as it completes.

The register is **Operate**: the user is finishing a task. Scannability, native affordances and reassurance at
the risky moments (install, pin Osaurus, stop a run) outrank expression.

## 2. Structure (as comped)

- One `Window` scene, about 1100×720 and resizable, with a `NavigationSplitView`. The sidebar section is
  "Setup", holding **Your Mac, Engines, Models, Benchmark, Results**. A completed step shows a trailing
  `checkmark.circle` in `.secondary`. A step that cannot be reached yet stays visible and is disabled, not
  hidden. The sidebar footer reads "Nothing changes on this Mac without a click."
- The detail toolbar shows a title, a subtitle ("Step 2 of 5"), and the screen's own trailing actions:
  Scan Again, Check Again, Stop After This Cell / Stop Now, Export Results….
- Content is a single column with readable width capped at about 680 pt. Lists are inset, grouped
  `List`/`Form` sections, never a grid of cards.
- The full-window states (Launching, Couldn't start, Unsupported, The backend stopped) have no sidebar. Each
  is a centred SF Symbol, a title, one or two lines of body, and one prominent action.
- The interrupted-job banner (Q2) is a thin bar pinned above the detail content, in `.background(.yellow.opacity(0.12))`
  or the system's warning material. It holds one sentence and two buttons, **Retry** and **Dismiss**.

## 3. Tokens → SwiftUI

The comps define every token as a CSS custom property with its SwiftUI counterpart in a comment. The
SwiftUI side is almost entirely system semantics, which is the point: light and dark, Increase Contrast,
and the user's accent colour all come for free. **Do not hard-code the hex values in Swift.**

| Role | Comp token | SwiftUI |
|---|---|---|
| Accent | `--color-accent` | `Color.accentColor` (follows System Settings) |
| Window / control / sidebar backgrounds | `--color-window-background` etc. | the defaults of `NavigationSplitView`, `List(.inset)`, `Form(.grouped)`; no explicit backgrounds |
| Label / secondary / tertiary | `--color-label`… | `.primary`, `.secondary`, `.tertiary` foreground styles |
| Separator | `--color-separator` | `Divider()` |
| Status: pass / installed-tested | `--color-green` | `Color.green` on a **glyph only** (`circle.fill`, 8 pt), never on text |
| Status: tight / untested / warning | `--color-orange` | `Color.orange`, glyph only |
| Status: fail / refusal | `--color-red` | `Color.red`, glyph only |
| Type scale | `--text-title2`, `--text-body`, `--text-callout`, `--text-caption`… | `.font(.title2)`, `.body`, `.callout`, `.caption`; no custom sizes |
| Figures (tok/s, GB, versions, seconds) | `--font-mono` | `.monospacedDigit()` on the **system** font. Never SF Mono for numbers, because the comps' `64  GB` double gap is a mono-font artefact. SF Mono (`.monospaced()`) only for commands in the consent sheet and stderr lines |
| Spacing | `--space-1..10` (4-pt grid) | `.padding(4/8/12/16/20/24/32/40)`; prefer the defaults of `Form`/`List` |
| Radii | `--radius-control/group/sheet` | none: system controls and `GroupBox` draw their own |
| Sidebar width | `--size-sidebar` 220 | `.navigationSplitViewColumnWidth(min: 200, ideal: 220)` |
| Meter | `--size-meter` | `ProgressView(value:)` (download), `Gauge` or a linear `ProgressView` for disk |

Badges ("estimated", "quick: measured on this Mac", "untested build", "Start here") are one small
component. Use `.font(.caption)`, `.foregroundStyle(.secondary)`, and a 1-pt `.secondary` hairline
`RoundedRectangle`, with no fill. The label carries the meaning, so colour is never the only signal.

## 4. Fixes the comps need (critique, ordered by severity)

These come from the coordinator's `impeccable` critique: an Assessment A design review, plus the bundled
detector as Assessment B. The run was degraded to a single context, because this project routes delegated
work to Command Code rather than native subagents. The detector is tuned for the web: its 11 "cramped
padding" and 6 "undersized text" findings mostly flag macOS's own 13-pt body and 11-pt callout, which are
correct on a Mac and are not carried here. Its contrast findings are real (item 2).

1. **Do not claim an uninstall.** The consent sheet's "Undo: Remove it from Engines at any time" describes a
   capability the backend does not have. Drop the row. The sheet lists `Plan.steps` (label, and command in
   SF Mono when present), `size_bytes_estimate`, and `needs_admin`, and nothing else. The comp's
   `pip install "mlx-optiq==0.5.13"` line is invented; the real steps come from the plan data
   (hash-pinned requirements, `-I`, `--isolated`).
2. **The dark Results table fails contrast.** Rows render dark text on dark fill. In SwiftUI, use the
   semantic `.primary`/`.secondary` styles and the `Table`/`List` defaults; never set a row text colour.
   Check in dark mode, and with Increase Contrast on.
3. **The status pills for SKIPPED and "Stopped by you" render as empty ovals.** Every status is a glyph plus
   a word: PASS `circle.fill` green, FAIL `xmark.circle.fill` red, SKIPPED `minus.circle` secondary,
   Stopped by you `stop.circle` secondary. The note column carries the reason.
4. **The models are fiction.** The Models comp shows 9B–70B models. The real catalog is the 12 rows
   `GET /recommendations` returns (0.6B–8.5B on this Mac), so build against the fixture, not the comp. Keep
   the comp's row anatomy: Start here badge, title, format, fit glyph and word with an `estimated` badge,
   the reason line, and one trailing action.
5. **Spacing between number and unit.** Figures render as `62.1 tok/s` and `40.4 GB` with one space, and the
   number and its unit are never split across lines (`.fixedSize()` on the figure group).
6. **Disabled actions need their reason next to them, not elsewhere (Q1).** The comp's busy Engines row is
   right: the trailing "Busy: download Qwen3.5 2B is running" sits beside a disabled Install…. Keep that
   pattern on every job-starting control, and expose the reason as the control's accessibility hint.
7. **Stop controls (Q3).** Keep both toolbar buttons with their glyphs (`pause.circle` "Stop After This
   Cell", `stop.circle` "Stop Now"), plus the comp's one-line explainer under the progress. Once one is
   pressed, both disable and the state line reads "Stopping after this cell…" or "Stopping…".
8. **The low-disk refusal (Q4)** stays inline under its model row with `exclamationmark.triangle` orange, as
   comped. Its amount is `needed_bytes − free_bytes` from the refusal payload (v5-app.md), formatted one
   decimal GB.

## 5. Accessibility floor

- Every glyph that carries status has a text label beside it. VoiceOver reads the row as one element:
  "OptiQ 0.5.13, installed, tested".
- All actions are reachable by keyboard. Return triggers the sheet's default button (Install, Start
  Benchmark) and Escape cancels.
- Dynamic Type is not a macOS concern, but the window must lay out at its minimum size (900×600) without
  truncating a figure.
- Increase Contrast and Reduce Transparency: system materials only, so these are handled by construction.

## 6. What this file does not decide

Behaviour (`docs/interfaces/v5-app.md`), copy for refusals (the backend's own `message`, shown as written),
and every number (the backend's). A screen that needs a new string writes it plainly in the voice of
§1. Hype words such as "blazing", "supercharge" and "magic" are banned.
