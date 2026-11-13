#!/bin/sh
# 045-03 clean-account smoke: build what a user gets, then drive it as a throwaway account.
#
# Runs as jrazz and does everything through `sudo -n -u oymlxtest`, so nothing it touches
# belongs to the real account. Subcommands, in the order a smoke uses them:
#
#   preflight     AC-1's preconditions; exits 1 naming the one that failed
#   setup         preflight, Jason's host snapshot, the wheel from `git archive HEAD`,
#                 oymlxtest's venv, and that venv's `ohyesmlx` installed --no-deps --no-index
#   run           the client (scripts/smoke_clean_account.py) as oymlxtest, with a sweep trap
#   verify-host   AC-7: Jason's Application Support, HF cache and Osaurus config unchanged
#   teardown      remove oymlxtest's venv, Application Support and HF cache; keep the results
#
# The model below is downloaded once, into oymlxtest's own HF cache, and evicted by the run.
set -eu

TEST_USER=oymlxtest
TEST_HOME=/Users/oymlxtest
SMOKE=/Users/Shared/oymlx-smoke
PY=/opt/homebrew/bin/python3.14
PORTS="1337 8000 8080 8081 8100 8200"

# Purpose (AGENTS.md, "Downloads need a reason and a record"): 045-03's clean-account smoke
# downloads this one 0.35 GB row, into oymlxtest's cache only, and evicts it in the same run.
# It is the smallest catalog model with no sibling formats, so quickbench stage B fetches
# nothing more. Jason's HF cache is never written.
MODEL=mlx-community/Qwen3-0.6B-4bit

REPO=$(cd "$(dirname "$0")/.." && pwd)
OSAURUS_APP='/Applications/osaurus.app/Contents/MacOS/osaurus'

log() { printf '%s\n' "$*" >&2; }

# The one wrapper every oymlxtest command goes through: launchd's default environment (P5-9)
# and a cwd that account can read. The subshell keeps the cd out of this script.
as_test_user() (
    cd "$SMOKE" 2>/dev/null || cd /
    exec sudo -n -u "$TEST_USER" env -i \
        HOME="$TEST_HOME" USER="$TEST_USER" LOGNAME="$TEST_USER" \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        "$@"
)

# --- preflight --------------------------------------------------------------------------

fail() { log "PRECONDITION: $*"; exit 1; }

listeners_on() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null
    as_test_user lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

preflight() {
    sudo -n -u "$TEST_USER" true 2>/dev/null \
        || fail "sudo -n -u $TEST_USER (add /etc/sudoers.d/oymlxtest)"

    for port in $PORTS; do
        [ -z "$(listeners_on "$port")" ] || fail "nothing listening on port $port"
    done

    if pgrep -f "^$OSAURUS_APP" >/dev/null 2>&1; then
        fail "the Osaurus app is not running ($OSAURUS_APP)"
    fi

    xcode-select -p >/dev/null 2>&1 || fail "xcode-select -p (optiq builds pygame from source)"

    free_kb=$(df -k / | awk 'NR == 2 {print $4}')
    [ "${free_kb:-0}" -ge 5242880 ] || fail "at least 5 GiB free on / (have ${free_kb:-0} KiB)"

    as_test_user test ! -e "$TEST_HOME/Library/Application Support/OhYesMLX" \
        || fail "$TEST_USER has no ~/Library/Application Support/OhYesMLX"
    hub="models--$(printf '%s' "$MODEL" | sed 's|/|--|g')"
    as_test_user test ! -e "$TEST_HOME/.cache/huggingface/hub/$hub" \
        || fail "$TEST_USER has no ~/.cache/huggingface/hub/$hub"

    log "preflight: ok"
}

# --- AC-7 host snapshot -----------------------------------------------------------------

