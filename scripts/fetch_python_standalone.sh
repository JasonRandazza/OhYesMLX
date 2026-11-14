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
# non-zero. The unpacked tree is cached beside the tarball for the same reason.
set -eu

RELEASE_TAG="20261026"
TARBALL="cpython-3.14.10+20261026-aarch64-apple-darwin-install_only.tar.gz"
SHA256="30a18bcb9ab75e485b4bf4e5d783dde165571e7e42c56dff47a2d2c5345183a4"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/${TARBALL}"

CACHE="${HOME}/Library/Caches/OhYesMLX/build"
ARCHIVE="${CACHE}/${TARBALL}"
UNPACKED="${CACHE}/${TARBALL%-install_only.tar.gz}"

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

if [ ! -x "${UNPACKED}/python/bin/python3" ]; then
    rm -rf "${UNPACKED}.tmp"
    mkdir -p "${UNPACKED}.tmp"
    tar -xzf "$ARCHIVE" -C "${UNPACKED}.tmp"
    if [ ! -x "${UNPACKED}.tmp/python/bin/python3" ]; then
        rm -rf "${UNPACKED}.tmp"
        echo "$0: ${TARBALL} did not unpack a python/bin/python3" >&2
        exit 1
    fi
    rm -rf "$UNPACKED"
    mv "${UNPACKED}.tmp" "$UNPACKED"
fi

printf '%s\n' "${UNPACKED}/python"
