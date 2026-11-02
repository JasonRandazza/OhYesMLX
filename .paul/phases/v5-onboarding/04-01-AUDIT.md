# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/04-01-PLAN.md
**Audited:** 2026-11-02
**Verdict:** conditionally acceptable (acceptable for APPLY with the upgrades below applied)

---

## 1. Executive Verdict

Conditionally acceptable. The plan puts the right control in the right place: a per-launch secret checked before
routing, on a loopback-only server, landing before any endpoint that changes the machine. As written it left
the failure behaviour of the guard itself underspecified: a missing `Host`, a non-ASCII `Authorization` value
(which makes `hmac.compare_digest` on `str` raise `TypeError`, a 500 instead of a 401), and a bind failure the
Swift app could not tell from a hang. It also left the stdlib server's defaults unexamined (unbounded slow
connections, keep-alive, caching) and produced no trace of a refused request. With the must-have upgrades applied
I would approve it; this is a read-only surface, and the residual risks are owned by Phase 4.5.

## 2. What Is Solid

- **Guard before routing, in a fixed order, with a test that a refused request runs no scan.** That makes the
  control testable as a property of the server, not of each handler.
- **Composition only.** The server holds no fit rule, version logic or reason text; one definition of each stays in
  its module. A shape mismatch is a BLOCKED finding, not a module edit.
- **No CORS at all.** The app is not a browser, so there is no allow-list to get wrong.
- **Loopback bind and an ephemeral port, the token printed once on stdout, never on disk.** The Swift app spawns the
  process and holds the pipe, so the secret never touches the filesystem or argv.
- **Parent death via stdin EOF.** No orphaned server holding a port after the app quits.
- **Real server, real sockets in tests** (S6), not handler unit tests.

## 3. Enterprise Gaps Identified

1. Absent `Host` header (HTTP/1.0 clients) was not specified; a loose check could pass it.
2. `hmac.compare_digest` raises `TypeError` on non-ASCII `str`: an attacker-controlled header could turn the guard
   into a 500, and a 500 path is where messages and tracebacks leak.
3. Responses could echo request data (error messages built from headers), including the token.
4. The plan implied Origin and Host were the defence; for a cross-site GET by navigation or `<img>` there is no
   `Origin` and the `Host` is correct. Only the token stops it, and no test proved that.
5. Bind failure on `--port N` had no defined behaviour; the app would wait on a line that never comes.
6. `ThreadingHTTPServer` defaults: no socket timeout (a slow or idle client holds a thread forever), non-daemon
   threads (shutdown can hang), and keep-alive if the protocol were bumped to 1.1.
7. No `Cache-Control`: a browser or proxy could cache a JSON body describing the machine.
8. No audit trail: a probe from a web page leaves nothing behind, so an incident cannot be reconstructed.
9. `ohyesmlx app </dev/null` exits immediately (stdin EOF), which will look like a crash to a CLI user.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Absent Host passes a loose check | AC-2, Task 1 action | Exact Host strings only; absent Host is `bad_host`; test added |
| 2 | Non-ASCII token raises in `compare_digest` | AC-2, Task 1 action | Compare UTF-8 bytes inside the guard; `Bearer é` test expects 401 |
| 3 | Responses may echo the token or headers | AC-2, Task 1 action | Fixed error strings per code; a test asserts no body contains the token |
| 4 | Bind failure undefined | AC-1, Task 2 action | Nothing on stdout, one stderr error line, exit 2; occupied-port test |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Token is the primary control, untested as such | AC-2, Task 1 tests | No-Origin, right-Host, no-token GET must be 401; a real-browser check in verification |
| 2 | Unbounded slow connections, hanging shutdown | new AC-8, Task 1 action | 10 s handler timeout, daemon threads, HTTP/1.0 one-request-per-connection; idle-socket test |
| 3 | No trace of refusals | new AC-8, Task 1 action | One stderr JSON line per refusal (code, method, path, time; no header values); served requests silent |
| 4 | Cacheable machine description | AC-6 | `Cache-Control: no-store` on every response |
| 5 | Surprising exit under `</dev/null` | Task 2 action | Documented in docs/interfaces.md as by design |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | The token travels over stdout; the Swift app must not log it | Phase 5 owns the client; Phase 4.5's checklist carries it as a packaging requirement |
| 2 | Rate limiting / lockout on repeated 401s | Loopback only, 256-bit token; brute force is not feasible, and refusals are now logged |
| 3 | A persistent access-log file under Application Support | stderr refusal lines reach the parent app; a file is a Phase 4.5 decision with the rest of the on-disk surface |
| 4 | TLS on loopback | No network path to protect; the threat is other local pages and processes, which the token covers |

## 5. Audit & Compliance Readiness

- **Evidence:** every guard has a red-checked test, and the manual checks (curl with and without token, Origin, a
  real browser, `lsof`) are written into verification for the coordinator to run and paste.
- **Silent failures:** bind failure, `install_plan` ValueError and module exceptions now all have defined, loud
  outcomes with pinned codes.
- **Reconstruction:** refusals leave a structured stderr line; served reads leave none (they change nothing).
- **Ownership:** the coordinator verifies; Jason approves at the human-verify checkpoint.

## 6. Final Release Bar

Before this plan ships: AC-1..AC-8 green with every guard red-checked by removing it, the curl and browser checks
run on this Mac, and the server bound to 127.0.0.1 only. Remaining risk if shipped: any local process that can read
the app's stdout pipe or memory can obtain the token. That is inside the user's own account, the same boundary as
their files, and Phase 4.5 reviews it. I would sign this for a read-only API.

---

**Summary:** Applied 4 must-have + 5 strongly-recommended upgrades. Deferred 4 items.
**Plan status:** Updated and ready for APPLY

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
