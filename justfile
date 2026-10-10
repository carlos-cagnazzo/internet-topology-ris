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

# Fleet slice: download + process for the given collectors only (no topology step).
# Run on each node in a distributed setup; collect path files centrally, then run topology.
slice: (download) (process)

# Step 3 — Build combined + per-AF topology edge lists
topology: (topology-combined) (topology-v4) (topology-v6)

# Step 3a — Combined topology (all prefixes)
topology-combined:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --date {{ date }} \
        --input "{{ paths_dir }}/{{ date }}/*.gz.txt" \
        --input "{{ paths_dir }}/{{ date }}/*.bz2.txt" \
        --output {{ output_dir }}/{{ date }}/{{ output }}

# Step 3b — IPv4-only topology
topology-v4:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --date {{ date }} \
        --input "{{ paths_dir }}/{{ date }}/*.gz.v4.txt" \
        --input "{{ paths_dir }}/{{ date }}/*.bz2.v4.txt" \
        --output {{ output_dir }}/{{ date }}/{{ output_v4 }}

# Step 3c — IPv6-only topology
topology-v6:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --date {{ date }} \
        --input "{{ paths_dir }}/{{ date }}/*.gz.v6.txt" \
        --input "{{ paths_dir }}/{{ date }}/*.bz2.v6.txt" \
        --output {{ output_dir }}/{{ date }}/{{ output_v6 }}

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
