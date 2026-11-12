---
phase: 045-security
plan: 02b
type: Summary
about: "OhYesMLX"
status: applied (part B uncommitted)
completed: 2026-11-10
duration: "2026-11-10 (APPLY and close-out)"
commits: [a031ad4]
tests: "1222 -> 1272 passed"
---

# 045-02b SUMMARY: installer and fetch security fixes

APPLY of `045-02b-PLAN.md` (audited 2026-11-10). Executed 2026-11-10 by the Claude Opus 5.5
coordinator, with two Command Code `implement` dispatches (DeepSeek v4.1 flash) and one close-out
dispatch. Six findings from the 045-01 threat model are fixed: T-01, T-07 and T-12 (part A, committed),
and T-06, T-13 and T-16 (part B, in the working tree and reviewed, uncommitted at the time of writing).
The private findings file held only T-06 at close-out, moved into the threat model here, and was deleted.

## Commits

| Commit | Contents |
|---|---|
| `a031ad4` | Part A (AC-1, AC-2, AC-3): `constraints/*.txt` became full hashed requirements files produced by `scripts/hash_freeze.py`; the install runs `-I -m pip install --isolated --require-hashes --only-binary :all: -r <file>`; `_check_hashed_requirements` refuses an unhashed pin or an option line as `no_constraints`; `_venv_root` searches the argv; `engines.check_lab_dir` guards both `_engine_env` and `record_lab_path`; `ohyesmlx.atomic_write_text` added. Threat model: T-01, T-07 and T-12 detail published and marked fixed; §9 gains the pygame source-build row. 1261 tests. |
| (uncommitted) | Part B (AC-4, AC-5, AC-6): `evict` takes `download.lock` and refuses `busy`, releasing in a `finally`; `_ledger_save` writes through `atomic_write_text`; quickbench records `not_evicted` and logs one event per refused eviction; `_repo_dir` is the one repo-directory helper used by `plan`, `evict` and the `.incomplete` residue check; `_link_conflicts` runs in the pre-transfer pass and in `link_all`. Threat model: T-06 detail published, T-06/T-13/T-16 rows marked fixed, §9 gains the reclaim-race row, §8's T-16 carried row names part B. 1272 tests. |

