# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Reconstruct Internet AS-level topology from RIPE RIS MRT files. The pipeline downloads binary MRT files, extracts AS paths using `bgpreader`, and produces a deduplicated edge list (`AS1 AS2` per line).

## Commands

```bash
# Run the full pipeline via just
# NOTE: variable assignments must come BEFORE the recipe name
just date=20240101 pipeline
just date=20240101 collectors=rrc00,rrc01,rrc04 pipeline
just date=20240101 collectors=rrc00-rrc10 pipeline
just date=20240101 collectors=rrc00-rrc05,rrc11 pipeline

# Run individual steps
just date=20240101 collectors=rrc00-rrc25 download
just date=20240101 download-routeviews
just date=20240101 process
just date=20240101 topology          # combined + v4 + v6
just date=20240101 topology-combined
just date=20240101 topology-v4
just date=20240101 topology-v6

# Fleet / distributed use
# On each node: assign a collector slice and run download + process only
just date=20240101 collectors=rrc00-rrc05 slice
# Optionally on each node: build a local partial topology
just date=20240101 topology
# On the central machine: collect all path files, then build the global topology
just date=20240101 collect          # reads fleet.csv, default 2 parallel rsyncs
just date=20240101 jobs=4 collect   # override parallelism
just date=20240101 topology

# Pack and publish output products
just date=20240101 pack-and-publish
just date=20240101 pubpoint=/srv/data/topo pack-and-publish

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

1. **`get-mrt.py`** — Downloads the 00:00 UTC RIB snapshot (`bview`) for a given date from one or more RIS collectors. Flags: `--collectors` (required), `--date` (required, YYYYMMDD), `--output-dir` (default `./mrt`). Skips already-downloaded files; failed transfers are counted and reported but do not abort the run. Output filenames include the collector name: `bview.rrcXX.YYYYMMDD.0000.gz`. The justfile passes `./mrt/<date>` as `--output-dir` to keep runs isolated by date. Invoked as the `download` recipe.

   **`get-routeviews.py`** — same interface as `get-mrt.py` but targets the RouteViews archive. Invoked as the `download-routeviews` recipe with a working subset of the ~40 available RouteViews collectors: `route-views.amsix`, `ix-br2.gru`, `namex.fco`, `route-views2`, `route-views.sg`, `crix.sjo`, `hkix.hkg`, `route-views.chicago`, `route-views.kixp`, `route-views.rio`, `route-views.perth`, `pacwave.lax`. No range notation (collectors don't follow a numeric sequence). To add more collectors, extend the `--collectors` argument in the `download-routeviews` justfile recipe; the full list is at https://www.routeviews.org/routeviews/index.php/collectors/. Output filenames: `rib.<collector>.<date>.0000.bz2`. URL pattern: `https://archive.routeviews.org/<collector>/bgpdata/YYYY.MM/RIBS/rib.YYYYMMDD.0000.bz2`. Both `download` and `download-routeviews` are dependencies of `pipeline`.

   `--collectors` accepts a comma-separated mix of individual names and ranges: `rrc00`, `rrc00,rrc04,rrc11`, `rrc00-rrc10`, `rrc00-rrc05,rrc11,rrc23`.

   **Note:** both RIS and RouteViews use bview-only (00:00 UTC RIB snapshot). Intraday update files are not collected.

2. **`extract-paths.py`** — Calls `bgpreader` on each MRT file (`.gz` or `.bz2`) to extract AS paths, writing three sidecar files per input into address-family subdirectories under `--output-dir` (default `./paths`). Output filenames strip the source extension (`.gz`/`.bz2`) and append a suffix:
   - `combined/<stem>.txt.gz` — all paths (combined)
   - `v4/<stem>.v4.txt.gz` — IPv4-only paths (prefix field has no `:`)
   - `v6/<stem>.v6.txt.gz` — IPv6-only paths (prefix field contains `:`)

   Address family is detected from bgpreader column 9 (prefix): presence of `:` indicates IPv6. Each path is written to the combined file and to the appropriate AF file. A file set is skipped only if all three output files already exist. The justfile passes `./paths/<date>` as `--output-dir`. bgpreader handles both `.gz` and `.bz2` inputs transparently. The justfile `process` recipe runs twice — once for `*.gz` and once for `*.bz2` — so both RIPE RIS and RouteViews files are processed automatically. If no files match a glob, the invocation prints a notice and exits cleanly.

