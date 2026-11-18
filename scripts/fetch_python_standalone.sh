#!/bin/sh
# The committed record of the one download the .app bundle needs (AGENTS.md, "Downloads need a
# reason and a record"): python-build-standalone CPython 3.14.10 arm64, the interpreter every
# engine venv is made from and the one the pip constraints were frozen with (plan 05-06, AC-1;
# decision D6).
#
#   scripts/fetch_python_standalone.sh              fetch, verify, unpack; print the python root
#   scripts/fetch_python_standalone.sh --identity   print the pinned facts as KEY=VALUE lines
#
# The tarball is cached under ~/Library/Caches/OhYesMLX/build/ so a rebuild never downloads it
# again. The sha256 is checked before anything is unpacked: a mismatch unpacks nothing and exits
# non-zero. The tree is unpacked into a fresh temporary directory on every run and the caller
# removes it: a cached tree lives in a user-writable place, is mutated by ordinary use (a pip
# install, an edited stdlib file, a planted .pth) and would be copied into the bundle while the
# SBOM names this tarball's sha256 (S6-F2).
set -eu

RELEASE_TAG="20261026"
TARBALL="cpython-3.14.10+20261026-aarch64-apple-darwin-install_only.tar.gz"
SHA256="30a18bcb9ab75e485b4bf4e5d783dde165571e7e42c56dff47a2d2c5345183a4"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/${TARBALL}"

CACHE="${HOME}/Library/Caches/OhYesMLX/build"
ARCHIVE="${CACHE}/${TARBALL}"

case "${1:-}" in
    --identity)
        printf 'release=%s\n' "$RELEASE_TAG"
        printf 'tarball=%s\n' "$TARBALL"
        printf 'url=%s\n' "$URL"
        printf 'sha256=%s\n' "$SHA256"
        exit 0
        ;;
    "") ;;
    *)
        echo "usage: $0 [--identity]" >&2
        exit 2
        ;;
esac

if [ "$(uname -m)" != "arm64" ]; then
    echo "$0: the bundle ships an arm64 interpreter; this Mac is $(uname -m)" >&2
    exit 1
fi

digest() {
    shasum -a 256 "$1" | awk '{print $1}'
}

mkdir -p "$CACHE"

if [ -f "$ARCHIVE" ]; then
    actual=$(digest "$ARCHIVE")
    if [ "$actual" != "$SHA256" ]; then
        echo "$0: the cached tarball does not match the pinned sha256; fetching it again" >&2
        rm -f "$ARCHIVE"
    fi
fi

if [ ! -f "$ARCHIVE" ]; then
    echo "$0: fetching ${URL}" >&2
    curl -fsSL --retry 3 --retry-delay 2 -o "${ARCHIVE}.part" "$URL"
    actual=$(digest "${ARCHIVE}.part")
    if [ "$actual" != "$SHA256" ]; then
        rm -f "${ARCHIVE}.part"
        echo "$0: sha256 mismatch for ${TARBALL}: expected ${SHA256}, got ${actual}; nothing was unpacked" >&2
        exit 1
    fi
    mv "${ARCHIVE}.part" "$ARCHIVE"
fi

# Never reuse an unpacked tree: bin/python3 being executable is no evidence that the tree is the
# verified tarball's, and it is the tree the bundle copies. Unpack the bytes just verified, into a
# directory this run made, and let the caller delete it (scripts/build_app.sh does, on exit).
FRESH=$(mktemp -d "${TMPDIR:-/tmp}/ohyesmlx-python.XXXXXX")
tar -xzf "$ARCHIVE" -C "$FRESH"
if [ ! -x "${FRESH}/python/bin/python3" ]; then
    rm -rf "$FRESH"
    echo "$0: ${TARBALL} did not unpack a python/bin/python3" >&2
    exit 1
fi

printf '%s\n' "${FRESH}/python"
