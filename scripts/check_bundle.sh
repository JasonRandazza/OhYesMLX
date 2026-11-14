#!/bin/sh
# Check P5-3, P5-4, P5-6 and P5-9 on the bundle that would ship (threat model §10; plan 05-06,
# AC-4). Every check prints PASS or FAIL, and the script exits non-zero if any failed.
#
#   scripts/check_bundle.sh dist/OhYesMLX.app            all four checks; launches the app
#   scripts/check_bundle.sh dist/OhYesMLX.app --no-gui   P5-3 and P5-4 only
#
# The P5-6 step copies the app onto a read-only disk image, opens it from there, waits for a
# served GET /hardware, quits it, and verifies the signature again. It writes to the real
# ~/Library/Application Support/OhYesMLX, as a real first launch would, and it needs the app to
# be the only OhYesMLX instance running.
set -eu

APP=${1:-}
MODE=${2:-}
case "$APP" in
    "" | -*)
        echo "usage: $0 <path to OhYesMLX.app> [--no-gui]" >&2
        exit 2
        ;;
esac
case "$MODE" in
    "" | --no-gui) ;;
    *)
        echo "usage: $0 <path to OhYesMLX.app> [--no-gui]" >&2
        exit 2
        ;;
esac

APP=$(CDPATH= cd -- "$APP" && pwd)
PYTHON="$APP/Contents/Resources/python/bin/python3"

