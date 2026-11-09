---
phase: 045-security
plan: 02a
type: Summary
about: "OhYesMLX"
status: applied
commits: [4b35ef8, 9bc9388]
tests: "1164 -> 1211 passed"
---

# 045-02a SUMMARY: server and lifecycle security fixes

APPLY of `045-02a-PLAN.md` (audited 2026-11-03). Executed 2026-11-04 to 2026-11-09 by the Claude Opus 5.5
coordinator, with three Command Code `implement` dispatches (DeepSeek v4.1 flash). Eight findings from the 045-01
threat model are fixed: T-02, T-03, T-04 and T-05 (medium), and T-08, T-09, T-10 and T-11 (low). T-01 and T-06 are
still withheld for 045-02b.

## Commits

| Commit | Contents |
|---|---|
| `4b35ef8` | Part A (AC-1 to AC-5): writable root, job-slot leak, thread and stream caps, absolute tool paths, `0700` Application Support, refusal log limited to served routes. Threat model: T-03 and T-04 detail published; T-03, T-04 and T-08 to T-11 marked fixed; §9 row added for the thread cap's residual risk. |
| `9bc9388` | Part B (AC-6, AC-7): interrupted-app recovery (Osaurus pin, orphaned engines, pip process groups) and a mid-cell Osaurus drift check. Threat model: T-02 and T-05 detail published and marked fixed; the part A rows carry `4b35ef8`. |

Each commit carries its work orders and worker logs (`.paul/orders/v5-fix-45a-{server-paths,lifecycle,drift}.{md,log}`).
Both commits were scanned for token-shaped strings first.

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-1 One writable root (T-03, T-10) | PASS | `ohyesmlx.app_support_dir`, `writable_root` and `ensure_app_support` are each defined once in `__init__.py`. `BASELINE_PATH` and `LOGS_DIR` are byte-identical before and after in this checkout (printed to `/tmp/oymlx-045-02a-paths-{before,after}.txt`; `diff` empty). `tests/test_paths.py` simulates an installed layout: a read-only tree with no `.git` sends a pin round-trip and a spawn log only under a scratch Application Support. The directory is `0700`, new or tightened from `0755`. |
| AC-2 Job slot cannot leak (T-04) | PASS | A raise from `_log_job` or `Thread.start` stores `error internal` + `done` and answers 500, and the next POST is 202. |
| AC-3 Threads and streams bounded (T-08) | PASS | `MAX_HANDLER_THREADS` 32 (semaphore taken in `process_request`, released in `process_request_thread`'s `finally`); `MAX_STREAMS_PER_JOB` 4 (`429 too_many_streams`). Live probe: 50 silent connections peaked at 34 threads (2 + 32), down from 52 in 045-01, and fell back after the 10 s timeout; `/hardware` answered 200 after the flood. |
| AC-4 No raw path in the refusal log (T-11) | PASS | `_served_path` reuses the router's own route set; anything else is `<unknown>`. A test puts the token in a path segment and checks it never reaches stderr. |
| AC-5 Absolute tools, bounded scan (T-09) | PASS | `/bin/ps` (`runtimes.PS`), `/usr/sbin/sysctl` (the existing `sample.SYSCTL`), `/usr/bin/sw_vers`, `/usr/sbin/ioreg`, `/usr/bin/open`. `hardware.TOOL_TIMEOUT_S` 10 s; a hung tool makes `/hardware` a 500. A fake `ps` on PATH is never executed. |
| AC-6 Interrupted app recovered (T-02) | PASS | See the live checks below. The ledger is written after `cold_load_s` (test with a fake clock and fake writer, plus a read of `Runtime.start`). Startup recovery is skipped with `recovery_pending` while the Osaurus app is reported running. pip steps run in their own session; on shutdown expiry the server kills them and waits `JOB_KILL_GRACE_S` 15 s more. No `.incomplete` sweep. |
| AC-7 Mid-cell Osaurus drift (T-05) | PASS (amended) | The drift check is an injectable `run()` keyword. On drift, both configs are copied byte-exact to `<backup_dir>/during-run/` (`0700`) before restore, the cell FAILs with the specified reason, and the summary names the directory. **Amendment:** one existing test was edited (see Deviations). |
| AC-8 Disclosure moves with the fix | PASS | T-03 and T-04 detail moved in `4b35ef8`, T-02 and T-05 in `9bc9388`. The private file now holds only T-01 and T-06 and is still gitignored. Since a commit cannot name its own hash, part A's rows read "part A" until `9bc9388` replaced that with `4b35ef8`; part B's rows read "part B". |

## Red-checks (coordinator, reverted and restored)

Part A: slot release (AC-2, 2 failed); semaphore (AC-3, 1 failed); stream cap (AC-3, 1 failed); route filter (AC-4,
1 failed); `PS = "ps"` (AC-5, 1 failed); `hardware._run` timeout removed (AC-5, 1 failed); `chmod` removed (AC-1, 1
failed); `ensure_app_support` call removed from `_app` (AC-1, 1 failed); `writable_root` always the repo (AC-1, 1
failed).

Part B: drift call removed (AC-7, 2 failed); identity match disabled (AC-6, 2 failed); live-owner skip removed (AC-6,
1 failed); `kill_running_steps` removed from `cancel_and_wait` (AC-6, 2 failed); pip `start_new_session` removed
(AC-6, 1 failed); app-running guard on recovery removed (AC-6, 1 failed). The worker also red-checked moving the
ledger write before the `cold_load_s` timestamp (the test failed).

## Live checks (scratch HOME, no measurement running)

**(a) Osaurus recovery at startup.** The package was copied outside the checkout, so `writable_root()` resolves to
the scratch Application Support and the repo's `config/` cannot be touched. The setup was a scratch backup (both
configs plus `baseline.absent`), a pinned scratch `~/.osaurus/config` and a pinned baseline. Then `ohyesmlx app`
was run, with the real Osaurus app not running:

