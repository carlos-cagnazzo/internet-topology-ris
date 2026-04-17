#!/usr/bin/env bash
set -euo pipefail

# Remote sources — add one rsync URL per machine pointing to its output/ dir.
# Format: user@host:/path/to/output/  or  rsync://host/module/output/
SOURCES=(
    # carlos@machine1.example.com:/home/carlos/src/internet-topology-ris/output/
    # carlos@machine2.example.com:/home/carlos/src/internet-topology-ris/output/
    carlos@jordan.in.xt6.us:/home/carlos/internet-topology-ris/output
    carlos@yacare.in.xt6.us:/home/carlos/checkouts/internet-topology-ris/output
    carlos@atl01.xt6.us:/home/carlos/src/internet-topology-ris/output
    carlos@gauss.xt6labs.io:/home/carlos/src/internet-topology-ris/output
    carlos@euler.in.xt6.us:/home/carlos/src/internet-topology-ris/output
)

# Files to fetch (rsync include patterns — one per line)
INCLUDES=(
    "topology*-asns.txt"
    "topology-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].txt"
)

# Files to skip (rsync exclude pattern) — applied after include
EXCLUDE="*.topcache*"

# Local destination root — per-host subdirs are created automatically
DEST_ROOT="./fetch"

# ---------------------------------------------------------------------------

failed=()

for src in "${SOURCES[@]}"; do
    # Extract hostname: strip user@ prefix and :/path suffix
    host="${src##*@}"   # remove user@
    host="${host%%:*}"  # remove :/path

    dest="${DEST_ROOT}/${host}"
    echo "==> ${host}: syncing ${src} -> ${dest}/"

    if rsync \
        --archive \
        --compress \
        --mkpath \
        --include="*/" \
        $(printf -- '--include=%s\n' "${INCLUDES[@]}") \
        --exclude="${EXCLUDE}" \
        --exclude="*" \
        --progress \
        "${src}" "${dest}/"; then
        echo "==> ${host}: done"
    else
        echo "==> ${host}: FAILED (exit $?)" >&2
        failed+=("${host}")
    fi

    echo
done

if (( ${#failed[@]} > 0 )); then
    echo "FAILED hosts: ${failed[*]}" >&2
    exit 1
fi
