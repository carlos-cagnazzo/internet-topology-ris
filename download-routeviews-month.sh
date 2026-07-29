#!/usr/bin/env bash
# Download one RouteViews bview per day for a given year-month.
# Usage: ./download-routeviews-month.sh YYYYMM [parallel_jobs]
# Example: ./download-routeviews-month.sh 202504

set -euo pipefail

YEARMONTH="${1:?Usage: $0 YYYYMM [parallel_jobs]}"
JOBS="${2:-4}"
MRT_DIR="./mrt-routeviews"
LOG_DIR="./logs/routeviews-${YEARMONTH}"

YEAR="${YEARMONTH:0:4}"
MONTH="${YEARMONTH:4:2}"

mkdir -p "$LOG_DIR"

# Build list of dates for the month
dates=()
day=1
while true; do
    date_str=$(printf "%s%s%02d" "$YEAR" "$MONTH" "$day")
    # Validate the date exists (handles months with 28/29/30/31 days)
    if ! date -d "${YEAR}-${MONTH}-$(printf '%02d' $day)" &>/dev/null 2>&1; then
        break
    fi
    dates+=("$date_str")
    day=$((day + 1))
done

echo "Downloading RouteViews bviews for ${YEARMONTH} — ${#dates[@]} days, ${JOBS} in parallel"
echo "Output dir: ${MRT_DIR}"
echo "Logs: ${LOG_DIR}"
echo ""

download_day() {
    local d="$1"
    local log="${LOG_DIR}/${d}.log"
    echo "[${d}] starting → ${log}"
    if just mrt_dir="${MRT_DIR}" date="${d}" download-routeviews > "${log}" 2>&1; then
        echo "[${d}] done"
    else
        echo "[${d}] FAILED — check ${log}"
    fi
}

export -f download_day
export LOG_DIR MRT_DIR

printf '%s\n' "${dates[@]}" | xargs -P "$JOBS" -I{} bash -c 'download_day "$@"' _ {}

echo ""
echo "All done."