```
stdout launch keys: ['port', 'token']
exit 0
stderr:
{"action": "recover", ... "outcome": "restored byte-exact"}
{"recovered": "osaurus", "backup_dir": ".../OhYesMLX/quickbench/osaurus-backup"}
runtime-byte-exact            (cmp against the original server-runtime.json)
```

The pinned baseline was deleted (the `baseline.absent` marker), the backup directory was removed, Application
Support went to `drwx------`, and `git status config/` in the repo was empty.

**(b) Orphan stop.** Two `/bin/sleep` processes were started in their own sessions. They were recorded under a dead
owner pid in `<scratch>/results/running-engines/`: one with its real `ps` start time, one with a wrong start time.
A second ledger file was written under the live probe process's pid. Then
`runtimes.stop_orphaned_engines(root=scratch)` was called:

```
before: ['89216.json', '89222.json']
after: ['89216.json']                     (dead owner's file removed; live owner's kept)
a (matching entry) exit: 0 | b (wrong lstart) alive: True
live-owner file untouched: True
b killed by hand
```

**Probe re-run (Task 3).** The 045-01 probe script had been cleared from `/tmp`, so it was rebuilt from
threat-model §6 at `scratchpad/probe-tools/probe.py` (session scratchpad, not committed). Run against a scratch-HOME
`ohyesmlx app`: **32/32 PASS**. Every 045-01 result held: auth, Host and Origin refusals, 415/413, the 10 s
short-body close, `bad_kind`/`bad_args`, `bad_name`/`ledger_unreadable`/`unknown_repo` on the job stream, 404s,
the plan `bad_args`, one IPv4 loopback listener, exit 0 on stdin EOF, no token on stderr, and the port free
afterwards. The thread peak was 34 (bounded). The real-state digest (`ls -laR` of real Application Support, the HF
cache, `~/.osaurus/config` and the repo `config/`, piped to `shasum`) was `9f4af8f1edce8154` before and after.

## Deviations

1. **AC-7: one existing test edited** (Jason, 2026-11-09; STATE Decisions). The worker reported BLOCKED: the plan
   asked for both "live config vs pinned baseline" and "existing quickbench tests unmodified".
   `test_the_host_pinned_between_pin_and_restore_shows_no_drift` pins a tmp config dir through injected lambdas,
   while a default check reads the real `~/.osaurus`. On this host that is 22 drifted keys, a FAIL, and a test
   reading real settings. Resolution: the check (`osaurus_drift`) and the copy (`keep_during_run`) are injectable,
   and that one test binds both to its tmp dir. The edit only adds lines.
2. **Recovery writes two stderr lines, not one.** `osaurus_settings.recover` always writes its own action line, and
   `_app` adds `{"recovered": ...}`. The app's own line is the one the AC defines; the action line was there
   before this plan.
3. **`sysctl` was not given a new constant.** `hardware` imports the existing `sample.SYSCTL` rather than spelling
   the path a second time (one definition of everything).
4. **Two dispatches for part B instead of one** (order B, then `v5-fix-45a-drift.md` after the BLOCKED).
5. **045-01 T-02(d) is withdrawn**, as the plan anticipated: `.incomplete` files are fetch's resume state.

## Known gaps and observations (not fixed here)

- **AC-7 runs only when `run_cells` returns.** A cell that raises is already a FAIL, but the drift copy is not
  taken, so a mid-run user edit in that path is still overwritten by restore. Recorded as residual in threat-model
  §7.4 T-05.
- **`during-run/` stays in the backup directory.** It does not block `pin`/`recover` (they check named files
  only), but a later drift overwrites it, and `restore` can no longer `rmdir` the backup directory while it
  exists. Phase 5 copy should tell the user where it is.
- **`runtimes.LSOF` is still `shutil.which("lsof")`** on the ambient PATH at import. T-09 did not list it, so it
  was left alone and noted in §7.4. Candidate for 045-02b.
- **Startup ordering.** `ensure_app_support()` runs before the bind in `_app`, so an unwritable HOME is a traceback,
  not the `bind_failed`-style stderr line. Minor; the Phase 5 app always has a writable HOME.
- **The thread-cap test reads `BoundedSemaphore._value`** (CPython-private) for determinism.

## Not done (out of scope, by plan)

T-01, T-06, T-07, T-12, T-13 and T-16 → 045-02b. T-14 accepted. T-15 → Phase 5 checklist. No install, download,
quickbench or measurement was run live.

## Process gates still owed

- `code-review` (Standards + Spec) on `4b35ef8..9bc9388` before UNIFY (plan success criteria).
- `/paul:verify` at the end of Phase 4.5.