Part A's commit carries its order and worker log (`.paul/orders/v5-fix-45b-installers.{md,log}`).
Part B's order and log are `.paul/orders/v5-fix-45b-fetch.{md,log}`; the close-out's are
`.paul/orders/v5-fix-45b-closeout.{md,log}`.

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-1 pip installs only hash-verified files (T-01) | PASS | Both `constraints/*.txt` files are full requirements files: every `name==version` pin carries a sha256 for every file PyPI lists for that version. Pin sets are unchanged (mlxlm 35 pins, 573 `--hash` lines; optiq 71 pins, 1539). `scripts/hash_freeze.py` is stdlib, fetches only `https://pypi.org` with the default SSL context, writes once through `atomic_write_text`, prints yanked pins and `LATE UPLOADS`, and exits non-zero without writing if any pin does not resolve; `tests/test_hash_freeze.py` has 9 tests. The install argv is `<venv>/bin/python -I -m pip install --isolated --no-input --disable-pip-version-check --require-hashes --only-binary :all: -r <constraints_path>`. The validator refuses an unhashed pin or any option line (`--index-url`, `-r`, `-e`, `--trusted-host`, ...) as `no_constraints`, and a test asserts both committed files pass and name the engine's package at its tested version. **Late uploads:** `hash_freeze.py` printed no `LATE UPLOADS` heading and no yanked warning for either file; the worker's spot check of three pins found real upload spans of 0 days, so the empty list is plausible. **Live:** on a scratch HOME with a bogus user `pip.conf`, mlxlm installed from the hashes under CPython 3.13 and 3.14 and optiq under 3.14; with every mlx hash altered, pip refused (`THESE PACKAGES DO NOT MATCH THE HASHES`) and installed nothing; the real Application Support directory was byte-identical before and after. The one named exception is `engines._SOURCE_BUILDS = {"optiq": ("pygame",)}`, below. |
| AC-2 installer ignores the user's Python and pip environment (T-07) | PASS | The venv step is `{python} -I -m venv <root>`; the pip step carries `-I` and `--isolated`. `_venv_root` finds `-m venv` by searching the argv (unit cases with and without `-I`), and a test over the real plan asserts a failed pip step rolls the venv back and a successful one records it in `lab-paths.json`. `_hermetic_env` is unchanged. **Live:** a user `pip.conf` with `index-url = http://127.0.0.1:9/simple` is listed by `pip config list` without `--isolated` and ignored with it, and the install succeeds. |
| AC-3 lab path is a directory this user owns and nobody else can write (T-12) | PASS | `engines.check_lab_dir(path)` requires absolute, a directory following symlinks, owned by `os.geteuid()`, with neither group- nor other-write. `runtimes._engine_env` calls it after `expanduser` and raises `RuntimeStartError`; `record_lab_path` calls it before reading or writing and writes through `ohyesmlx.atomic_write_text`. Read-only on this host, both real lab dirs printed `passes:` (`~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`, `…/engines/optiq-0.5.13/bin`). `detect_all` is unchanged. |
| AC-4 evict runs under the download lock (T-06) | PASS | `evict(..., lock_dir=DEFAULT_LOCK_DIR)` acquires `download.lock` after its consent and name checks and before reading the ledger; a live holder gets `busy` ("a download or eviction is running; nothing was removed"); the lock is released in a `finally`. `_ledger_save` writes through `atomic_write_text`. Tests: a live lock holder is refused with the ledger and every listed file untouched; the lock is released after a normal evict and after one that raises; an autouse fixture fails any fetch test that reaches `DEFAULT_LOCK_DIR`. quickbench records `not_evicted` in the summary and logs one event naming the repo for any refused eviction (sibling and outstanding sweep), with three tests; `docs/interfaces.md` lists `busy` and `not_evicted`. Scratch check A below shows the `busy` event and a byte-identical ledger. The coordinator added `lock_dir` to the one `tests/test_server.py` test that called the real `evict` without it (Deviations 4). |
| AC-5 evict removes only paths inside that repo's own directory (T-13) | PASS (code); the host-ledger clause did not accept | `_repo_dir(root, repo)` is used by `plan` and by `evict`, and the `.incomplete` residue check asks it too. A ledger path resolving in another repo's directory, at the cache root, or outside the cache refuses `ledger_unreadable` before anything is removed; the test is parametrized over those three cases. An entry written by a real `download` still evicts in full (the existing `test_evict_removes_exactly_the_ledger_paths`). Read-only against this host's real `fetched.json`, the per-repo check accepted **0 of 60** paths: that entry is residue from scratch-cache runs that left the ledger at its default path, not an existing real download. The old whole-cache-root check accepted 0 of 60 as well, so part B does not make it newly unevictable. Check B below has the output. |
| AC-6 snapshot conflict is refused before any byte is requested (T-16) | PASS | `_link_conflicts(link, blob)` is the one decision used by the pre-transfer pass and by `link_all`. A snapshot link that exists and does not resolve to its blob (including a regular file in its place) refuses `integrity_failed` naming the path before the first request; a fake opener recorded zero calls, no blob was fetched, and the existing file was not overwritten. The already-present path behaves as before (`test_a_fully_present_model_makes_no_request`). |
| AC-7 disclosure moves with the fix | PASS | Part A moved T-01, T-07 and T-12 in `a031ad4`. This close-out moves T-06 into §7.4 in the T-01 section's shape (what it was, actor, fix, verified), marks the §7.3 T-06/T-13/T-16 rows "Fixed in 045-02b (part B)", appends the fixed bullets to the T-13 and T-16 sections, adds the §9 reclaim-race row, and marks §8's T-16 carried row part B. The private file held only T-06 and is deleted; the three `.gitignore` lines naming it and the two 045-01 review logs are removed; both 045-01 logs were scanned first (step 3 below). A commit cannot name its own hash, so part B's rows say "part B" until the coordinator commits; the SUMMARY names `a031ad4` for part A. |

## Red-checks (reverted, run, restored)

Part A: validator no-op (8 failed: 7 parametrized cases plus the unhashed real file); `--only-binary :all:`
removed (3); `-I` removed from the venv step (3); `_venv_root` back to fixed indices (3); `check_lab_dir`
removed at `record_lab_path` (5); `check_lab_dir` removed at `_engine_env` (5); `atomic_write_text` temp
cleanup removed (1).

