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
#   just process
#   just topology

collectors := "rrc00"
date       := ""
mrt_dir    := "./mrt"
paths_dir  := "./paths"
output_dir := "./output"
output     := "topology.txt"

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
        --output-dir {{ mrt_dir }}

# Step 2 — Extract AS paths from downloaded MRT files
process:
    uv run process-mrt.py \
        --input-files "{{ mrt_dir }}/*.gz" \
        --output-dir {{ paths_dir }}

# Step 3 — Build deduplicated AS-level topology edge list
topology:
    uv run build-topology.py \
        --justify-output \
        --filter-registered \
        --input "{{ paths_dir }}/*.txt" \
        --output {{ output_dir }}/{{ output }}
