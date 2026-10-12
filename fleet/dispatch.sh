#!/usr/bin/env bash
# Dispatch slice jobs to fleet nodes based on assignments.csv.
#
# Usage: ./dispatch.sh [parallel_jobs]
#   parallel_jobs — max concurrent dispatches (default 2)
#
# Reads fleet.csv for user+repo per host.
# Reads assignments.csv for date ranges and collector assignments.
#
# For each assignment line, starts one tmux session on the target host
# named slice-STARTDATE-ENDDATE. The session loops through all dates in
# the range serially, running 'just slice' for each. Multiple lines per
# host = multiple parallel sessions on that host.
#
# Re-running is idempotent: sessions that already exist are skipped.
# Requires bash 4+, python3, and tmux on all fleet nodes.

set -euo pipefail

JOBS="${1:-2}"
FLEET="./fleet.csv"
ASSIGNMENTS="./assignments.csv"
SSH_OPTS="-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=30"

for f in "$FLEET" "$ASSIGNMENTS"; do
    if [ ! -f "$f" ]; then
        echo "Error: ${f} not found." >&2
        case "$f" in
            *fleet*)       echo "  Create it from fleet/fleet.csv.example" >&2 ;;
            *assignments*) echo "  Create it from fleet/assignments.csv.example" >&2 ;;
        esac
        exit 1
    fi
done

# Build entries array: "host|user|repo|start|end|collectors"
# Looks up user+repo from fleet.csv by hostname.
entries=()
while IFS=, read -r ahost start end collectors; do
    ahost="${ahost#"${ahost%%[![:space:]]*}"}"
    [[ -z "$ahost" || "$ahost" == \#* ]] && continue
    ahost="${ahost//[[:space:]]/}"
    start="${start//[[:space:]]/}"
    end="${end//[[:space:]]/}"
    collectors="${collectors//[[:space:]]/}"

    fleet_entry=$(awk -F, -v h="$ahost" \
        'NF>=3 && $1 !~ /^[[:space:]]*#/ && $2==h {
            gsub(/[[:space:]]/, "", $1); gsub(/[[:space:]]/, "", $3)
            print $1 "|" $3; exit
        }' "$FLEET")

    if [ -z "$fleet_entry" ]; then
        echo "Warning: ${ahost} not found in fleet.csv — skipping" >&2
        continue
    fi
    entries+=("${ahost}|${fleet_entry}|${start}|${end}|${collectors}")
done < "$ASSIGNMENTS"

if [ ${#entries[@]} -eq 0 ]; then
    echo "Error: no valid assignments found in ${ASSIGNMENTS}" >&2
    exit 1
fi

echo "Dispatching ${#entries[@]} session(s) — ${JOBS} in parallel"
echo ""

dispatch_one() {
    local raw="$1"
    IFS='|' read -r host user repo start end collectors <<< "$raw"
    local session="slice-${start}-${end}"

    # Skip if session already running on remote
    if ssh $SSH_OPTS "${user}@${host}" "tmux has-session -t '${session}' 2>/dev/null"; then
        echo "[${host}] ${session}: already running — skipped"
        return 0
    fi

    # Expand date range to space-separated list
    local date_list
    date_list=$(python3 -c "
from datetime import date, timedelta
s, e = '${start}', '${end}'
d = date(int(s[:4]), int(s[4:6]), int(s[6:]))
e = date(int(e[:4]), int(e[4:6]), int(e[6:]))
r = []
while d <= e:
    r.append(d.strftime('%Y%m%d'))
    d += timedelta(1)
print(' '.join(r))
")

    # Write the slice script to a temp file on the remote and start it in tmux.
    # Variables expanded locally: repo, date_list, collectors, session.
    # Escaped with \$: HOME, PATH, d — these must stay as variables in the remote script.
    local script_file="/tmp/dispatch-${session}.sh"
    cat <<ENDSCRIPT | ssh $SSH_OPTS "${user}@${host}" \
        "cat > '${script_file}' && chmod +x '${script_file}' && tmux new-session -d -s '${session}' '${script_file}'"
#!/usr/bin/env bash
export PATH="\$HOME/.cargo/bin:\$HOME/.local/bin:/usr/local/bin:\$PATH"
set -euo pipefail
cd ${repo}
git pull -q
for d in ${date_list}; do
    printf '[%s] %s starting (${collectors})\n' "\$(date +%H:%M:%S)" "\$d"
    just date=\$d collectors=${collectors} slice
    printf '[%s] %s done\n' "\$(date +%H:%M:%S)" "\$d"
done
echo '[DONE] ${session}'
ENDSCRIPT

    local nd
    nd=$(echo "$date_list" | wc -w | tr -d ' ')
    echo "[${host}] ${session}: dispatched (${nd} date(s), collectors: ${collectors})"
}

export -f dispatch_one
export SSH_OPTS

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

printf '%s\n' "${entries[@]}" | xargs -P "$JOBS" -I{} bash -c '
    dispatch_one "$1" || echo "$1" >> "'"$tmpfile"'"
' _ {}

echo ""
if [ -s "$tmpfile" ]; then
    echo "FAILED dispatches:"
    while IFS= read -r e; do
        IFS='|' read -r host _ _ start end _ <<< "$e"
        echo "  ${host}: slice-${start}-${end}"
    done < "$tmpfile"
    exit 1
fi
echo "All dispatched."
