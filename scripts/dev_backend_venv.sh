#!/bin/sh
# Make the development backend venv the app's launcher spawns in `swift run`.
#
# Usage: scripts/dev_backend_venv.sh [dir]
#   dir defaults to ~/.local/share/ohyesmlx/app-dev-venv
#
# The venv holds no packages. One .pth file in its site-packages names this checkout, so
# `python -I -m ohyesmlx.cli app` imports the repository without pip and without a network.
# Prints the interpreter path to export as OYMLX_DEV_PYTHON.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)
dir=${1:-"$HOME/.local/share/ohyesmlx/app-dev-venv"}

base=python3
fallback=/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python
if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    :
elif [ -x "$fallback" ]; then
    base=$fallback
    echo "python3 is older than 3.11; using the test venv's interpreter at $fallback" >&2
else
    echo "python3 is older than 3.11 and $fallback is not executable" >&2
    exit 1
fi

"$base" -m venv "$dir"

site=$("$dir/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
printf '%s\n' "$repo" > "$site/ohyesmlx-repo.pth"

"$dir/bin/python" -c 'import ohyesmlx, sys; print(sys.version.split()[0], ohyesmlx.__file__, file=sys.stderr)' >&2

echo "$dir/bin/python"