FAILURES=0
pass() { printf 'PASS %s: %s\n' "$1" "$2"; }
fail() { printf 'FAIL %s: %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

WORK=$(mktemp -d "${TMPDIR:-/tmp}/ohyesmlx-bundle-check.XXXXXX")
# macOS reports /var/folders paths as /private/var/folders in `mount` and in process argv, so
# `mount` is matched on the physical path; process argv on the path without /private, which is
# how the app's bundle path (and so the backend's argv) spells it.
WORK=$(cd -P "$WORK" && pwd)
MOUNT="$WORK/mnt"
DMG="$WORK/OhYesMLX-check.dmg"
APP_PID=""
BACKEND_PID=""
cleanup() {
    if [ -n "$APP_PID" ]; then
        kill -TERM "$APP_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ]; then
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -d "$MOUNT" ]; then
        hdiutil detach "$MOUNT" -force >/dev/null 2>&1 || true
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

[ -x "$PYTHON" ] || {
    echo "$0: $PYTHON is not executable; is $APP a built bundle?" >&2
    exit 2
}

echo "==> P5-3: $PYTHON under -I"
CWD="$WORK/cwd"
SHADOW="$WORK/shadow"
mkdir -p "$CWD" "$SHADOW"
printf 'raise SystemExit("a module from the cwd or PYTHONPATH was imported")\n' >"$CWD/shadow.py"
printf 'raise SystemExit("a module from the cwd or PYTHONPATH was imported")\n' >"$SHADOW/shadow.py"
if (cd "$CWD" && PYTHONPATH="$SHADOW" HOME="$WORK/p53-home" \
    "$PYTHON" -I -B -B - <<'PY'
import json
import os
import site
import sys

facts = {
    "sys.path": sys.path,
    "ENABLE_USER_SITE": site.ENABLE_USER_SITE,
    "usersite": site.getusersitepackages(),
    "cwd": os.getcwd(),
    "PYTHONPATH": os.environ.get("PYTHONPATH"),
}
print(json.dumps(facts, indent=2))

assert "" not in sys.path, "the current directory is on sys.path"
assert facts["cwd"] not in sys.path, "the current directory is on sys.path"
assert not site.ENABLE_USER_SITE, "the user site is enabled"
assert not any(path.startswith(site.getusersitepackages()) for path in sys.path), "user site is on sys.path"
assert not any(path == facts["PYTHONPATH"] for path in sys.path), "PYTHONPATH reached sys.path"
try:
    import shadow
except ImportError:
    pass
else:
    raise SystemExit("a module from the cwd or PYTHONPATH was imported")
PY
); then
    pass P5-3 "no user site, no cwd, no PYTHON* on sys.path"
else
    fail P5-3 "sys.path is not isolated (see above)"
fi

echo "==> P5-4: an HTTPS GET to huggingface.co on a clean environment"
if (env -i \
    HOME="$WORK/p54-home" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    "$PYTHON" -I -B -B - <<'PY'
import json
import ssl
import urllib.request

context = ssl.create_default_context()
facts = {
    "verify_mode": context.verify_mode.name,
    "check_hostname": context.check_hostname,
    "openssl": ssl.OPENSSL_VERSION,
}
with urllib.request.urlopen(
    "https://huggingface.co/api/models/mlx-community/Qwen3-0.6B-4bit", timeout=60
) as response:
    facts["status"] = response.status
print(json.dumps(facts, indent=2))
assert context.verify_mode == ssl.CERT_REQUIRED, "certificate verification is not required"
assert context.check_hostname, "hostname checking is off"
assert facts["status"] == 200, f"HTTP {facts['status']}"
PY
); then
    pass P5-4 "https://huggingface.co answered 200 with verification on"
else
    fail P5-4 "the HTTPS GET failed (see above)"
fi

if [ "$MODE" = "--no-gui" ]; then
    echo "==> P5-6 and P5-9 skipped (--no-gui)"
else
    echo "==> P5-6 and P5-9: the app on a read-only disk image"
    RUNNING=$(pgrep -f 'OhYesMLX\.app/Contents/MacOS/OhYesMLX' || true)
    if [ -n "$RUNNING" ]; then
        fail P5-6 "quit OhYesMLX before running this check (one instance only, P5-7)"
    else
        hdiutil create -quiet -srcfolder "$APP" -format UDRO -volname OhYesMLXCheck -ov "$DMG" \
            || fail P5-6 "could not create the disk image"
    fi

    if [ -f "$DMG" ]; then
        mkdir -p "$MOUNT"
        hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT" "$DMG" >/dev/null \
            || fail P5-6 "could not mount the disk image"
    fi

    if [ -d "$MOUNT/OhYesMLX.app" ]; then
        mount | grep -F " on $MOUNT " | grep -q 'read-only' \
            && pass P5-6 "the mounted volume is read-only" \
            || fail P5-6 "the mounted volume is not read-only (mount: $(mount | grep -F " on $MOUNT " || echo none))"

        open "$MOUNT/OhYesMLX.app" || fail P5-6 "could not open the mounted copy"
        attempt=0
        while [ "$attempt" -lt 120 ] && [ -z "$BACKEND_PID" ]; do
            BACKEND_PID=$(pgrep -f "${MOUNT#/private}/OhYesMLX.app/Contents/Resources/python/bin/python3" | head -1 || true)
            [ -n "$BACKEND_PID" ] || sleep 0.5
            attempt=$((attempt + 1))
        done
        APP_PID=$(pgrep -f "${MOUNT#/private}/OhYesMLX.app/Contents/MacOS/OhYesMLX" | head -1 || true)

        if [ -z "$BACKEND_PID" ]; then
            fail P5-6 "the backend never started from the mounted copy"
        else
            pass P5-6 "the backend started from the read-only copy (pid $BACKEND_PID)"

            PORT=""
            attempt=0
            while [ "$attempt" -lt 60 ] && [ -z "$PORT" ]; do
                PORT=$(/usr/sbin/lsof -nP -a -p "$BACKEND_PID" -iTCP -sTCP:LISTEN 2>/dev/null |
                    awk 'NR > 1 { split($9, parts, ":"); print parts[length(parts)]; exit }')
                [ -n "$PORT" ] || sleep 0.5
                attempt=$((attempt + 1))
            done
            if [ -z "$PORT" ]; then
                fail P5-6 "the backend never listened on a port"
            else
                CODE=""
                attempt=0
                while [ "$attempt" -lt 60 ]; do
                    CODE=$(/usr/bin/curl -s -o /dev/null -w '%{http_code}' \
                        "http://127.0.0.1:$PORT/hardware" || true)
                    case "$CODE" in
                        200 | 401) break ;;
                    esac
                    sleep 0.5
                    attempt=$((attempt + 1))
                done
                case "$CODE" in
                    200) pass P5-6 "GET /hardware answered 200 from the read-only copy" ;;
                    401) pass P5-6 "GET /hardware was served (401 unauthorised: the token is the parent's, P5-2)" ;;
                    *) fail P5-6 "GET /hardware answered ${CODE:-nothing} on port $PORT" ;;
                esac
            fi

            ARGS=$(/bin/ps -p "$BACKEND_PID" -o args= || true)
            case "$ARGS" in
                *"-I -B -m ohyesmlx.cli app"*)
                    pass P5-9 "the backend runs the launcher's argv: $ARGS" ;;
                *)
                    fail P5-9 "the backend's argv is not the launcher's: ${ARGS:-nothing}" ;;
            esac

            # P5-9 wants the backend's PATH read from outside. macOS no longer exposes another
            # process's environment: on 27.2.1 `ps eww`, `ps -E` and KERN_PROCARGS2 all return
            # the argv with no environment block. When the block is there it is checked; when
            # it is not, the check says so instead of passing on an unverified property.
            ENV_DUMP=$(/bin/ps eww -p "$BACKEND_PID" -o command= || true)
            case "$ENV_DUMP" in
                *"PATH="*)
                    case "$ENV_DUMP" in
                        *"PATH=/usr/bin:/bin:/usr/sbin:/sbin"*)
                            pass P5-9 "the backend's PATH is launchd's default" ;;
                        *)
                            fail P5-9 "the backend's PATH is not /usr/bin:/bin:/usr/sbin:/sbin" ;;
                    esac
                    case "$ENV_DUMP" in
                        *"PYTHONPATH="* | *"PYTHONHOME="*)
                            fail P5-9 "the backend carries a PYTHON* variable" ;;
                        *)
                            pass P5-9 "the backend carries no PYTHON* variable" ;;
                    esac
                    ;;
                *)
                    fail P5-9 "macOS $(sw_vers -productVersion) prints no environment for another process, so the backend's PATH cannot be read from outside; the property is covered by LauncherTests.testArgvEnvironmentAndDirectory and needs a decision here" ;;
            esac
        fi

        if [ -n "$APP_PID" ]; then
            osascript -e 'tell application id "io.github.jasonrandazza.ohyesmlx" to quit' >/dev/null 2>&1 || true
            attempt=0
            while [ "$attempt" -lt 60 ] && kill -0 "$APP_PID" 2>/dev/null; do
                sleep 0.5
                attempt=$((attempt + 1))
            done
            if kill -0 "$APP_PID" 2>/dev/null; then
                kill -TERM "$APP_PID" 2>/dev/null || true
                attempt=0
                while [ "$attempt" -lt 20 ] && kill -0 "$APP_PID" 2>/dev/null; do
                    sleep 0.5
                    attempt=$((attempt + 1))
                done
            fi
            kill -0 "$APP_PID" 2>/dev/null && fail P5-6 "the app did not quit" || APP_PID=""
        fi

        codesign --verify --deep --strict "$MOUNT/OhYesMLX.app" \
            && pass P5-6 "codesign --verify --deep --strict still passes on the mounted copy" \
            || fail P5-6 "the signature no longer verifies after the run"
        hdiutil detach "$MOUNT" -force >/dev/null 2>&1 && MOUNT=""
    fi
fi

if [ "$FAILURES" -ne 0 ]; then
    echo "$FAILURES check(s) FAILED" >&2
    exit 1
fi
echo "all checks PASS"