Part B: the evict acquire guard reverted (1, the `busy` test); the two quickbench `if not evict(...)`
checks reverted (2, the `refused_*` tests on `not_evicted`); the AC-5 containment reverted to the cache
root (2, `[another_repo]` and `[cache_root]`; `[outside]` stayed caught by the old check, as expected);
`_link_conflicts` removed from the pre-transfer pass (2, both tests recorded one request).

## Live checks

**(a) Part A installs** (coordinator, scratch HOME, no measurement running; from `a031ad4` and threat-model
T-01/T-07):

- mlxlm installed from the hashed file under CPython 3.13 (the test-venv interpreter) and 3.14 (the lab
  venv); optiq installed under 3.14. A bogus user `pip.conf` at both `~/Library/Application Support/pip/pip.conf`
  and `~/.config/pip/pip.conf` was ignored under `--isolated`.
- With every mlx hash altered in a scratch copy of the file, pip refused with
  `THESE PACKAGES DO NOT MATCH THE HASHES` and installed nothing.
- The real Application Support directory was byte-identical before and after (the commit records this; the
  close-out's own checks wrote nothing there).
- `hash_freeze.py` printed no `LATE UPLOADS` for either constraints file, so there was no late-uploaded file
  to judge before trusting the freeze.

**(b) Check A (AC-4), scratch cache.** Command: the test-venv interpreter, `mktemp -d` under the session
scratchpad, a ledger with one repo, `locks/download.lock` holding the pid of a live `sleep 60`, and
`fetch.evict(repo, True, cache_dir=…, ledger_path=…, log_path=…, lock_dir=…, emit=print)`. Output verbatim:

```
{'seq': 1, 'type': 'error', 'message': 'a download or eviction is running; nothing was removed', 'fraction': None, 'payload': {'code': 'busy'}}
{'seq': 2, 'type': 'done', 'message': 'fetch ended', 'fraction': None, 'payload': None}
evict returned False
lock still held by sleep pid 57336
cmp: ledger byte-identical
scratch removed: /private/tmp/commandcode-501/-Users-jrazz-Dev-active-OhYesMLX/78d2f196-a914-4e71-80d1-6355903f089c/scratchpad/checkA.WZYuaA
```

**(c) Check B (AC-5), read-only against the real ledger.** `fetch.default_cache_dir()` is
`/Users/jrazz/.cache/huggingface/hub`; every listed path was checked with
`fetch._inside(path, fetch._repo_dir(root, repo))`. Output verbatim:

```
mlx-community/Qwen3.5-2B-4bit  paths=60  all-inside=False  repo_dir=/Users/jrazz/.cache/huggingface/hub/models--mlx-community--Qwen3.5-2B-4bit
```

All 60 paths live under two `/private/tmp/claude-501/.../scratchpad/{qb-hfcache,hf}` cache roots, from
scratch-cache runs on 2026-11-03 that took a scratch `cache_dir` but the default ledger path. Supporting
comparison (same read, no writes):

```
mlx-community/Qwen3.5-2B-4bit: paths=60 inside-repo=0 inside-old-root=0 still-on-disk=16
ledger mtime: 2026-11-03 12:12:55
```

So the entry was already outside the old whole-cache-root boundary and `evict` already refused it before
part B; the code change did not make an existing real download unevictable. The AC's real-ledger clause
assumed the entry was a real download, and on this checkout it is not.

**(d) Steps 3-5 output, verbatim.**

Token scan (step 3), over the two 045-01 logs, `.paul/orders/v5-fix-45b-fetch.log` and
`.paul/orders/v5-fix-45b-closeout.log`:

```
.paul/orders/v5-fix-45b-fetch.log:75:- Tests: `test_evict_refuses_a_ledger_path_outside_that_repos_own_directory[another_repo|cache_root|outside]`; the real-download entry still evicts in full via the existing `test_evict_removes_exactly_the_ledger_paths`.
.paul/orders/v5-fix-45b-fetch.log:80:- Tests: `test_a_snapshot_link_pointing_elsewhere_is_refused_before_any_request`, `test_a_regular_file_where_the_snapshot_link_belongs_is_refused_before_any_request`; the already-present path is the unchanged `test_a_fully_present_model_makes_no_request`.
EXIT=0
```

Both hits are Python test names of exactly 43 characters — `test_evict_removes_exactly_the_ledger_paths`
and `test_a_fully_present_model_makes_no_request` — not token-shaped secrets; the two 045-01 logs and the
close-out log had no hits. As an extra check, part A's `.paul/orders/v5-fix-45b-installers.log` was scanned
too: no hits (`EXIT=1`).

Check A and check B outputs are pasted in (b) and (c) above.

## Deviations

1. **The test-venv interpreter is Python 3.13, not 3.14** (the plan assumed 3.14, the lab copies'
   version). The part A live install therefore ran mlxlm under both 3.13 (test-venv) and 3.14 (lab venv),
   and optiq under 3.14 only. The install path is the same; the wheel set a 3.13 install resolves is not
   the set a 3.14 install resolves, which is why mlxlm was run both ways.
2. **A single altered hash does not make pip refuse.** Flipping one hex digit of mlx's hash leaves pip a
   second listed wheel for the same version that matches, so the install can still succeed. The refusal
   was demonstrated by altering **every** mlx hash; pip then reported
   `THESE PACKAGES DO NOT MATCH THE HASHES` and installed nothing. A one-hash tamper test would have
   proven nothing.
3. **Worker A briefly created an empty directory in the real Application Support.** Its first
   `_venv_root` red-check made the fake create
   `<real Application Support>/OhYesMLX/engines/mlxlm-0.31.3/bin` (empty), because `_relocate` depends on
   `_venv_root`. It removed it with `rmdir` (empty-only). The real `optiq-0.5.13` venv, `lab-paths.json`,
   `install-log.jsonl` and `fetched.json` were not written. It then pinned `DEFAULT_ENV.home` to `tmp_path`
   in `do_install` so no install test can leave the scratch tree even when the code under test breaks.
4. **`tests/test_server.py` gained a `lock_dir`.** Worker B could not touch that file, and
   `test_a_real_evict_refusal_ends_its_stream_and_frees_the_slot` was calling the real `fetch.evict`
   without one, acquiring `download.lock` in the real Application Support (that directory's mtime moved
   Nov 3 12:12:01 to Nov 10 09:24:56 across suite runs; it stayed empty and no lock file remained). The
   coordinator added `lock_dir=str(tmp_path / "locks")` to that partial. This is the only edit outside the
   two orders' file lists. Verified after the fix: that test passes and the real locks directory's mtime is
   unchanged (`1794320828` before and after), and the full 1272-test run left it at the same mtime.
5. **The carried-items table is §8, not §7.4.** The order said "§7.4's PHASE-4 carried-items table (search
   'fixed in 045-02')"; the table matching that search is in section 8, and the T-16 row was marked there.
