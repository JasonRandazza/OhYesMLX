---
description: "05-03 design direction: Open Design comps (frontend-design + apple-hig) reviewed with impeccable; DESIGN.md is the authority for 05-04/05-05"
type: Summary
about: "OhYesMLX"
---

# 05-03 — Design direction (coordinator)

**Output:** `docs/design/phase5/DESIGN.md` (direction, SwiftUI token mapping, 8 ordered fixes, a11y floor),
`docs/design/phase5/comps.html` (15 frames: launch, couldn't start, unsupported, Your Mac, Engines ×3,
Models, Benchmark plan + running, Results light + dark, banner), `results-light-dark.png`.

**How:** Open Design 0.26.1, project `ohyesmlx-phase-5-app-397c`, skill `frontend-design` + `apple-hig`, brief
built from the live backend fixtures. Critique: `impeccable` (single-context, degraded by design: delegation
goes to Command Code, not native subagents) + its detector (25 web-tuned findings; contrast real, padding/size
mostly macOS-correct and not carried).

**Deviations:**
- Open Design's MCP is registered for Codex only, and that registration pointed at the 0.24.1 payload after the
  app self-updated to 0.26.1; two runs died with "daemon restarted". Fixed for this session by running a
  headless 0.26.1 daemon on 127.0.0.1:17456 and a stdio shim (`od mcp --daemon-url`) in the scratchpad. Jason:
  open Open Design once and refresh its MCP registration (and add it for Claude Code if wanted).
- The comps invent models (9B–70B) and an uninstall; DESIGN.md §4 overrides both.

**Next:** 05-04 / 05-05 build the screens to DESIGN.md on 05-02's AppModel.