# AC-7. One function, so `verify-host` cannot snapshot a different set of things than `setup`.
# A file that is absent leaves a marker, so a file that appears later is still a difference.
snapshot_host() {
    target=$1
    support="$HOME/Library/Application Support/OhYesMLX"
    hub="$HOME/.cache/huggingface/hub"
    osaurus="$HOME/.osaurus/config"
    rm -rf "$target"
    mkdir -p "$target"
    # Copies of Jason's config land under /Users/Shared, which every account can read.
    chmod 700 "$target"

    if [ -d "$support" ]; then
        # `..` is Application Support itself, whose mtime moves whenever any app writes there.
        ls -laT "$support" | grep -v ' \.\.$' >"$target/app-support.txt"
        for name in lab-paths.json fetched.json; do
            if [ -f "$support/$name" ]; then
                cp "$support/$name" "$target/$name"
            else
                : >"$target/$name.absent"
            fi
        done
    else
        : >"$target/app-support.absent"
    fi

    if [ -d "$hub" ]; then
        ls "$hub" >"$target/hub.txt"
    else
        : >"$target/hub.absent"
    fi

    if [ -d "$osaurus" ]; then
        for file in "$osaurus"/*; do
            if [ -f "$file" ]; then
                cp "$file" "$target/osaurus-$(basename "$file")"
            fi
        done
    else
        : >"$target/osaurus.absent"
    fi
}

pgrep_snapshot() { pgrep -lu "$TEST_USER" 2>/dev/null || true; }

# --- setup ------------------------------------------------------------------------------

setup() {
    preflight
    mkdir -p "$SMOKE"
    # oymlxtest starts the app, and the client writes its results here; the token is never
    # on disk, so a world-writable results directory discloses nothing but PASS/FAIL.
    mkdir -p "$SMOKE/results"
    chmod 0777 "$SMOKE/results"

    log "setup: host snapshot -> $SMOKE/host-before"
    snapshot_host "$SMOKE/host-before"
    pgrep_snapshot >"$SMOKE/pgrep-before.txt"

    head_sha=$(git -C "$REPO" rev-parse HEAD)
    printf '%s\n' "$head_sha" >"$SMOKE/head"
    log "setup: HEAD $head_sha"

    work=$(mktemp -d "${TMPDIR:-/tmp}/oymlx-smoke.XXXXXX")
    trap 'rm -rf "$work"' EXIT
    git -C "$REPO" archive --format=tar HEAD >"$work/head.tar"
    tar -xf "$work/head.tar" -C "$work"
    rm -f "$work/head.tar"

    rm -rf "$SMOKE/dist"
    mkdir -p "$SMOKE/dist"
    log "setup: uv build --wheel"
    ( cd "$work" && uv build --wheel --out-dir "$SMOKE/dist" >/dev/null )

    cp "$REPO/scripts/smoke_clean_account.py" "$SMOKE/smoke_clean_account.py"
    chmod a+rX "$SMOKE" "$SMOKE/dist" "$SMOKE/dist"/* "$SMOKE/smoke_clean_account.py"

    log "setup: venv for $TEST_USER"
    as_test_user "$PY" -I -m venv "$TEST_HOME/oymlx-venv"
    as_test_user "$TEST_HOME/oymlx-venv/bin/python" -I -m pip install \
        --no-deps --no-index "$SMOKE"/dist/*.whl >/dev/null

    log "setup: done"
}

# --- run --------------------------------------------------------------------------------

# AC-6: a crash mid-quickbench must not leave a model resident. The trap kills the client
# first, because the client's death is what closes the app's stdin and stdin EOF is the app's
# own shutdown signal (docs/interfaces.md); it then gives the app its own moment to exit and
# sweeps whatever engine is left listening on an AC-1 port. Every listing here is taken AS
# oymlxtest, whose own pgrep and lsof cannot see another account's processes at all, so
# ownership is structural rather than a guess from a process table: a jrazz-owned process is
# never named, whatever port it holds.
sweep() {
    for pid in $(as_test_user pgrep -f "$SMOKE/smoke_clean_account.py" 2>/dev/null || true); do
        sweep_pid "client" "$pid"
    done
    for port in $PORTS; do
        for pid in $(as_test_user lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true); do
            sweep_pid "port $port" "$pid"
        done
    done
    # Last, and by its own start command: the app binds an ephemeral port, so a port sweep
    # alone would miss it and leave it holding the venv's interpreter.
    for pid in $(as_test_user pgrep -f "$TEST_HOME/oymlx-venv/bin/ohyesmlx app" 2>/dev/null || true); do
        sweep_pid "app" "$pid"
    done
}

sweep_pid() {
    what=$1
    pid=$2
    log "sweep: $what held by $TEST_USER pid $pid, TERM"
    sudo -n -u "$TEST_USER" kill "$pid" 2>/dev/null || true
    waited=0
    while [ "$waited" -lt 5 ] && sudo -n -u "$TEST_USER" kill -0 "$pid" 2>/dev/null; do
        sleep 1
        waited=$((waited + 1))
    done
    if sudo -n -u "$TEST_USER" kill -0 "$pid" 2>/dev/null; then
        log "sweep: $what pid $pid still alive after ${waited}s, KILL"
        sudo -n -u "$TEST_USER" kill -9 "$pid" 2>/dev/null || true
    fi
}

run() {
    [ -f "$SMOKE/head" ] || { log "run: no $SMOKE/head; run setup first"; exit 1; }
    head_sha=$(cat "$SMOKE/head")

    trap 'exit 130' INT TERM
    trap 'sweep' EXIT
    status=0
    as_test_user "$TEST_HOME/oymlx-venv/bin/python" -I \
        "$SMOKE/smoke_clean_account.py" \
        --out "$SMOKE/results" --head "$head_sha" \
        --forbid /Users/jrazz --model "$MODEL" || status=$?
    trap - EXIT INT TERM

    sweep
    pgrep_snapshot >"$SMOKE/pgrep-after.txt"
    if diff -u "$SMOKE/pgrep-before.txt" "$SMOKE/pgrep-after.txt"; then
        log "run: $TEST_USER processes unchanged"
    else
        log "run: $TEST_USER processes changed (above)"
    fi
    return "$status"
}

# --- verify-host ------------------------------------------------------------------------

verify_host() {
    [ -d "$SMOKE/host-before" ] || { log "verify-host: no $SMOKE/host-before; run setup first"; exit 1; }
    snapshot_host "$SMOKE/host-after"
    if diff -r "$SMOKE/host-before" "$SMOKE/host-after"; then
        log "verify-host: Jason's account is unchanged"
    else
        log "verify-host: DIFFERENCES above"
        exit 1
    fi
}

# --- teardown ---------------------------------------------------------------------------

teardown() {
    log "teardown: removing $TEST_USER's smoke state"
    as_test_user rm -rf \
        "$TEST_HOME/oymlx-venv" \
        "$TEST_HOME/Library/Application Support/OhYesMLX" \
        "$TEST_HOME/.cache/huggingface"
    log "teardown: removed venv, Application Support/OhYesMLX, .cache/huggingface"

    for entry in "$SMOKE"/*; do
        [ -e "$entry" ] || continue
        case "$entry" in
        "$SMOKE/results") continue ;;
        esac
        rm -rf "$entry"
        log "teardown: removed $entry"
    done
    log "teardown: kept $SMOKE/results"
}

case "${1:-}" in
preflight) preflight ;;
setup) setup ;;
run) run ;;
verify-host) verify_host ;;
teardown) teardown ;;
*)
    log "usage: $0 {preflight|setup|run|verify-host|teardown}"
    exit 2
    ;;
esac
