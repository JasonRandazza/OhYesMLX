GOAL: add the two reruns Jason asked for to docs/research/2026-09-16-prompt-length-sweep.md.
FILES YOU MAY EDIT: that doc only. Read-only elsewhere. No git, no pytest, no servers.

Jason's decisions (record them): vMLX 32k is published as FAIL; it was rerun as a separate test.
Osaurus 128 was rerun because the sweep cell measured 4 of 9 (root cause, from
.paul/orders/short-measured.log: visit 1's runtime.start() raised, visit 2 measured its quota,
_set_status erased the failure; a code fix is in progress).

INPUTS:
- results/rerun-vmlx-32k/ (run dir, log-vmlx-32768.log) and the vMLX server log
  results/logs/vmlx-20260916T210611-40527.log. Coordinator saw: 35/40 warmups and 8/9 measured
  failed; first two warmups succeeded; errors are `[METAL] Command buffer execution failed:
  Impacting Interactivity (kIOGPUCommandBufferCallbackErrorImpactingInteractivity)` during
  prefill — the macOS GPU watchdog. Also grep the sweep's own vMLX 32k server log for the same
  error. Verify all counts. Do not claim why other runtimes avoid it unless their logs/source
  show it; say it is unverified otherwise.
- results/rerun-osaurus-128/: Osaurus 0.25.5 (sweep was 0.25.4), caches off, and
  server.json modelIdleResidencyPolicy.seconds set to 900 for the run (0.25.5's update set it to
  30, which would unload the model inside the 30 s cooldown); restored byte-exact after.
  Coordinator saw 23 warmups, 9 measured, 0 failed, TTFT p50 0.640 s vs sweep 0.592 s (n=4).
  Verify. It cannot join the sweep table (guard 4: one version per runtime) — say so.

Add one section "Reruns" before "Open questions", update "Open questions" (vMLX: whether a
prefill chunk-size setting avoids the watchdog is Jason's call), and fix anything earlier in the
doc these results contradict. Report what changed.
