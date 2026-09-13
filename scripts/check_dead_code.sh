#!/usr/bin/env bash
# Run deadcode over the repository and turn its output into an exit status.
#
# KLUDGE: both the pinned interpreter and the output sniffing work around an
# unmaintained tool. deadcode always exits 0 — even when it crashes — so only
# its output reveals the outcome, and its latest release (2.4.1, Aug 2024) uses
# the `ast.Str` alias Python 3.14 removed, so it cannot run on the newer
# supported interpreters (3.14+). Pinning the version too keeps the gate
# reproducible now that the tool is deliberately absent from `uv.lock`. Replace
# all of this with a plain `uv run <tool>` once deadcode supports current
# Python, or swap in a maintained analyzer.
set -uo pipefail

output=$(uvx --python 3.13 --from deadcode==2.4.1 deadcode src tests examples 2>&1)
echo "$output"

if grep -q "DC0" <<<"$output"; then
    exit 1
fi

if ! grep -q "Well done" <<<"$output"; then
    echo "check_dead_code: deadcode did not run to completion" >&2
    exit 1
fi