6. **The `.gitignore` block was removed whole.** Besides the three pattern lines, the two comment lines
   that described them ("unfixed security finding detail stays local..." and "045-01 worker reports carry
   unfixed finding detail...") were removed; leaving them would have described files that are no longer
   ignored. No other `.gitignore` line changed.
7. **pygame is a named exception to `--only-binary :all:`** (`engines._SOURCE_BUILDS = {"optiq":
   ("pygame",)}`). pygame 2.6.1 ships no CPython 3.14 wheel and mlx-optiq 0.5.13 requires it for its game
   command only; its build tools are fetched without hash checks. Jason's call at a BLOCKED, 2026-11-10
   (STATE Decisions); recorded in threat-model §9 and STATE Deferred Issues with a monthly check. Every
   other package installs wheels-only, and the sdist hashes in the two files are inert under the flag.

## Known gaps and observations (not fixed here)

- **The real fetch ledger is polluted by scratch-cache runs.** Its one repo entry names 60 paths under two
  `/private/tmp/claude-501/...` scratch caches (16 still on disk), so both the old cache-root check and the
  new per-repo check refuse it. quickbench injects `cache_dir` but leaves `ledger_path` at the default, so
  a scratch-cache quickbench run records scratch paths in the real ledger; that is the mechanism here. The
  app's own runs use the real cache and the default ledger, so this does not describe a user state; a real
  user ledger would pass. Cleaning the host's entry is a coordinator decision (it means writing the real
  ledger, which this order forbids).
- **The lock's stale-reclaim race is accepted, not fixed.** `_acquire_lock` is check-then-remove: two
  processes that both read a dead owner's pid can both remove and recreate the lock. Recorded in §9.
