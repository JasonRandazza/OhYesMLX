#!/bin/sh
# Sourced, not run. One sweep, by process, not by port (055-03, item 5).
#
# Every measured runner used to carry its own copy of this function, and each copy killed
# whatever held 8000/8080/8081/8100/1337 -- a user's dev server included -- while missing an
# engine on any other port (AGENTS.md, "Ports"). The decision of what is an engine is
# `runtimes._engine_of`, reached through `runtimes.resident_engines`, and the kill loop is
# `runtimes.sweep_resident_engines`; tests/test_055_03_sweep.py exercises that loop with the
# scan and the signal function monkeypatched.
#
# Needs $PY. Source it after PY is set:
#   . "$(dirname "$0")/sweep.sh"
#
# `sweep` returns non-zero when the machine cannot be confirmed clear of resident engines, and
# callers write `sweep || exit 1` outside a trap so that no column starts on a machine still
# holding another runtime's weights. It never calls `exit`: osaurus-pin.sh's signal trap runs
# `sweep; osaurus_restore`, and an exit here would skip the byte-exact Osaurus restore.

sweep() {
  : "${PY:?sweep.sh needs PY}"
  $PY -c '
from ohyesmlx import runtimes
try:
    lines = runtimes.sweep_resident_engines()
except runtimes.RuntimeLifecycleError as error:
    print("SWEEP FAILED: %s" % error)
    raise SystemExit(1)
for line in lines:
    print(line)
' || return 1
  sleep 3
}
