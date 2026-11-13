# v5 hardening — interface shapes

Plan 045-02a's recovery of an interrupted app, and plan 045-02b's hash-pinned installs and validated lab path.

## v5.0 plan 045-02a — an interrupted app is recovered at the next launch

Three lifecycle contracts close T-02: a `SIGKILL` of `ohyesmlx app` (or its 120 s shutdown wait expiring) no longer
leaves an engine holding a port and its weights, a pinned Osaurus whose restore never ran, or a pip step running
with no rollback.

**The running-engines ledger** (`ohyesmlx/runtimes.py`). `Runtime.start` records one entry per started engine —
`{"pid": int, "lstart": str|null, "argv": str|null, "serving_pid": int, "serving_lstart": str|null,
"serving_argv": str|null, "port": int, "stop_command": [str, ...]}` — in
`<writable_root()>/results/running-engines/<owner pid>.json`, one file per owner process so two harness processes
never read-modify-write one file. Each pid carries its own identity read from `/bin/ps -ww -o lstart=,args= -p <pid>`;
`serving_pid` is the pid `Runtime.start` already resolved as the one holding the weights, and a launcher that has
already exited (`osaurus serve` exits once the app is listening) is recorded with a null identity rather than failing
the start. The write is after `cold_load_s` is taken, so no measured load time contains the `ps` calls, and its
failure is one stderr line (`{"error": {"code": "running_engine_ledger", "message": str}}`) that never fails the
start. Every write is a temp file in the same directory plus `os.replace`; `Handle.stop` drops its own entry and the
file goes when its last entry does.

```python
stop_orphaned_engines(root=None) -> None   # root: the writable root, default writable_root()
```

For each ledger file whose owner pid is dead — and only `<owner pid>.json` is a ledger; any other file in the
directory is left alone — it reads the pids listening on the entry's `port` (`lsof -t`) and stops the entry through
`_shutdown(pid, port, tuple(stop_command))` only when **every** listener is one of the entry's recorded pids with the
identity recorded for it (the Osaurus shape: the launcher pid is already dead and the app is the listener), or when
nothing is listening and the spawned pid is alive with its recorded identity. An unreadable port, a stranger
listening, or an identity that no longer matches — a reused pid, or the user's own identical command started later —
is dropped and never signalled; a file whose owner is still alive belongs to a grid running from the CLI and is never
read or touched. A stop that does not take effect keeps the file and raises `RuntimeStopError`.

**`ohyesmlx app` startup** (`cli._recover_startup`, after the bind and before the launch line):
`stop_orphaned_engines()` runs first; then, only while `quickbench._osaurus_app_running()` is False,
`osaurus_settings.recover(backup_dir=quickbench.DEFAULT_BACKUP_DIR, baseline_path=osaurus_settings.BASELINE_PATH)`
runs. Each outcome is at most one stderr line and nothing is written to stdout (the launch line stays the only
stdout line), and none of them can stop the server:

```python
{"recovered": "osaurus", "backup_dir": str}          # recover returned True
{"recovery_pending": "osaurus", "backup_dir": str}   # the app is running and a backup is present; left alone
{"recovery_failed": "osaurus", "backup_dir": str}    # recover returned False with backups still present
{"error": {"code": "osaurus_recovery_failed", "message": str}}
{"error": {"code": "orphan_stop_failed", "message": str}}
```

**An install step's process group** (`engines._real_run`, `engines.kill_running_steps`,
`server.JOB_KILL_GRACE_S`). Each step runs through `Popen(..., start_new_session=True)` and is registered in a
module-level set under the same lock that covers its spawn, so a kill can neither snapshot the registry between the
two nor miss a step that has started; the registry is empty however the step ends. A step that exceeds its own
timeout has its process group killed and still reports `TIMEOUT_EXIT_CODE` with the output it produced.
`kill_running_steps()` kills every registered group — it is what `_Jobs.cancel_and_wait` calls when its bound expires
(see the shutdown paragraph above).

## v5.0 plan 045-02b — hash-pinned installs and a validated lab path

**A pip engine's install argv** (`engines._command_plan`, AC-1 and AC-2). Both steps run their
interpreter with `-I`, so neither reads the user's site-packages or `PYTHON*` variables; the pip
step also runs `--isolated`, so no user pip config and no `PIP_*` variable chooses the index. The
requirements file names every package: no `pkg==ver` token is passed on the command line.

```sh
{python} -I -m venv <Application Support>/OhYesMLX/engines/<name>-<TESTED_VERSIONS[name]>
<root>/bin/python -I -m pip install --isolated --no-input --disable-pip-version-check \
    --require-hashes --only-binary :all: -r <ohyesmlx/constraints/<name>-<version>.txt>
```

`--require-hashes` makes the file the pin: a line without a hash is refused by pip, and a hash the
file does not list is refused for the file it names. `--only-binary :all:` is required with it,
because hash-checking mode does not cover the PEP 517 build dependencies pip fetches to build an
sdist, and building an sdist runs its code. There is no exception: every pip step also carries
`--no-deps`, so the file is the whole closure and optiq's pygame (used only by `optiq game`, no
CPython 3.14 wheel) is omitted rather than built from source (045-03; rationale at `engines._command_plan`). (`--isolated` still loads the global and site pip
config; they need admin to write, and a rerouted index cannot pass the hashes.)

**`engines._check_hashed_requirements(path) -> None`** (AC-1). One validator, called by
`install_plan` beside the missing-file check, so `install` refuses a file with no hashes exactly
as it refuses a missing one (`ValueError`, reported as `error` code `no_constraints`). Every
non-blank, non-comment logical line — `\` continuations joined — must be exactly
`name==version` followed by one or more `--hash=sha256:<64 lowercase hex>` tokens and nothing
else. A pin with no hash is refused with a message saying it "carries no hashes"; anything else
— `--index-url`, `--extra-index-url`, `--trusted-host`, `-f`, `-r`, `-c`, `-e` — is refused naming
the line. Each message names the file, because the fix is to regenerate it with
`scripts/hash_freeze.py` (a stdlib maintenance script beside `scripts/`, not a package surface:
`<freeze-file>` in, the same file out with every `urls[].digests.sha256` PyPI lists for each pin,
sorted, plus one header line naming the source and date).

**`engines.check_lab_dir(path) -> None`** (AC-3). One definition of what may become the front of
PATH, called by `runtimes._engine_env` after `expanduser` and after its "nothing at" refusal
(which keeps its wording), and by `record_lab_path` before it reads or writes. It raises
`ValueError` naming the path and the reason unless the path is absolute, `os.stat` (following
symlinks) is a directory, `st_uid == os.geteuid()`, and
`st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0`. A failure at start is a `RuntimeStartError`
carrying that message; `detect_all` is unchanged and only reports (`ValueError` there is a
configuration defect, never a reason to fall back to the global install).

**`fetch.ledger_for(cache_dir) -> str`** (045-02b review). The one answer to which ledger a
download or eviction writes. It is `DEFAULT_LEDGER` (`<app support>/fetched.json`) when
`cache_dir` is None or resolves (`os.path.realpath`) to `fetch.default_cache_dir()`; any
other cache gets `<realpath(cache_dir)>.ohyesmlx-fetched.json`, a sibling of the cache and
never a path inside it. `fetch.download` and `fetch.evict` take `ledger_path=None` and use
this answer, so a run against a scratch or per-run cache records what it fetched beside
that cache instead of writing scratch paths into this Mac's ledger; an explicit
`ledger_path` is honoured exactly as before.
