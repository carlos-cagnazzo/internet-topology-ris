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
just date=20240101 collectors=rrc00-rrc25 ris-day   # bview + updates, replaces download+process for RIS
just date=20240101 process
just date=20240101 topology          # combined + v4 + v6
just date=20240101 topology-combined
just date=20240101 topology-v4
just date=20240101 topology-v6

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

   **`get-routeviews.py`** — same interface as `get-mrt.py` but targets the RouteViews archive. Invoked as the `download-routeviews` recipe with a fixed collector list: `route-views.amsix`, `ix-br2.gru`, `route-views2`, `route-views.sg`. No range notation (collectors don't follow a numeric sequence). Output filenames: `rib.<collector>.<date>.0000.bz2`. URL pattern: `https://archive.routeviews.org/<collector>/bgpdata/YYYY.MM/RIBS/rib.YYYYMMDD.0000.bz2`. Both `download` and `download-routeviews` are dependencies of `pipeline`.

   **`get-ris-day.py`** — alternative to `get-mrt.py` + `process-mrt.py` for RIS collectors. Downloads the bview AND all 288 five-minute update files for the given date, extracts paths from both (bview: `field[1]=='R'`; updates: `field[1]=='A'`, withdrawals ignored), and writes three compressed path files per collector (mirroring `process-mrt.py`):
   - `bview.<collector>.<date>.full.gz.txt` — combined paths
   - `bview.<collector>.<date>.full.gz.v4.txt` — IPv4-only paths
   - `bview.<collector>.<date>.full.gz.v6.txt` — IPv6-only paths

   Address family is detected from bgpreader column 9 (prefix) exactly as in `process-mrt.py`. A collector is skipped only if all three output files already exist. `--keep` preserves update files on disk (bview always kept). `--concurrency` caps parallel update downloads (default 20). Invoked via the `ris-day` justfile recipe. bgpreader option for update files: `upd-file=<path>` (vs `rib-file=<path>` for bview).

   `--collectors` accepts a comma-separated mix of individual names and ranges: `rrc00`, `rrc00,rrc04,rrc11`, `rrc00-rrc10`, `rrc00-rrc05,rrc11,rrc23`.

2. **`process-mrt.py`** — Calls `bgpreader` on each `.gz` file to extract AS paths, writing three sidecar files per input to `--output-dir` (default `./paths`):
   - `<name>.gz.txt` — all paths (combined)
   - `<name>.gz.v4.txt` — IPv4-only paths (prefix field has no `:`)
   - `<name>.gz.v6.txt` — IPv6-only paths (prefix field contains `:`)

   Address family is detected from bgpreader column 9 (prefix): presence of `:` indicates IPv6. Each path is written to the combined file and to the appropriate AF file. A file set is skipped only if all three output files already exist. The justfile passes `./paths/<date>` as `--output-dir`. bgpreader handles both `.gz` and `.bz2` inputs transparently. The justfile `process` recipe runs twice — once for `*.gz` and once for `*.bz2` — so both RIPE RIS and RouteViews files are processed automatically. If no files match a glob, the invocation prints a notice and exits cleanly.

3. **`build-topology.py`** — Reads `.txt` path files (via `--input` glob, repeatable), extracts edges, and writes output files to the directory of `--output` (default `./topology.txt`). The justfile runs it three times, passing both `*.gz.*` and `*.bz2.*` globs so RIPE RIS and RouteViews files are merged seamlessly. Always produces three files:
   - `{stem}.txt` — deduplicated undirected edge list, one `AS1 AS2` per line, sorted numerically
   - `{stem}-asns.txt` — sorted list of all unique ASNs present in the topology
   - `{stem}-paths.txt` — deduplicated list of unique AS paths seen across all input files, sorted fully numerically across all ASN fields; paths are directional (BGP semantics preserved). Per-file paths are sorted and deduplicated in worker processes via chunked sort + `heapq.merge`; the final step merges all per-file sorted files into one globally deduplicated output.

   Optional flags:
   - `--filter-registered` — filters at the **path level**: a path is excluded if *any* of its ASNs is not `assigned` per the NRO delegated stats. Excluded ASNs are collected in `{stem}-dropped-asns.txt`. The stats file is cached next to the input `.txt` files; see `--date` for which file is fetched.
   - `--date YYYYMMDD` — when provided alongside `--filter-registered`, fetches the historical NRO stats snapshot for that date (`https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{YYYYMMDD}/nro-delegated-stats`) instead of the latest file. Historical files are cached permanently (they never change). Without `--date`, the latest file is used and re-downloaded if older than 24 hours. Cache filenames: `nro-delegated-stats` (latest) or `nro-delegated-stats-{YYYYMMDD}` (historical), stored next to the input `.txt` files.
   - `--justify-output` — zero-pads all ASNs to 8 digits in all output files (e.g. `6057` → `00006057`). Does not affect terminal output.
   - `--no-paths` — skip the paths sort/merge step entirely. Use when only the edge list and ASN list are needed.
   - `--workers N` — number of parallel `ProcessPoolExecutor` workers (default: `cpu_count`). Each worker processes one input file independently.

   **Per-file cache**: after processing, each input file gets two sidecar files written next to it:
   - `<name>.topcache` — pickle with edges set, asns set, dropped_asns set, and raw path count. Keyed on (input mtime, NRO stats mtime, filter_registered flag). On subsequent runs, valid cache entries are loaded without re-reading the input file.
   - `<name>.topcache.paths` — sorted+deduplicated paths for that file (plain, un-justified). Used directly as input to the final `heapq.merge` step. Not written when `--no-paths` is active.

## Conventions

- All scripts: measure and display total execution time on exit; show progress when processing multiple files; include inline docstrings and rich `--help` output.
- **Path files are gzip-compressed** (`compresslevel=1`). Both `process-mrt.py` and `get-ris-day.py` write compressed output despite the `.txt` extension. `build-topology.py` detects compression via the `\x1f\x8b` magic bytes and opens files with `gzip.open()` transparently — plain text files are also still accepted.
- `--collectors` is mandatory with no default.
- AS path processing rules (applied in `process-mrt.py`):
  - Collapse consecutive duplicate ASNs before extracting edges (remove prepending): `A A B C` → `A B C`.
  - AS sets (e.g. `{64500,64501}`) truncate the path at that point; edges before the set are kept.
  - Edges are stored as integer-ordered tuples: `(a, b) if int(a) < int(b) else (b, a)`. **Do not use string `min`/`max`** — lexicographic order differs from numeric order for ASNs (e.g. `"22773" < "6"` as strings).
- `bview` files are the RIB snapshot type used by RIS.
- Output data files (`topology*.txt`, `nro-delegated-stats`) are excluded from version control via `.gitignore`.
- **`DATA-README.md`** — template for the human-readable README included in every published archive. Uses `{date}` as a placeholder; `pack-and-publish` substitutes the actual date via `sed` before archiving.
- **`pack-and-publish`** just recipe — packs `./output/{date}/` into `topology-{date}.tar.bz2`, injects the substituted `DATA-README.md` as `README.md`, prompts before overwriting at destination, then `sudo cp`s to `pubpoint` (default `/var/www/html/topo`). Standalone — does not depend on `topology`.

## NRO Delegated Stats

- Latest URL: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats`
- Historical URL: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{YYYYMMDD}/nro-delegated-stats`
- Format: `|`-delimited. ASN records have field[2]`==`asn`. Valid statuses: `assigned` (keep), `available`/`reserved` (discard). Skip lines where field[1]`==`*` (summary) or field[4]`==`summary`.
- field[3] = start ASN, field[4] = count (expand range with `range(start, start+count)`).

## Helper Tools

**`topology-ops.py`** — Set operations on two or more topology edge list files. Input files are positional arguments (minimum 2). `--op add` produces the union of all inputs; `--op sub` produces edges in the first file not present in any of the remaining files. Both plain and zero-padded ASN formats handled transparently (comparison is always numeric). `--justify-output` follows the same convention as other tools.

**`fetch-results.sh`** — Fetches output files from multiple remote machines running the pipeline in parallel. Rsyncs into `./fetch/<hostname>/` subdirs to avoid conflicts. Configure `SOURCES` (rsync URLs), `INCLUDES` (array of glob patterns), and `EXCLUDE` at the top. Uses `--include="*/"` to recurse into date subdirs, then applies include/exclude filters. Continues on per-host failure and reports all failed hosts at the end. Topology files are gzip-compressed; count unique ASNs across fetched files with: `zcat fetch/*/topology-????????.txt | awk '{print $1; print $2}' | sort -un | wc -l`

**`lookup-as.py`** — Queries the RIPEstat Data API for one or more ASNs. Returns AS holder name, announced prefix count, last-seen timestamp, and announced status. Three input modes: `--asn <N>` (single), `--file <path>` (batch), `--file -` or implicit stdin (pipe). Batch requests run concurrently via `asyncio` + `httpx.AsyncClient`, bounded by `--concurrency` (default 10). A live progress bar is shown for batch mode. `--output` writes a TSV sidecar alongside the terminal table.

API endpoints used (all under `https://stat.ripe.net/data/`):
- `as-overview` → holder name, `announced` bool
- `announced-prefixes` → `prefixes` list (len = prefix count)
- `routing-status` → `last_seen.time` (ISO string)

## Graph Analysis Tools (`graph-analysis/`)

A separate directory of tools for analysing topology files as graphs. All run via `uv run graph-analysis/<tool>` from the repo root. See `graph-analysis/README.md` for full usage and examples.

**`graph-analysis/topo-to-nx.py`** — Converts a topology edge list to a NetworkX GML file (undirected graph). Plain and gzip-compressed inputs accepted. Zero-padded ASNs are normalised to plain integers. Each node carries `asn` (int) and `label` (plain ASN string) attributes; edges carry no attributes. With `--enrich`, nodes with degree ≥ `--min-degree` (default 3) receive their AS holder name from RIPEstat as label; names cached at `~/.cache/internet-topology-ris/as-names.json` (60-day TTL). Flags: `--input` (required), `--output` (default: input stem + `.gml`), `--enrich/--no-enrich`, `--min-degree`, `--concurrency` (default 10), `--cache`.

**`graph-analysis/hubs.py`** — Lists ASNs with degree >= `--min-degree` from a GML file. Without `--wide`: one ASN per line, sorted numerically. With `--wide`: two columns (`ASN degree`), sorted by degree descending. Flags: `--input` (required), `--output` (default: input stem + `-hubs.txt`), `--min-degree` (required), `--wide`.

**`graph-analysis/nx-to-topo.py`** — Inverse of `topo-to-nx.py`. Reads a GML file and writes a two-column topology edge list (`ASN1 ASN2` per line, `ASN1 < ASN2`, sorted by ASN1). ASNs are always read from the node `asn` attribute (safe for enriched GML files). Optional `--min-degree N` filters to edges where both endpoints have degree ≥ N. `--justify-output` zero-pads ASNs to 8 digits.

**`graph-analysis/core.py`** — Filters a topology edge list to edges where **both** endpoints have degree >= `--min-degree`. Output is a valid topology file (same two-column format, `ASN1 < ASN2`, sorted by ASN1). Degree is computed from the input file directly — no GML needed. Flags: `--input` (required), `--output` (default: input stem + `-core.txt`), `--min-degree` (required), `--wide` (adds `DEG1 DEG2` columns), `--justify-output` (zero-pad ASNs to 8 digits).

## RIS Data

- Collectors: `rrc00` through `rrc25`
- URL pattern: `https://data.ris.ripe.net/rrcXX/YYYY.MM/bview.YYYYMMDD.0000.gz`
