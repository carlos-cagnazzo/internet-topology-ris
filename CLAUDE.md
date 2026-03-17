# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Reconstruct Internet AS-level topology from RIPE RIS MRT files. The pipeline downloads binary MRT files, extracts AS paths using `bgpreader`, and produces a deduplicated edge list (`AS1 AS2` per line).

## Commands

```bash
# Run the full pipeline via just
just date=20240101 pipeline
just date=20240101 collectors=rrc00,rrc01,rrc04 pipeline

# Run individual steps
just date=20240101 collectors=rrc00 download
just process
just topology

# Run a script directly
uv run get-mrt.py --collectors rrc00,rrc01 --date 20240101

# Add a dependency
uv add <package>
```

## Tech Stack

- **Python 3.12+** via `uv`
- **typer** + **rich** for CLI and colorful output
- **httpx** for streaming HTTP downloads
- **bgpreader** (system binary) for parsing MRT files
- **just** for pipeline orchestration

## bgpreader Usage

To read a single local RIB (bview) file:

```bash
bgpreader -d singlefile -o rib-file=<path>
```

Output is `|`-delimited. Column indices (0-based): 0=record type, 1=element type (`R`=RIB entry, `B`=block start marker), 2=timestamp, 7=peer ASN, 8=peer IP, 9=prefix, 10=next-hop, **11=AS path**, 12=origin AS, 13=communities. Only process lines where field[1] == `R`; skip `B` lines. Note: the option name is `rib-file`, not `mrt-file`.

## Pipeline Architecture

Three scripts forming a linear pipeline, orchestrated via `justfile`:

1. **`get-mrt.py`** — Downloads the 00:00 UTC RIB snapshot (`bview`) for a given date from one or more RIS collectors. Flags: `--collectors` (required, comma-separated), `--date` (required, YYYYMMDD), `--output-dir` (default `./mrt`). Skips already-downloaded files. Output filenames include the collector name: `bview.rrcXX.YYYYMMDD.0000.gz`.

2. **`process-mrt.py`** — Calls `bgpreader` on each `.gz` file to extract AS paths, writing `.txt` sidecar files to `--output-dir` (default `./paths`). Each output line contains only the AS path string (space-separated ASNs). Skips files whose `.txt` already exists.

3. **`build-topology.py`** — Reads `.txt` path files (via `--input` glob), extracts edges, and writes output files to the directory of `--output` (default `./topology.txt`). Always produces three files:
   - `{stem}.txt` — deduplicated undirected edge list, one `AS1 AS2` per line, sorted numerically
   - `{stem}-asns.txt` — sorted list of all unique ASNs present in the topology
   - `{stem}-paths.txt` — deduplicated list of unique AS paths seen across all input files, sorted by leading ASN numerically; paths are directional (BGP semantics preserved)

   Optional flags:
   - `--filter-registered` — filters at the **path level**: a path is excluded if *any* of its ASNs is not `assigned` per the NRO delegated stats. Excluded ASNs are collected in `{stem}-dropped-asns.txt`; excluded edges are counted in the summary. The NRO stats file is cached next to the input `.txt` files and re-downloaded only if older than 24 hours.
   - `--justify-output` — zero-pads all ASNs to 8 digits in all output files (e.g. `6057` → `00006057`). Does not affect terminal output.

## Conventions

- All scripts: measure and display total execution time on exit; show progress when processing multiple files; include inline docstrings and rich `--help` output.
- `--collectors` is mandatory with no default.
- AS path processing rules (applied in `process-mrt.py`):
  - Collapse consecutive duplicate ASNs before extracting edges (remove prepending): `A A B C` → `A B C`.
  - AS sets (e.g. `{64500,64501}`) truncate the path at that point; edges before the set are kept.
  - Edges are stored as integer-ordered tuples: `(a, b) if int(a) < int(b) else (b, a)`. **Do not use string `min`/`max`** — lexicographic order differs from numeric order for ASNs (e.g. `"22773" < "6"` as strings).
- `bview` files are the RIB snapshot type used by RIS.
- Output data files (`topology*.txt`, `nro-delegated-stats`) are excluded from version control via `.gitignore`.

## NRO Delegated Stats

- URL: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats`
- Format: `|`-delimited. ASN records have field[2]`==`asn`. Valid statuses: `assigned` (keep), `available`/`reserved` (discard). Skip lines where field[1]`==`*` (summary) or field[4]`==`summary`.
- field[3] = start ASN, field[4] = count (expand range with `range(start, start+count)`).

## RIS Data

- Collectors: `rrc00` through `rrc25`
- URL pattern: `https://data.ris.ripe.net/rrcXX/YYYY.MM/bview.YYYYMMDD.0000.gz`
