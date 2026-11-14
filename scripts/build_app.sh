#!/bin/sh
# Build dist/OhYesMLX.app: the release Swift binary, the pinned python-build-standalone
# interpreter with the ohyesmlx package in its site-packages, ad-hoc signed inside-out, zipped
# and recorded in an SBOM (plan 05-06, tasks 1; AC-1..AC-3, AC-7).
#
#   scripts/build_app.sh
#
# Every tool is macOS's own (swift, ditto, codesign, plutil, PlistBuddy, shasum, file) or the
# interpreter this script fetches, so there is no new dependency. Not notarized and not signed
# with a Developer ID: D7, no Apple Developer account (docs/release/gatekeeper.md).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_DIR="$ROOT/app"
DIST="$ROOT/dist"
APP="$DIST/OhYesMLX.app"
CONTENTS="$APP/Contents"

fail() {
    echo "build_app.sh: $*" >&2
    exit 1
}

echo "==> the pinned interpreter" >&2
PYTHON_ROOT=$("$ROOT/scripts/fetch_python_standalone.sh")
IDENTITY=$("$ROOT/scripts/fetch_python_standalone.sh" --identity)
RELEASE_TAG=$(printf '%s\n' "$IDENTITY" | sed -n 's/^release=//p')
INTERPRETER_URL=$(printf '%s\n' "$IDENTITY" | sed -n 's/^url=//p')
INTERPRETER_SHA256=$(printf '%s\n' "$IDENTITY" | sed -n 's/^sha256=//p')
[ -x "$PYTHON_ROOT/bin/python3" ] || fail "$PYTHON_ROOT/bin/python3 is not executable"

# One definition of the version: the package's own `__version__`, read before it is copied.
VERSION=$(OYMLX_REPO="$ROOT" "$PYTHON_ROOT/bin/python3" -I -c \
    'import os, sys; sys.path.insert(0, os.environ["OYMLX_REPO"]); import ohyesmlx; print(ohyesmlx.__version__)')
[ -n "$VERSION" ] || fail "could not read ohyesmlx.__version__"
ZIP="$DIST/OhYesMLX-$VERSION.zip"
SBOM="$DIST/OhYesMLX-$VERSION-sbom.json"

echo "==> swift build -c release (OhYesMLX $VERSION)" >&2
swift build --package-path "$APP_DIR" -c release >&2 || fail "swift build failed"
BINARY="$APP_DIR/.build/release/OhYesMLX"
[ -f "$BINARY" ] || fail "$BINARY was not built"
SWIFT_VERSION=$(swift --version 2>/dev/null | head -1)

echo "==> assembling $APP" >&2
rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"
ditto "$BINARY" "$CONTENTS/MacOS/OhYesMLX"
ditto "$APP_DIR/Resources/Info.plist" "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$CONTENTS/Info.plist"
plutil -lint "$CONTENTS/Info.plist" >/dev/null || fail "Contents/Info.plist is not a valid plist"

echo "==> copying the interpreter into Contents/Resources/python" >&2
ditto "$PYTHON_ROOT" "$CONTENTS/Resources/python"
BUNDLED="$CONTENTS/Resources/python/bin/python3"
[ -x "$BUNDLED" ] || fail "the copied interpreter is not executable"

# The interpreter must resolve its prefix inside the bundle, not back at the cache it came from.
# -B everywhere the bundled interpreter runs: it must never write bytecode into the bundle.
OYMLX_APP="$APP" "$BUNDLED" -I -B -c \
    'import os, sys; assert sys.prefix.startswith(os.environ["OYMLX_APP"]), sys.prefix' \
    || fail "the bundled interpreter's sys.prefix is not inside the app"

echo "==> installing ohyesmlx into the bundled site-packages" >&2
SITE_PACKAGES=$("$BUNDLED" -I -B -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
mkdir -p "$SITE_PACKAGES"
ditto "$ROOT/ohyesmlx" "$SITE_PACKAGES/ohyesmlx"
find "$SITE_PACKAGES/ohyesmlx" -name '__pycache__' -type d -exec rm -rf {} +
find "$SITE_PACKAGES/ohyesmlx" -name '*.pyc' -delete
# The whole bundled tree is precompiled with unchecked-hash pycs, the stdlib included: -B keeps the
# backend from writing bytecode, but its child interpreters and every engine venv made from this
# interpreter import the same stdlib, and a missing .pyc there would be written into the signed
# bundle (found by check_bundle.sh, 2026-11-14). unchecked-hash pycs are never revalidated against
# source mtimes, so a copy, a zip or a read-only volume can never make one look stale.
"$BUNDLED" -I -B -m compileall -q -j 0 --invalidation-mode unchecked-hash \
    "$CONTENTS/Resources/python/lib" >&2 || fail "compileall failed"
[ -n "$(find "$SITE_PACKAGES/ohyesmlx" -name '*.pyc' -print -quit)" ] || fail "no bytecode was written"

echo "==> checking the interpreter's licence files shipped unmodified" >&2
find "$PYTHON_ROOT" -type f \( -name 'LICENSE*' -o -name 'COPYING*' \) -print |
    while IFS= read -r source; do
        copy="$CONTENTS/Resources/python/${source#"$PYTHON_ROOT"/}"
        [ -f "$copy" ] || fail "missing licence file $copy"
        cmp -s "$source" "$copy" || fail "licence file $copy differs from the tarball's"
    done

echo "==> signing ad hoc, inside-out" >&2
MAXCHOS=$(mktemp -t ohyesmlx-macho)
trap 'rm -f "$MAXCHOS"' EXIT
find "$CONTENTS/Resources/python" -type f -print |
    while IFS= read -r candidate; do
        case "$(file -b "$candidate")" in
            *Mach-O*)
                codesign --force --sign - "$candidate" >/dev/null 2>&1 ||
                    fail "could not sign $candidate"
                codesign --verify --strict "$candidate" >/dev/null 2>&1 ||
                    fail "$candidate does not verify after signing"
                printf '%s\n' "$candidate" >>"$MAXCHOS"
                ;;
        esac
    done
echo "    $(wc -l <"$MAXCHOS" | tr -d ' ') Mach-O files under Contents/Resources/python signed" >&2
[ -s "$MAXCHOS" ] || fail "no Mach-O files were found under Contents/Resources/python"
codesign --force --sign - "$CONTENTS/MacOS/OhYesMLX" || fail "could not sign the app binary"
codesign --force --sign - "$APP" || fail "could not sign the app"
codesign --verify --deep --strict --verbose=2 "$APP" || fail "codesign --verify --deep --strict failed"
echo "    codesign --verify --deep --strict: OK" >&2

echo "==> SBOM" >&2
"${PYTHON:-/usr/bin/python3}" "$ROOT/scripts/make_sbom.py" \
    --out "$SBOM" \
    --python "$BUNDLED" \
    --release-tag "$RELEASE_TAG" \
    --interpreter-url "$INTERPRETER_URL" \
    --interpreter-sha256 "$INTERPRETER_SHA256" \
    --swift-version "$SWIFT_VERSION" >&2 || fail "make_sbom.py failed"
[ -f "$SBOM" ] || fail "$SBOM was not written"

# The SBOM step runs the bundled interpreter, so the signature is the last word, not an earlier
# one: a .pyc written into the bundle breaks it (and P5-6).
codesign --verify --deep --strict "$APP" || fail "the bundle no longer verifies after the SBOM step"

echo "==> zip" >&2
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP" || fail "ditto could not write $ZIP"
[ -f "$ZIP" ] || fail "$ZIP was not written"

printf '%s\n' "$APP" "$ZIP" "$SBOM"
