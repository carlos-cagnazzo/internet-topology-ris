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
# Usage: just [recipe] [variable=value ...]
#
# Examples:
#   just pipeline date=20240101
#   just pipeline date=20240101 collectors=rrc00,rrc01,rrc04
#   just download date=20240101 collectors=rrc00,rrc04
#   just process
#   just topology

collectors := "rrc00"
date       := ""
mrt_dir    := "./mrt"
paths_dir  := "./paths"
output     := "./topology.txt"

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
        --input "{{ paths_dir }}/*.txt" \
        --output {{ output }}
