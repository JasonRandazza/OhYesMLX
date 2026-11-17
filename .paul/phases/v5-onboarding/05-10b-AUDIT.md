# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/05-10b-PLAN.md
**Audited:** 2026-11-17
**Verdict:** conditionally acceptable (upgrades applied)

---

## 1. Executive Verdict

Conditionally acceptable. The plan correctly moves the resident decision from "a listener on one of six ports" to
"an engine process", but as written its fallback **failed open**: any default-port holder the signature table did not
recognise was treated as harmless and the engine was moved beside it. The signature table cannot be complete (the
argv of app-launched servers is not yet established, and LM Studio / llama.cpp / Ollama are not engines here but do
hold weights). Before this plan, the accidental protection was that every default-port holder blocked a start. Moving
engines without a fail-closed holder test would trade a false refusal for a void run, which is the worse failure under
AGENTS.md's one-model rule. With M1–M3 applied I would approve it.

## 2. What Is Solid

- Default ports and every argv stay byte-identical when the default is free; the change is invisible on a clean Mac.
- Osaurus never moves: its port also lives in a host config file the harness does not edit, and the plan states the
  unknown ("whether `serve --port` rewrites it is not established") rather than claiming an incapability.
- `dataclasses.replace(self, port=chosen)` makes one value flow to argv, probe, `_serving_pid`, ledger and stop.
- The stop command stays derived from `RUNTIMES`, never from disk (S5-F13 preserved), with a port fallback for old
  ledger entries.
- Scope: no new flag, setting, module or subcommand; ROADMAP step 3 explicitly out.

## 3. Enterprise Gaps Identified

1. Fallback fails open for an unrecognised engine or model server on a default port (void run, silently).
2. Matching robustness: lab venvs live under `~/Library/Application Support/` (a space in the path), console scripts
   show as `<python> <path>/optiq serve`, and a naive whitespace split or substring match either misses engines or
   matches `grep mlx_lm.server`; `ps` width was unpinned.
3. The live checkpoint named `scripts/run_canary.sh`, whose `sweep()` kill -9s whatever holds 8081 — it would kill the
   test listener and the check would pass without exercising the fallback.
4. Two port decisions (start vs quickbench skip) could disagree: quickbench says go, start refuses.
5. The runner scripts' default-port sweeps neither see an engine on a fallback port nor spare a user's dev server on a
   default port; undocumented.
6. Post-incident reconstruction: the fallback line should name the holder's executable, not just its pid.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Fallback fails open for an unrecognised holder | AC-3b (new), Task 2 action + tests, verification | Holder is resident if its executable is under a known engine root or `/v1/models` answers 200 + `data` list or 401/403; only otherwise does the engine move; timeout residual recorded |
| 2 | Signature matching fragile (spaces, console scripts, grep lines, ps width) | Task 1 actions 1–2 | `ps -ww` comm + args joined by pid; executable-path match first, token-anchored regexes on args; never split argv; tests for a spaced lab path and a grep line |
| 3 | Live checkpoint would kill its own test listener | checkpoint how-to-verify | Run `ohyesmlx canary --engines mlxlm` directly via the test venv; check the http.server survives |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Two port decisions could disagree | Task 1 step 4, Task 2 step 2, verification | One `port_plan(runtime)` asked by `Runtime.start` and quickbench, seams kept injectable |
| 2 | Fallback line lacks holder identity | Task 2 tests | stderr line names the holder's executable as well as pid |
| 3 | Probe/lsof failure semantics underspecified | AC-3b | Unreadable lsof refuses (unchanged); probe timeout/refusal = not a model server, recorded as residual |
| 4 | Runner scripts' port sweeps undocumented | boundaries, Task 3 | Scripts unchanged, AGENTS.md Ports line states what they sweep and that fallback engines are the harness's to stop |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Rewrite the ~20 runner scripts' `sweep()` to use the process scan | Pre-existing behaviour, outside ROADMAP scope; documented by S4 |
| 2 | Bind-close-spawn race on the chosen port | Readiness and `_serving_pid` already catch a stolen port; marked `# ponytail:` |
| 3 | Another user's engine whose ports lsof cannot read | Still refused (port "unknown"); fails in the safe direction |
| 4 | A non-MLX model server on a non-default port stays invisible | True today as well; detecting arbitrary model servers by process is a new surface |

## 5. Audit & Compliance Readiness

- Evidence: `port` on every row plus one stderr line per move (default, holder pid + executable, chosen port) lets a
  reviewer reconstruct why a cell served where it did.
- Silent failure: M1 closes the one path by which this plan could produce a void run that looks healthy.
- Ownership: the decision lives in one function; refusals name engine, pid and port.

## 6. Final Release Bar

Must be true: AC-1..AC-7 and AC-3b green with red-first tests; argv byte-identical on free defaults; one `port_plan`;
the live checkpoint run with the CLI directly (or recorded pending Jason's "when"). Remaining risk if shipped: an
engine mid-load whose argv and executable are both unrecognised, on a default port, could be moved beside — narrow,
recorded. I would sign it with M1–M3 in.

---

**Summary:** Applied 3 must-have + 4 strongly-recommended upgrades. Deferred 4 items.
**Plan status:** Updated and ready for APPLY

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
