# ┌─────────────────────────────────────────────────────────────────────┐
# │  Internet AS-Level Topology Pipeline                                │
# │                                                                     │
# │  Reconstructs the Internet's AS-level topology from RIPE RIS BGP   │
# │  data. Downloads MRT RIB snapshots from route collectors, extracts  │
# │  AS paths, and produces a deduplicated undirected edge list where   │
# │  each line represents a peering link between two Autonomous Systems.│
# │                                                                     │
# │  Created: 2026-03-16                                                │
# └─────────────────────────────────────────────────────────────────────┘
#
# Usage: just [variable=value ...] [recipe]
#   NOTE: variable assignments must come BEFORE the recipe name.
#
# Examples:
#   just date=20240101 pipeline
#   just date=20240101 collectors=rrc00,rrc01,rrc04 pipeline
#   just date=20240101 collectors=rrc00-rrc10 pipeline
#   just date=20240101 collectors=rrc00-rrc05,rrc11,rrc23 pipeline
#   just date=20240101 collectors=rrc00-rrc25 download
#   just date=20240101 process
#   just date=20240101 topology
#
# Fleet / distributed use:
#   On each node: just date=20240101 collectors=<slice> slice
#   Then rsync path files back and run: just date=20240101 topology

collectors := "rrc00"
date       := ""
mrt_dir    := "./mrt"
paths_dir  := "./paths"
output_dir := "./output"
output     := "topology-" + date + ".txt"
output_v4  := "topology-" + date + "-v4.txt"
output_v6  := "topology-" + date + "-v6.txt"
pubpoint   := "/var/www/html/topo"
jobs       := "2"
workers    := ""
paths      := ""

# List available recipes
default:
    @just --list

# Run the full pipeline: download (RIS + RouteViews) → process → topology
pipeline: (download) (download-routeviews) (process) (topology)

# Step 1a — Download bview RIB snapshots from RIS collectors
download:
    uv run get-mrt.py \
        --collectors {{ collectors }} \
        --date {{ date }} \
        --output-dir {{ mrt_dir }}/{{ date }}

# Step 1b — Download RIB snapshots from RouteViews collectors
# This is a working subset of ~40 available collectors.
# To add more, extend the --collectors list below.
# Full collector index: https://www.routeviews.org/routeviews/index.php/collectors/
download-routeviews:
    uv run get-routeviews.py \
        --collectors route-views.amsix,ix-br2.gru,namex.fco,route-views2,route-views.sg,\
                     crix.sjo,hkix.hkg,route-views.chicago,route-views.kixp,route-views.rio,route-views.perth,pacwave.lax \
        --date {{ date }} \
        --output-dir {{ mrt_dir }}/{{ date }}

# Step 2 — Extract AS paths from downloaded MRT files (handles .gz and .bz2)
process:
    uv run extract-paths.py \
        --input-files "{{ mrt_dir }}/{{ date }}/*.gz" \
        --output-dir {{ paths_dir }}/{{ date }}
    uv run extract-paths.py \
        --input-files "{{ mrt_dir }}/{{ date }}/*.bz2" \
        --output-dir {{ paths_dir }}/{{ date }}

# Fleet slice: download (RIS + RouteViews) + process for the given date and collectors.
# Each node is self-contained: downloads both RIS and RouteViews for its assigned dates.
slice: (download) (download-routeviews) (process)

# Dispatch slice jobs to fleet nodes (reads assignments.csv + fleet.csv)
dispatch:
    ./dispatch.sh {{ jobs }}

# Report per-date slice status for all fleet nodes
status:
    ./status.sh

# Collect path files from all fleet nodes into ./paths/<date>/ (reads fleet.csv)
collect:
    ./collect.sh '{{ date }}' {{ jobs }}

# Step 3 — Build combined + per-AF topology edge lists
topology: (topology-combined) (topology-v4) (topology-v6)

# Step 3a — Combined topology (all prefixes)
# date accepts a glob: just date='202607*' topology-combined
# workers controls parallelism/memory: just workers=2 topology-combined
# paths writes a consolidated paths file: just paths=1 topology-combined
topology-combined:
    #!/usr/bin/env bash
    set -euo pipefail
    safe="{{ date }}"; safe="${safe//[\*\?\[\]]/}"
    date_flag="";    [[ "{{ date }}"    =~ ^[0-9]{8}$ ]] && date_flag="--date {{ date }}"
    workers_flag=""; [[ -n "{{ workers }}" ]]             && workers_flag="--workers {{ workers }}"
    paths_flag="";   [[ -n "{{ paths }}" ]]               && paths_flag="--paths"
    mkdir -p "{{ output_dir }}/${safe}"
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        $date_flag $workers_flag $paths_flag \
        --input "{{ paths_dir }}/{{ date }}/*.txt.gz" \
        --output "{{ output_dir }}/${safe}/topology-${safe}.txt"