3. **`build-topology.py`** — Reads `.txt.gz` path files (via `--input` glob, repeatable), extracts edges, and writes output files to the directory of `--output` (default `./topology.txt`). The justfile passes `paths/<date>/combined/*.txt.gz` for combined topology and per-AF globs for v4/v6. All topology output goes to `./output-combined/<date>/`. Always produces two files:
   - `{stem}.txt` — deduplicated undirected edge list, one `AS1 AS2` per line, sorted numerically
   - `{stem}-asns.txt` — sorted list of all unique ASNs present in the topology

   Optional flags:
   - `--paths` — also write `{stem}-paths.txt`: deduplicated AS paths, sorted fully numerically. Off by default (paths files are large and expensive). Per-file paths are sorted and deduplicated in worker processes via chunked sort + `heapq.merge`; the final step merges all per-file sorted files into one globally deduplicated output.
   - `--filter-registered` — filters at the **path level**: a path is excluded if *any* of its ASNs is not `assigned` per the NRO delegated stats. Excluded ASNs are collected in `{stem}-dropped-asns.txt`. The stats file is cached next to the input `.txt` files; see `--date` for which file is fetched.
   - `--date YYYYMMDD` — when provided alongside `--filter-registered`, fetches the historical NRO stats snapshot for that date (`https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{YYYYMMDD}/nro-delegated-stats`) instead of the latest file. Historical files are cached permanently (they never change). Without `--date`, the latest file is used and re-downloaded if older than 24 hours. Cache filenames: `nro-delegated-stats` (latest) or `nro-delegated-stats-{YYYYMMDD}` (historical), stored next to the input `.txt` files.
   - `--justify-output` — zero-pads all ASNs to 8 digits in all output files (e.g. `6057` → `00006057`). Does not affect terminal output.
   - `--workers N` — number of parallel `ProcessPoolExecutor` workers (default: `cpu_count`). Each worker processes one input file independently.

## Conventions

- All scripts: measure and display total execution time on exit; show progress when processing multiple files; include inline docstrings and rich `--help` output.
- **Path files are gzip-compressed** (`compresslevel=1`). `extract-paths.py` writes gzip output with a `.txt.gz` extension. `build-topology.py` detects compression via the `\x1f\x8b` magic bytes and opens files with `gzip.open()` transparently — plain text files are also still accepted.
- `--collectors` is mandatory with no default.
- AS path processing rules (applied in `extract-paths.py`):
  - Collapse consecutive duplicate ASNs before extracting edges (remove prepending): `A A B C` → `A B C`.
  - AS sets (e.g. `{64500,64501}`) truncate the path at that point; edges before the set are kept.
  - Edges are stored as integer-ordered tuples: `(a, b) if int(a) < int(b) else (b, a)`. **Do not use string `min`/`max`** — lexicographic order differs from numeric order for ASNs (e.g. `"22773" < "6"` as strings).
- `bview` files are the RIB snapshot type used by RIS.
- Output data files (`topology*.txt`, `nro-delegated-stats`) are excluded from version control via `.gitignore`.
- **`DATA-README.md`** — template for the human-readable README included in every published archive. Uses `{date}` as a placeholder; `pack-and-publish` substitutes the actual date via `sed` before archiving.
- **`pack-and-publish`** just recipe — packs `./output-combined/{date}/` into `topology-{date}.tar.bz2`, injects the substituted `DATA-README.md` as `README.md`, prompts before overwriting at destination, then `sudo cp`s to `pubpoint` (default `/var/www/html/topo`). Standalone — does not depend on `topology`.

## NRO Delegated Stats

