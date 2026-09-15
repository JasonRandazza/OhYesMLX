#!/bin/sh
# Dispatch a work order to Command Code with the cached preamble in front.
#
#   .paul/orders/dispatch.sh implement order-file.md [logfile]
#
# The preamble is byte-identical on every call, so it lands as a DeepSeek prompt-cache
# prefix at $0.003/M instead of $0.15/M. Order text goes AFTER it — never before, or the
# prefix stops matching and every order pays full input price.
#
# Roles: implement | refactor | test | explain | review.
# `explain` and `review` run read-only and cannot write a file; a research task that must
# produce one needs `implement`.
set -eu
role=$1
order=$2
log=${3:-/dev/stdout}
here=$(dirname "$0")
cc-agent "$role" "$(cat "$here/PREAMBLE.md" "$order")" >"$log" 2>&1
