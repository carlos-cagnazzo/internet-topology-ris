#!/usr/bin/env bash
# Collect path files from fleet nodes after running 'just slice' on each.
#
# Usage: ./collect.sh YYYYMMDD|PATTERN [parallel_jobs]
#   YYYYMMDD or PATTERN  — exact date or glob (e.g. 202607* for all of July)
#   parallel_jobs        — max concurrent rsyncs (default 2)
#
# Reads fleet.csv (repo root): username,hostname,/path/to/remote/repo
# SSHes to each node to list matching paths/<date>/ dirs, then rsyncs each.
# Collector filenames are unique (include collector name) so no conflicts.
#
# Requires bash 4+ for export -f.
# macOS ships bash 3.2 — install a newer version: brew install bash

set -euo pipefail

DATE="${1:?Usage: $0 YYYYMMDD|PATTERN [parallel_jobs]}"
if [[ ! "$DATE" =~ ^[0-9]{4} ]]; then
    echo "Error: date must start with a 4-digit year, got: '${DATE}'" >&2
    echo "  Examples: 20260701  202607*  2026*" >&2
    echo "  Hint: variable assignments must come BEFORE the recipe name: just date=YYYYMMDD collect" >&2
    exit 1
fi
JOBS="${2:-2}"
FLEET="./fleet.csv"
# Strip glob metacharacters for use in the log directory name
LOG_DATE="${DATE//[\*\?\[\]]/}"
LOG_DIR="./logs/collect-${LOG_DATE}"
PATHS_DIR="./paths"

if [ ! -f "$FLEET" ]; then
    echo "Error: ${FLEET} not found." >&2
    echo "Create it from fleet.csv.example — lines: username,hostname,/path/to/repo" >&2
    exit 1
fi

mkdir -p "$LOG_DIR" "$PATHS_DIR"

collect_host() {
    local user="$1" host="$2" repo="$3"
    local log="${LOG_DIR}/${host}.log"
    echo "[${host}] starting → ${log}"

    # List matching date directories on the remote.
    # The glob in ${DATE} is intentionally unquoted so the remote shell expands it.
    local dirs
    dirs=$(ssh "${user}@${host}" "ls -d ${repo}/paths/${DATE} 2>/dev/null" || true)

    if [ -z "$dirs" ]; then
        echo "[${host}] no directories match paths/${DATE} — skipping"
        return 0
    fi

    local count=0 failed=0
    while IFS= read -r remote_dir; do
        local date_name
        date_name=$(basename "$remote_dir")
        mkdir -p "${PATHS_DIR}/${date_name}"
        echo "[${host}] syncing ${date_name}..."
        if rsync -az \
            "${user}@${host}:${remote_dir}/" \
            "${PATHS_DIR}/${date_name}/" \
            >> "${log}" 2>&1; then
            (( count++ )) || true
        else
            failed=1
        fi
    done <<< "$dirs"

    if [ "$failed" -eq 0 ]; then
        echo "[${host}] done (${count} date dir(s))"
    else
        echo "[${host}] FAILED — check ${log}"
        return 1
    fi
}

export -f collect_host
export LOG_DIR DATE PATHS_DIR

# Read CSV — skip blank lines and lines starting with #
entries=()
while IFS=, read -r user host repo; do
    # Strip leading whitespace to catch indented comments
    user="${user#"${user%%[![:space:]]*}"}"
    [[ -z "$user" || "$user" == \#* ]] && continue
    # Strip any accidental whitespace from all three fields
    host="${host//[[:space:]]/}"
    repo="${repo//[[:space:]]/}"
    entries+=("${user// /}|${host}|${repo}")
done < "$FLEET"

if [ ${#entries[@]} -eq 0 ]; then
    echo "Error: no entries found in ${FLEET}" >&2
    exit 1
fi

echo "Collecting paths/${DATE}/ from ${#entries[@]} host(s) — ${JOBS} in parallel"
echo "Output : ${PATHS_DIR}/"
echo "Logs   : ${LOG_DIR}/"
echo ""

# Collect failures via a temp file (append is atomic for small writes)
tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

printf '%s\n' "${entries[@]}" | xargs -P "$JOBS" -I{} bash -c '
    IFS="|" read -r user host repo <<< "$1"
    collect_host "$user" "$host" "$repo" || echo "$host" >> "'"$tmpfile"'"
' _ {}

echo ""
if [ -s "$tmpfile" ]; then
    echo "FAILED hosts:"
    while IFS= read -r h; do echo "  $h"; done < "$tmpfile"
    exit 1
fi
echo "All done."