- Latest URL: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats`
- Historical URL: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{YYYYMMDD}/nro-delegated-stats`
- Format: `|`-delimited. ASN records have field[2]`==`asn`. Valid statuses: `assigned` (keep), `available`/`reserved` (discard). Skip lines where field[1]`==`*` (summary) or field[4]`==`summary`.
- field[3] = start ASN, field[4] = count (expand range with `range(start, start+count)`).

## CAIDA AS Relationships

**`get-caida-peers.py`** — Downloads the CAIDA AS relationships dataset for a given month and extracts peer-to-peer edges (`rel=0`). Prefers serial-2; falls back to serial-1 for months not covered by serial-2 (~pre-2012). Discovers the correct filename by fetching the directory index (files are not always named with the 1st of the month). Caches downloaded `.bz2` files permanently in `./caida-cache/` — CAIDA files are immutable once published. Output: `output-combined/YYYYMM/caida-peers-YYYYMM.txt`.

- `--date YYYYMM` — required
- `--output PATH` — override default output path
- `--justify-output / --no-justify-output` — zero-pad ASNs to 8 digits (default: on)
- `--cache-dir` — override cache location (default: `./caida-cache`)

Justfile: `just date=202401 caida-peers` · `just date=202401 no_justify=1 caida-peers`

Index URLs:
- Serial-2: `https://publicdata.caida.org/datasets/as-relationships/serial-2/`
- Serial-1: `https://publicdata.caida.org/datasets/as-relationships/serial-1/`

## Helper Tools

**`topology-ops.py`** — Set operations on two or more topology edge list files. Input files are positional arguments (minimum 2). `--op add` produces the union of all inputs; `--op sub` produces edges in the first file not present in any of the remaining files. Both plain and zero-padded ASN formats handled transparently (comparison is always numeric). `--justify-output` follows the same convention as other tools.

**`collect.sh`** — Collects path files from all fleet nodes into the local `./paths/<date>/` directory. Reads `fleet.csv` (gitignored, copy from `fleet.csv.example`) where each line is `username,hostname,/path/to/repo`. For each host, rsyncs `<repo>/paths/<date>/` directly into `./paths/<date>/` — no filename conflicts because path files include the collector name. Runs up to N hosts in parallel (default 2). Per-host logs go to `./logs/collect-<date>/<hostname>.log`; reports all failed hosts at the end. Invoked via the `collect` just recipe. Requires bash 4+ (`export -f`); on macOS: `brew install bash`.

**Distributed workflow** — typical pattern for a fleet of machines each handling a slice of collectors:
1. On each node: `just date=YYYYMMDD collectors=<slice> slice` (download + extract paths)
2. Optionally on each node: `just date=YYYYMMDD topology` (build a local partial topology for inspection)
3. On the central machine: `just date=YYYYMMDD collect` (rsync all path files in)
4. On the central machine: `just date=YYYYMMDD topology` (build the global topology from all collected paths)

`fleet.csv` is gitignored; `fleet.csv.example` is tracked and serves as the template. The `jobs` justfile variable (default `2`) controls parallel rsyncs: `just date=YYYYMMDD jobs=4 collect`.

**`download-routeviews-month.sh`** — Downloads one RouteViews bview per day for an entire month using the `download-routeviews` recipe. Usage: `./download-routeviews-month.sh YYYYMM [parallel_jobs]` (default 4 parallel jobs). Downloads land in `./mrt-routeviews/YYYYMMDD/`. Per-day logs go to `./logs/routeviews-YYYYMM/YYYYMMDD.log`.

**`fetch-results.sh`** — Fetches output files from multiple remote machines running the pipeline in parallel. Rsyncs into `./fetch/<hostname>/` subdirs to avoid conflicts. Configure `SOURCES` (rsync URLs), `INCLUDES` (array of glob patterns), and `EXCLUDE` at the top. Uses `--include="*/"` to recurse into date subdirs, then applies include/exclude filters. Continues on per-host failure and reports all failed hosts at the end. Topology files are gzip-compressed; count unique ASNs across fetched files with: `zcat fetch/*/topology-????????.txt | awk '{print $1; print $2}' | sort -un | wc -l`

**`lookup-as.py`** — Queries the RIPEstat Data API for one or more ASNs. Returns AS holder name, announced prefix count, last-seen timestamp, and announced status. Three input modes: `--asn <N>` (single), `--file <path>` (batch), `--file -` or implicit stdin (pipe). Batch requests run concurrently via `asyncio` + `httpx.AsyncClient`, bounded by `--concurrency` (default 10). A live progress bar is shown for batch mode. `--output` writes a TSV sidecar alongside the terminal table.

API endpoints used (all under `https://stat.ripe.net/data/`):
- `as-overview` → holder name, `announced` bool
- `announced-prefixes` → `prefixes` list (len = prefix count)
- `routing-status` → `last_seen.time` (ISO string)

