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
#   just date=20240101 collectors=rrc00-rrc05,rrc11,rrc23 output="topology-20240101.txt" pipeline
#   just date=20240101 collectors=rrc00-rrc25 download
#   just date=20240101 process
#   just date=20240101 topology

collectors := "rrc00"
date       := ""
mrt_dir    := "./mrt"
mrt_ext    := "gz"
paths_dir  := "./paths"
output_dir := "./output"
output     := "topology.txt"
output_v4  := "topology-v4.txt"
output_v6  := "topology-v6.txt"

# List available recipes
default:
    @just --list

# Run the full pipeline: download → process → topology
pipeline: (download) (process) (topology)

# Step 1 — Download bview RIB snapshots from RIS collectors
download:
    uv run get-mrt.py \
        --collectors {{ collectors }} \
        --date {{ date }} \
        --output-dir {{ mrt_dir }}/{{ date }}

# Step 2 — Extract AS paths from downloaded MRT files
process:
    uv run process-mrt.py \
        --input-files "{{ mrt_dir }}/{{ date }}/*.{{ mrt_ext }}" \
        --output-dir {{ paths_dir }}/{{ date }}

# Step 3 — Build combined + per-AF topology edge lists
topology: (topology-combined) (topology-v4) (topology-v6)

# Step 3a — Combined topology (all prefixes)
topology-combined:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --input "{{ paths_dir }}/{{ date }}/*.gz.txt" \
        --output {{ output_dir }}/{{ date }}/{{ output }}

# Step 3b — IPv4-only topology
topology-v4:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --input "{{ paths_dir }}/{{ date }}/*.gz.v4.txt" \
        --output {{ output_dir }}/{{ date }}/{{ output_v4 }}

# Step 3c — IPv6-only topology
topology-v6:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --input "{{ paths_dir }}/{{ date }}/*.gz.v6.txt" \
        --output {{ output_dir }}/{{ date }}/{{ output_v6 }}