# Step 3b — IPv4-only topology
# date accepts a glob: just date='202607*' topology-v4
# workers controls parallelism/memory: just workers=2 topology-v4
topology-v4:
    #!/usr/bin/env bash
    set -euo pipefail
    safe="{{ date }}"; safe="${safe//[\*\?\[\]]/}"
    date_flag="";    [[ "{{ date }}"    =~ ^[0-9]{8}$ ]] && date_flag="--date {{ date }}"
    workers_flag=""; [[ -n "{{ workers }}" ]]             && workers_flag="--workers {{ workers }}"
    mkdir -p "{{ output_dir }}/${safe}"
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        $date_flag $workers_flag \
        --input "{{ paths_dir }}/{{ date }}/*.v4.txt.gz" \
        --output "{{ output_dir }}/${safe}/topology-${safe}-v4.txt"

# Step 3c — IPv6-only topology
# date accepts a glob: just date='202607*' topology-v6
# workers controls parallelism/memory: just workers=2 topology-v6
topology-v6:
    #!/usr/bin/env bash
    set -euo pipefail
    safe="{{ date }}"; safe="${safe//[\*\?\[\]]/}"
    date_flag="";    [[ "{{ date }}"    =~ ^[0-9]{8}$ ]] && date_flag="--date {{ date }}"
    workers_flag=""; [[ -n "{{ workers }}" ]]             && workers_flag="--workers {{ workers }}"
    mkdir -p "{{ output_dir }}/${safe}"
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        $date_flag $workers_flag \
        --input "{{ paths_dir }}/{{ date }}/*.v6.txt.gz" \
        --output "{{ output_dir }}/${safe}/topology-${safe}-v6.txt"

# Remove .edges and .paths.gz checkpoint sidecars left by an interrupted topology build
# date accepts a glob: just date='202607*' clean-edges
clean-edges:
    #!/usr/bin/env bash
    set -euo pipefail
    count=$(find "{{ paths_dir }}/{{ date }}" \( -name "*.edges" -o -name "*.paths.gz" \) 2>/dev/null | wc -l | tr -d ' ')
    if [ "$count" -eq 0 ]; then
        echo "No .edges / .paths.gz sidecar files found under {{ paths_dir }}/{{ date }}"
        exit 0
    fi
    echo "Deleting ${count} checkpoint sidecar(s) under {{ paths_dir }}/{{ date }} ..."
    find "{{ paths_dir }}/{{ date }}" \( -name "*.edges" -o -name "*.paths.gz" \) -delete
    echo "Done."

# Start JupyterLab bound to the Tailscale interface
lab2:
    uv run jupyter lab --ip 100.98.4.21 --no-browser --notebook-dir ./ --IdentityProvider.token=''

# Start JupyterLab bound to the Tailscale interface
lab:
    uv run jupyter lab --ip 0.0.0.0 --no-browser --notebook-dir ./ --IdentityProvider.token=''

# Pack output products for a given date and publish to pubpoint
pack-and-publish:
    #!/usr/bin/env bash
    set -euo pipefail
    archive="topology-{{ date }}.tar.bz2"
    dest="{{ pubpoint }}/${archive}"
    if [ -z "{{ date }}" ]; then
        echo "Error: date is required. Usage: just date=YYYYMMDD pack-and-publish" >&2
        exit 1
    fi
    if [ ! -d "{{ output_dir }}/{{ date }}" ]; then
        echo "Error: output directory {{ output_dir }}/{{ date }} does not exist." >&2
        exit 1
    fi
    echo "Packing {{ output_dir }}/{{ date }}/ → ${archive} ..."
    sed "s/{date}/{{ date }}/g" DATA-README.md > "{{ output_dir }}/{{ date }}/README.md"
    tar -cjf "${archive}" -C "{{ output_dir }}/{{ date }}" .
    rm -f "{{ output_dir }}/{{ date }}/README.md"
    echo "$(tar -tjf "${archive}" | wc -l) files packed."
    if [ -e "${dest}" ]; then
        read -r -p "  ${dest} already exists. Overwrite? [y/N] " confirm
        if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
            echo "Aborted."
            rm -f "${archive}"
            exit 1
        fi
    fi
    sudo cp "${archive}" "${dest}"
    rm -f "${archive}"
    echo "Published → ${dest}"
