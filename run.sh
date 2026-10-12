#!/usr/bin/env bash
# run.sh — Run a pipeline or analysis Python script via uv without knowing its directory.
#
# Usage: ./run.sh <script.py> [args...]
#
# Searches pipeline/, analysis/, and fleet/ in that order.
# Direct invocation is always also valid: uv run pipeline/script.py [args...]

set -euo pipefail

if [[ $# -eq 0 ]]; then
    printf 'Usage: ./run.sh <script.py> [args...]\n' >&2
    exit 1
fi

script="$1"
shift

for dir in pipeline analysis fleet; do
    if [[ -f "$dir/$script" ]]; then
        exec uv run "$dir/$script" "$@"
    fi
done

printf "error: '%s' not found in pipeline/, analysis/, or fleet/\n" "$script" >&2
printf 'Available scripts:\n' >&2
find pipeline analysis fleet -name "*.py" 2>/dev/null | sort | sed 's|.*/||; s/^/  /' >&2
exit 1