- **Two continuation joiners.** `scripts/hash_freeze.py` and `engines._check_hashed_requirements` each
  join `\` continuations with their own small helper. Putting it in `__init__.py` was outside part A's
  "add `atomic_write_text` only" scope.
- **The late-upload review is empty because nothing was late.** `hash_freeze.py` printed no
  `LATE UPLOADS`; that is a report of no late files, not a skipped step. A future freeze that gains a late
  file will print it.
- **Part A's independent hash cross-check is not recorded in the commit or threat model.** The coordinator
  has the live install and the refusal evidence, but this SUMMARY does not claim the plan's
  re-run-and-diff or the three-wheel `curl` + `shasum` checks.

## Deferred

- **The other four atomic-write copies** (`osaurus_settings`, `runtimes`, `measure`, `quickbench`) are not
  migrated to `ohyesmlx.atomic_write_text`. Plan SCOPE LIMITS; candidate for a Deferred Issues row.
- **Global pip config** (`/etc/pip.conf`, `/Library/Application Support/pip/pip.conf`) still loads under
  `--isolated`. It needs admin to write and a rerouted index cannot pass the hashes. Recorded, not fixed.
- **The reclaim race** is in §9, not fixed.
- **The pygame wheel watch** is a STATE Deferred Issues row: check about monthly and at every OptiQ bump;
  last checked 2026-11-10, pygame 2.6.1, no cp314 arm64 macOS wheel.

## Not done (out of scope, by plan)

No model download, no quickbench, no measurement, no server start. No live install was run by this
close-out dispatch; part A's live installs are the coordinator's. Code review (Standards + Spec) on part
B, UNIFY, `graphify update .` and `/paul:verify` are still owed.

## Test count

`1222` at the start (045-02a's end) -> `1261` after part A (39 new) -> `1272` after part B (11 new),
`1272 passed in 47.06s` on the final close-out run. The close-out changes only Markdown and `.gitignore`.

## Code review

Fixes for the two reviews of `a031ad4` + `fb4e61c` (`v5-review-45b-standards.log`,
`v5-review-45b-spec.log`), applied 2026-11-12. Every numbered item is listed; nothing else changed.
TDD, red test first, for each behavioural change.

| # | Item | Change | Test(s) |
|---|---|---|---|
| 1 | One joiner, one pin grammar | `engines.py:695-718`: `_PIN` is the single `name==version` fragment; `_PIN_ONLY` and `_HASHED_PIN` are built from it. `_requirement_lines` flushes a pending `\` line at EOF, so a file ending `pkg==1.0 \` is seen and refused as unhashed. `scripts/hash_freeze.py` imports `_requirement_lines` and `_PIN_ONLY` (`:38-42`) and `parse_freeze` (`:68-91`) uses them; `_logical_lines` and `_PIN` are deleted. | `test_engines.py:398` `test_a_file_ending_in_a_continuation_is_refused_as_unhashed` (2 cases); `test_hash_freeze.py:253` `test_a_trailing_continuation_at_eof_is_still_a_pin`; the 9 existing hash_freeze tests stay green. |
| 2 | A raising per-cell evictor | `quickbench.py:845-861`: the per-cell `evict` is wrapped like the leftover sweep's — the exception is caught, one `log` event names the repo, and the repo is appended to `summary["not_evicted"]` before `outstanding` drops it. | `test_quickbench.py:553` `test_an_evictor_that_raises_is_logged_and_recorded`. |
| 3 | `install`'s comment | `engines.py:1225-1228`: comment now says a missing constraints file and an unhashed one are both `no_constraints` (AC-1). No code change. | Existing `test_engines.py:437` `test_an_unhashed_constraints_file_refuses_the_install_as_no_constraints` already asserts the code. |
| 4 | One `_link_conflicts` refusal text | `fetch.py:566` `_link_refusal(planned_file)` is the one message; used by the pre-transfer pass (`:784`) and `link_all` (`:857`). | `test_fetch.py:862-863` asserts the exact text on the pre-transfer refusal. |
| 5 | Rationale written once | `engines.py`: `record_lab_path`'s docstring points at `ohyesmlx.atomic_write_text` and `check_lab_dir` instead of restating them (`:473-481`), and its app-engine raise no longer restates the archival reason (`:483-487`); `lab_paths`'s docstring points at `LAB_ENGINES` (`:425-426`). "Archived" is explained once, at `LAB_ENGINES` (`:380-383`). One exception below. | `test_engines.py:866` (match string updated to the new refusal). |
| 6 | Global lock-dir guard; no real lab-paths file | New `tests/conftest.py`: the autouse `_no_real_lock_dir` fixture applies to every module and compares `os.path.realpath(os.path.dirname(...))`; the copy in `tests/test_fetch.py` is deleted. `tests/test_runtimes.py:3375` now passes `tmp_path / "no-lab-paths.json"`. | `test_fetch.py:29` `test_the_lock_dir_guard_fires_on_the_real_directory`. |
| 7 | `runtimes.py` `entry["lab_path"]` KeyError | **Fixed by the coordinator** (Jason, 2026-11-11): pre-existing, but it would crash every engine start the first time a manifest entry omits the optional key (MTPLX, Phase 5). Now `entry.get("lab_path")`. | `test_a_manifest_entry_without_a_lab_path_key_means_no_lab_path` (red before, green after) |
| 8 | Ledger follows cache | `fetch.py:152` `ledger_for(cache_dir)`: `DEFAULT_LEDGER` for None or the default cache (realpath), else `<realpath(cache_dir)>.ohyesmlx-fetched.json`. `download` (`:686`) and `evict` (`:1202`) default `ledger_path=None` and resolve it; an explicit path is honoured. `docs/interfaces.md:1854-1861` has the paragraph. | `test_fetch.py:1356` `test_a_non_default_cache_writes_its_own_sibling_ledger`, `:1375` `test_the_default_cache_uses_the_apps_ledger`, `:1386` `test_evict_on_a_scratch_cache_reads_the_sibling_ledger`. |

### Red-checks (reverted, run, restored)

- **Item 1.** EOF flush removed -> `test_a_file_ending_in_a_continuation_is_refused_as_unhashed` (both
  cases) and `test_a_trailing_continuation_at_eof_is_still_a_pin` failed (validator passed the dangling
  pin; hash_freeze parsed zero pins). Restored, green.
- **Item 2.** Inner try/except removed -> `test_an_evictor_that_raises_is_logged_and_recorded` failed with
  `OSError: the log path is not writable` out of `evict`. Restored, green.
- **Item 6.** `monkeypatch.setattr(fetch, "_acquire_lock", guarded)` disabled in `conftest.py` -> the guard
  test failed `DID NOT RAISE AssertionError` and `download.lock` appeared under a scratch `HOME`
  (`.commandcode` scratchpad, `HOME=<scratch>` so `DEFAULT_LOCK_DIR` was scratch). Restored; the test
  passes and no locks directory is created. The real lock directory was never reachable in this check.
- **Item 8.** `ledger_for` reverted to `return DEFAULT_LEDGER` for every cache ->
  `test_a_non_default_cache_writes_its_own_sibling_ledger` and
  `test_evict_on_a_scratch_cache_reads_the_sibling_ledger` failed (`FileNotFoundError` on the sibling; the
  download had written the monkeypatched `DEFAULT_LEDGER` instead). `test_the_default_cache_uses_the_apps_ledger`
  still passed, as expected. Restored, green.

### Notes

- **The one "archived" restatement left** is the `lab_paths` refusal text
  (`test-visible` at `engines.py:454-457`): `docs/runtimes/lab-copies.md:116` quotes that sentence as the
  contract, and that file is outside this order's allowlist. Changing the message would have left a stale
  quote in a file I could not touch, so the message stays and the archival rationale lives in both
  `LAB_ENGINES` and that published refusal. A follow-up that may touch the doc can move it fully.
- Items 3, 4 and 5 are non-behavioural (a comment, an extraction that preserves the asserted text, and
  docstrings), so none of the three has a red-check; no test can fail for them without contriving one.
- No module, subcommand or dependency. No download, network, real HOME, Application Support, ledger, lock
  directory or HF cache was touched: the new fetch tests run on `tmp_path` with a fake transport, and the
  red-check for item 6 ran under a scratch `HOME`.
- Final: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` -> `1280 passed in 46.43s`
  (1272 before; 8 new). Four full runs on the final code: three `1280 passed` and one
  (`1279 passed, 1 failed`) in which
  `tests/test_server.py::test_the_handler_thread_cap_closes_the_extra_connection_and_releases_at_timeout`
  failed. That test is a 0.5 s wall-clock/32-socket concurrency check and touches nothing this order changed;
  it passed 20/20 repetitions alone, passed with all of `test_server.py`, and passed in the three clean full
  runs, so it is a load-sensitive flake rather than a regression — but I did not prove that. Nothing committed.

