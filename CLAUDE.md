# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Reconstruct Internet AS-level topology from RIPE RIS MRT files. The pipeline downloads binary MRT files, extracts AS paths using `bgpreader`, and produces a deduplicated edge list (`AS1 AS2` per line).

## Commands

```bash
# Run a script
uv run get-mrt.py --collectors rrc00,rrc01 --date 20240101

# Add a dependency
uv add typer

# Run with inline dependency (before pyproject.toml is updated)
uv run --with typer get-mrt.py
```

## Tech Stack

- **Python 3.12+** via `uv`
- **typer** for CLI and colorful output
- **bgpreader** (system binary) for parsing MRT files

## bgpreader Usage

To read a single local MRT file and extract elements:

```bash
bgpreader -d singlefile -o mrt-file=<path> -e
```

Key flags: `-d singlefile` selects the file interface; `-o mrt-file=<path>` sets the file; `-e` outputs per-element records (default). The output columns include record type, element type, timestamps, collector, peer info, prefix, and AS path.

## Pipeline Architecture

Three scripts forming a linear pipeline:

1. **`get-mrt.py`** — Downloads `.gz` MRT files from `https://data.ris.ripe.net/rrcXX/YYYY.MM/TYPE.YYYYMMDD.HHmm.gz`. Flags: `--collectors` (comma-separated rrcXX list), `--date` (YYYYMMDD), `--output-dir` (default `./mrt`). Skips already-downloaded files. Only downloads **RIB snapshots** (`bview` type), specifically the **00:00 UTC** snapshot for the given date.

2. **`process-mrt.py`** — Calls `bgpreader` on each `.gz` file to extract AS paths, writing `.txt` sidecar files in `--output-dir` (default `./paths`). Each line of the output file contains **only the AS path string** (space-separated ASNs). Skips files whose `.txt` already exists.

3. **`build-topology.py`** *(planned)* — Reads `.txt` path files (via `--input` glob), extracts edges from AS paths, and emits a deduplicated undirected `AS1 AS2` edge list. Links are undirected: `AS1 AS2` and `AS2 AS1` are the same edge.

## Conventions

- All scripts: measure and display total execution time on exit; show progress when processing multiple files; include inline docstrings and rich `--help` output.
- `--collectors` is a mandatory argument with no default.
- AS path processing rules:
  - Collapse consecutive duplicate ASNs before extracting edges (remove prepending): `A A B C` → treat as `A B C`.
  - AS sets (e.g., `{64500,64501}`) are skipped as segment endpoints: truncate the path at the AS set, keeping edges from segments before it. E.g., `A B {C,D} E` → only edge `(A,B)`.
  - Store edges as sorted tuples to deduplicate regardless of direction: `(min(A,B), max(A,B))`.
- `bview` files are the RIB snapshot type used by RIS.

## RIS Data

- Collectors: `rrc00` through `rrc25`
- URL pattern: `https://data.ris.ripe.net/rrcXX/YYYY.MM/TYPE.YYYYMMDD.HHmm.gz`
