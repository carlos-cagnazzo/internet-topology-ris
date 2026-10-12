#!/usr/bin/env bash
# Report per-date slice status for all fleet nodes in assignments.csv.
#
# Usage: ./status.sh
#
# SSHes to each host once and checks:
#   - which tmux sessions named slice-* are running
#   - which paths/<date>/ directories exist (proxy for "done")
#
# Output per host, per assigned range:
#   slice-STARTDATE-ENDDATE  collectors  [running|done|partial|pending]  N/total
#   followed by a per-date grid (✓ done, · pending)

set -euo pipefail

FLEET="./fleet.csv"
ASSIGNMENTS="./assignments.csv"
SSH_OPTS="-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=30"

for f in "$FLEET" "$ASSIGNMENTS"; do
    [ -f "$f" ] || { echo "Error: ${f} not found." >&2; exit 1; }
done

# Expand a YYYYMMDD-YYYYMMDD range to newline-separated dates
expand_range() {
    python3 -c "
from datetime import date, timedelta
s, e = '$1', '$2'
d = date(int(s[:4]), int(s[4:6]), int(s[6:]))
e = date(int(e[:4]), int(e[4:6]), int(e[6:]))
while d <= e:
    print(d.strftime('%Y%m%d'))
    d += timedelta(1)
"
}

# Report status for one host
report_host() {
    local host="$1"

    local fleet_entry
    fleet_entry=$(awk -F, -v h="$host" \
        'NF>=3 && $1 !~ /^[[:space:]]*#/ && $2==h {
            gsub(/[[:space:]]/, "", $1); gsub(/[[:space:]]/, "", $3)
            print $1 "|" $3; exit
        }' "$FLEET")

    if [ -z "$fleet_entry" ]; then
        echo "${host}: not in fleet.csv"
        echo ""
        return
    fi
    local user repo
    IFS='|' read -r user repo <<< "$fleet_entry"

    # One SSH round-trip: get running tmux sessions + existing paths dirs
    local remote_data
    remote_data=$(ssh $SSH_OPTS "${user}@${host}" "
        echo SESSIONS
        tmux ls 2>/dev/null | grep '^slice-' | cut -d: -f1 || true
        echo PATHS
        cd '${repo}' && ls paths/ 2>/dev/null | sort || true
    " 2>/dev/null) || {
        printf "%-30s [unreachable]\n\n" "${host}"
        return
    }

    # Parse remote data into two arrays
    local running_sessions=() done_paths=() section=""
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        case "$line" in
            SESSIONS) section=sessions ;;
            PATHS)    section=paths    ;;
            *)
                [[ "$section" == sessions ]] && running_sessions+=("$line")
                [[ "$section" == paths    ]] && done_paths+=("$line")
                ;;
        esac
    done <<< "$remote_data"

    echo "${host}"

    # Get all assignments for this host
    while IFS=, read -r h start end collectors; do
        h="${h#"${h%%[![:space:]]*}"}"
        [[ -z "$h" || "$h" == \#* ]] && continue
        h="${h//[[:space:]]/}"
        [[ "$h" == "$host" ]] || continue
        start="${start//[[:space:]]/}"
        end="${end//[[:space:]]/}"
        collectors="${collectors//[[:space:]]/}"
        local session="slice-${start}-${end}"

        # Is the tmux session running?
        local is_running=false
        for s in "${running_sessions[@]+"${running_sessions[@]}"}"; do
            [[ "$s" == "$session" ]] && is_running=true && break
        done

        # Expand date range and count done dates
        local dates=()
        mapfile -t dates < <(expand_range "$start" "$end")
        local total=${#dates[@]} done_count=0

        for d in "${dates[@]}"; do
            for p in "${done_paths[@]+"${done_paths[@]}"}"; do
                [[ "$p" == "$d" ]] && (( done_count++ )) && break
            done
        done

        # Status label
        local label
        if   $is_running;                      then label="running"
        elif [ "$done_count" -eq "$total" ];   then label="done   "
        elif [ "$done_count" -gt 0 ];          then label="partial"
        else                                        label="pending"
        fi

        printf "  %-36s  %-14s  [%s  %d/%d]\n" \
            "$session" "$collectors" "$label" "$done_count" "$total"

        # Per-date grid, 7 per row
        local row="" col=0
        for d in "${dates[@]}"; do
            local mark="·"
            for p in "${done_paths[@]+"${done_paths[@]}"}"; do
                [[ "$p" == "$d" ]] && mark="✓" && break
            done
            row+="  ${d}${mark}"
            (( col++ ))
            if [ "$col" -eq 7 ]; then
                echo "   ${row}"
                row="" col=0
            fi
        done
        [ -n "$row" ] && echo "   ${row}"

    done < "$ASSIGNMENTS"
    echo ""
}

# Collect unique hosts in assignment order
hosts=()
while IFS=, read -r host _ _ _; do
    host="${host#"${host%%[![:space:]]*}"}"
    [[ -z "$host" || "$host" == \#* ]] && continue
    host="${host//[[:space:]]/}"
    local already=false
    for h in "${hosts[@]+"${hosts[@]}"}"; do
        [[ "$h" == "$host" ]] && already=true && break
    done
    $already || hosts+=("$host")
done < "$ASSIGNMENTS"

if [ ${#hosts[@]} -eq 0 ]; then
    echo "Error: no hosts found in ${ASSIGNMENTS}" >&2
    exit 1
fi

for host in "${hosts[@]}"; do
    report_host "$host"
done