## Graph Analysis Tools (`graph-analysis/`)

A separate directory of tools for analysing topology files as graphs. All run via `uv run graph-analysis/<tool>` from the repo root. See `graph-analysis/README.md` for full usage and examples.

**`graph-analysis/topology-to-gml.py`** — Converts a topology edge list to a NetworkX GML file. Always writes `.gml` output. `--min-degree N` filters edges where both endpoints have degree >= N before writing (useful to reduce the graph before enrichment). With `--enrich`, nodes with degree >= `--enrich-min-degree` (default 3) receive their AS holder name from RIPEstat as label; names cached at `~/.cache/internet-topology-ris/as-names.json` (60-day TTL). To produce a filtered `.txt` topology instead, use `topology-core.py`.

**`graph-analysis/hubs.py`** — Lists ASNs with degree >= `--min-degree` from a topology edge list (`.txt`/`.txt.gz`) or GML file. Degrees are computed in a single pass for `.txt` input — no GML conversion required. Without `--wide`: one ASN per line, sorted numerically. With `--wide`: two columns (`ASN degree`), sorted by degree descending. Flags: `--input` (required), `--output` (default: input stem + `-hubs.txt`), `--min-degree` (required), `--wide`.

**`graph-analysis/gml-to-topology.py`** — Inverse of `topology-to-gml.py`. Reads a GML file and writes a two-column topology edge list (`ASN1 ASN2` per line, `ASN1 < ASN2`, sorted by ASN1). ASNs are always read from the node `asn` attribute (safe for enriched GML files). Optional `--min-degree N` filters to edges where both endpoints have degree ≥ N. `--justify-output` zero-pads ASNs to 8 digits.

**`graph-analysis/geo-filter.py`** — Filters a topology (`.txt`/`.txt.gz` or `.gml`) to edges where both ASNs are assigned to one of the given ISO 3166-1 alpha-2 country codes per the NRO delegated stats. ASNs absent from the NRO file are excluded. Always writes both a `.txt` topology and a `.gml` (nodes carry a `country` attribute). NRO stats are fetched and cached next to the input file; `--date YYYYMMDD` selects a historical snapshot. Flags: `--input`, `--countries` (comma-separated, required), `--output` (base path, no extension), `--date`, `--justify-output`.

**`graph-analysis/annotate-topology.py`** — Enriches a topology edge list by adding four columns per edge: `cc1 rir1 cc2 rir2` (country and RIR for each ASN). Country codes are lowercase ISO 3166-1 alpha-2; RIR names follow NRO stats terminology (`ripencc`, `arin`, `lacnic`, `apnic`, `afrinic`). ASNs absent from the NRO file are annotated as `unknown unknown`. NRO stats are fetched and cached next to the input file; `--date YYYYMMDD` selects a historical snapshot. Input sort order is preserved. Flags: `--input`, `--output` (default: input stem + `-annotated.txt`), `--date`, `--justify-output`.

**`graph-analysis/topology-core.py`** — Filters a topology edge list to edges where **both** endpoints have degree >= `--min-degree`. Output is a valid topology file (same two-column format, `ASN1 < ASN2`, sorted by ASN1). Degree is computed from the input file directly — no GML needed. Flags: `--input` (required), `--output` (default: input stem + `-core.txt`), `--min-degree` (required), `--wide` (adds `DEG1 DEG2` columns), `--justify-output` (zero-pad ASNs to 8 digits).

**`graph-analysis/asn-presence.py`** — Builds a day-by-day ASN presence matrix from `{stem}-asns-YYYYMMDD.txt` files (produced by `build-topology.py`). One row per unique ASN, one column per date, values `0`/`1`. The first line is a header (`ASN YYYYMMDD YYYYMMDD …`). ASNs are zero-padded to 8 digits. Flags: `--input` (glob, repeatable, required), `--output` (default: directory of first matched file / `asn-presence.txt`). Load in pandas: `pd.read_csv("asn-presence.txt", sep=r"\s+", index_col=0, dtype=int)`.

## RIS Data

- Collectors: `rrc00` through `rrc25`
- URL pattern: `https://data.ris.ripe.net/rrcXX/YYYY.MM/bview.YYYYMMDD.0000.gz`
