# Internet Topology from RIPE RIS

Reconstruct the Internet's AS-level topology from publicly available BGP routing data published by [RIPE NCC's Routing Information Service (RIS)](https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris).

The pipeline downloads MRT RIB snapshot files from RIS route collectors, extracts AS paths, and produces a set of output files describing the observed AS-level topology — including a deduplicated edge list, a unique ASN list, a unique path list, and optionally a list of ASNs filtered out against the NRO registry.

```
00000006 00022773
00001299 00003356
00001299 00022773
...
```

---

## How It Works

BGP routers exchange reachability information in the form of **AS paths** — ordered sequences of Autonomous System Numbers (ASNs) that a route traverses to reach a destination prefix. For example, the AS path `1299 3356 15169` tells us that links exist between AS 1299 and AS 3356, and between AS 3356 and AS 15169.

RIPE RIS operates a global network of **route collectors** (`rrc00` through `rrc25`), each peering with many BGP routers worldwide. Periodically, each collector dumps a full snapshot of its routing table into an MRT-format binary file (a "RIB dump" or `bview` file). This pipeline processes those snapshots to reconstruct the observed AS-level topology.

---

## Prerequisites

- **Python 3.12+** managed via [`uv`](https://github.com/astral-sh/uv)
- **`bgpreader`** installed as a system binary (part of [BGPStream](https://bgpstream.caida.org/))
- **`just`** command runner ([installation](https://github.com/casey/just))

---

## Quick Start

```bash
# Full pipeline: all collectors, December 1st 2025
just date=20251201 collectors=rrc00-rrc25 pipeline

# Custom output filename
just date=20251201 collectors=rrc00-rrc25 output="topology-20251201.txt" pipeline
```

> **Note:** variable assignments must come **before** the recipe name in `just`.

---

## The Pipeline

### Step 1 — Download MRT RIB snapshots: `get-mrt.py`

Downloads the 00:00 UTC RIB snapshot (`bview`) for a given date from one or more RIS collectors. Already-downloaded files are skipped. Failed transfers are reported per-collector and counted in the summary without aborting the run.

```
uv run get-mrt.py --collectors <spec> --date <YYYYMMDD> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--collectors` | Collector specification. **Required.** See range notation below. |
| `--date` | Date of the 00:00 UTC RIB snapshot in `YYYYMMDD` format. **Required.** |
| `--output-dir` | Directory to store downloaded `.gz` files. Default: `./mrt` |

#### Collector specification

`--collectors` accepts a comma-separated mix of individual names and ranges:

| Syntax | Example | Expands to |
|---|---|---|
| Individual | `rrc00` | `rrc00` |
| List | `rrc00,rrc04,rrc11` | `rrc00`, `rrc04`, `rrc11` |
| Range | `rrc00-rrc05` | `rrc00` through `rrc05` inclusive |
| Mixed | `rrc00-rrc03,rrc11,rrc23` | `rrc00`–`rrc03`, `rrc11`, `rrc23` |

**Examples:**
```bash
# Single collector
uv run get-mrt.py --collectors rrc00 --date 20251201

# Range of collectors
uv run get-mrt.py --collectors rrc00-rrc10 --date 20251201

# Mixed: two ranges and an individual
uv run get-mrt.py --collectors rrc00-rrc05,rrc11,rrc23 --date 20251201 --output-dir ./mrt
```

---

### Step 1b — Download RouteViews RIB snapshots: `get-routeviews.py`

Downloads the 00:00 UTC RIB snapshot for a given date from one or more RouteViews collectors. Same behaviour as `get-mrt.py`: already-downloaded files are skipped, failed transfers are reported without aborting the run. Output files are `.bz2` format.

```
uv run get-routeviews.py --collectors <spec> --date <YYYYMMDD> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--collectors` | Comma-separated RouteViews collector IDs. **Required.** |
| `--date` | Date of the 00:00 UTC RIB snapshot in `YYYYMMDD` format. **Required.** |
| `--output-dir` | Directory to store downloaded `.bz2` files. Default: `./mrt` |

Known collectors:

| Collector ID | Location |
|---|---|
| `route-views.amsix` | AMS-IX, Amsterdam |
| `ix-br2.gru` | São Paulo, Brazil |
| `route-views2` | Oregon, US |
| `route-views.sg` | Singapore |

**Example:**
```bash
uv run get-routeviews.py \
  --collectors route-views.amsix,ix-br2.gru,route-views2,route-views.sg \
  --date 20251201 \
  --output-dir ./mrt/20251201
```

RouteViews `.bz2` files are processed automatically alongside RIPE RIS `.gz` files — no extra flags needed.

---

### Step 2 — Extract AS paths: `process-mrt.py`

Processes downloaded MRT files using `bgpreader`, extracting one AS path per line into three sidecar files per input. A file set is skipped if all three outputs already exist.

AS path cleaning is applied before writing:
- **Prepending removed**: consecutive duplicate ASNs are collapsed (`64500 64500 64501` → `64500 64501`).
- **AS sets truncated**: paths containing AS sets (e.g. `{64500,64501}`) are truncated at the set; edges before it are kept.

Address family is detected from the prefix field: prefixes containing `:` are IPv6; all others are IPv4. Each path is written to the combined file and to the appropriate address-family file.

```
uv run process-mrt.py --input-files <glob> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--input-files` | Glob pattern matching MRT `.gz` files to process. **Required.** |
| `--output-dir` | Directory to write output files. Default: `./paths` |

#### Output files per MRT input

| File | Description |
|---|---|
| `<name>.gz.txt` | All paths (combined, IPv4 + IPv6) |
| `<name>.gz.v4.txt` | IPv4-only paths |
| `<name>.gz.v6.txt` | IPv6-only paths |

**Example:**
```bash
uv run process-mrt.py --input-files "./mrt/*.gz" --output-dir ./paths
```

---

### Step 3 — Build the topology: `build-topology.py`

Reads AS path files and produces a set of output files describing the topology. Always generates three files; a fourth is produced when `--filter-registered` is active.

```
uv run build-topology.py --input <glob> [--output <file>] [options]
```

| Flag | Description |
|---|---|
| `--input` | Glob pattern matching AS path `.txt` files. **Required.** Repeat to include multiple patterns. |
| `--output` | Output file for the edge list. Default: `./topology.txt` |
| `--date` | Snapshot date in `YYYYMMDD` format. When set, the matching historical NRO stats file is used for filtering instead of the latest. |
| `--filter-registered` | Drop any path containing an unregistered ASN (see below). Default: off. |
| `--justify-output` | Zero-pad all ASNs to 8 digits in all output files. Default: off. |
| `--no-paths` | Skip building the paths file (fastest mode for edge-list-only runs). Default: off. |
| `--workers` | Number of parallel file-processing workers. Default: `cpu_count`. |

#### Output files

All output files are written to the same directory as `--output`, named after its stem.

| File | Description |
|---|---|
| `topology.txt` | Deduplicated undirected edge list, one `AS1 AS2` per line, sorted numerically. |
| `topology-asns.txt` | Sorted list of all unique ASNs present in the topology. |
| `topology-paths.txt` | Deduplicated list of unique AS paths, sorted numerically by leading ASN. Paths are directional. |
| `topology-dropped-asns.txt` | *(only with `--filter-registered`)* ASNs removed because they are not formally assigned. |

#### `--filter-registered`

When enabled, any path where **at least one ASN** is not formally `assigned` in the [NRO delegated extended stats](https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats) is excluded entirely. The NRO stats file is cached next to the input `.txt` files and only re-downloaded if it is more than 24 hours old.

#### `--justify-output`

Zero-pads all ASN numbers to 8 digits in every output file, making them fixed-width and suitable for lexicographic sorting tools:

```
# Without --justify-output      # With --justify-output
6 22773                         00000006 00022773
1299 3356                       00001299 00003356
```

**Examples:**
```bash
# Combined topology
uv run build-topology.py --input "./paths/*.gz.txt" --output ./output/topology.txt

# With filtering and zero-padding
uv run build-topology.py \
  --input "./paths/*.gz.txt" \
  --output ./output/20251201/topology-20251201.txt \
  --filter-registered \
  --justify-output
```

---

## Running the Full Pipeline

### Using `just` (recommended)

```bash
# Minimal: single collector, default output
just date=20251201 pipeline

# All collectors, custom output name
just date=20251201 collectors=rrc00-rrc25 output="topology-20251201.txt" pipeline

# Individual steps
just date=20251201 collectors=rrc00-rrc25 download
just process
just topology           # combined + v4 + v6
just topology-combined  # combined only
just topology-v4        # IPv4 only
just topology-v6        # IPv6 only
```

Available `just` variables:

| Variable | Default | Description |
|---|---|---|
| `collectors` | `rrc00` | Collector specification (supports range notation) |
| `date` | *(required for download)* | Snapshot date in `YYYYMMDD` format |
| `mrt_dir` | `./mrt` | Root directory for downloaded MRT files (date subdir created automatically) |
| `paths_dir` | `./paths` | Root directory for extracted AS path files (date subdir created automatically) |
| `output_dir` | `./output` | Root directory for topology output files (date subdir created automatically) |
| `output` | `topology.txt` | Combined output filename |
| `output_v4` | `topology-v4.txt` | IPv4-only output filename |
| `output_v6` | `topology-v6.txt` | IPv6-only output filename |

### Using scripts directly

```bash
# 1. Download RIB snapshots from all collectors
uv run get-mrt.py \
  --collectors rrc00-rrc25 \
  --date 20251201 \
  --output-dir ./mrt/20251201

# 2. Extract AS paths
uv run process-mrt.py \
  --input-files "./mrt/20251201/*.gz" \
  --output-dir ./paths/20251201

# 3. Build topology (run once per address family)
uv run build-topology.py \
  --input "./paths/20251201/*.gz.txt" \
  --output ./output/20251201/topology-20251201.txt \
  --filter-registered \
  --justify-output

uv run build-topology.py \
  --input "./paths/20251201/*.gz.v4.txt" \
  --output ./output/20251201/topology-20251201-v4.txt \
  --filter-registered \
  --justify-output

uv run build-topology.py \
  --input "./paths/20251201/*.gz.v6.txt" \
  --output ./output/20251201/topology-20251201-v6.txt \
  --filter-registered \
  --justify-output
```

---

## Helper Tools

### Topology Set Operations: `topology-ops.py`

Combines two or more topology edge list files using set operations.

```
uv run topology-ops.py --op <add|sub> --output <file> [--justify-output] FILE [FILE ...]
```

| Argument / Flag | Description |
|---|---|
| `FILE ...` | Two or more topology edge list files. **Required.** |
| `--op` | Operation: `add` (union) or `sub` (difference). **Required.** |
| `--output` | Output edge list file. **Required.** |
| `--justify-output` | Zero-pad all ASNs to 8 digits in the output. Default: off. |

Both plain (`6 22773`) and zero-padded (`00000006 00022773`) input formats are handled transparently — comparison is always numeric.

- **add**: union of all input files (all edges present in any file, deduplicated)
- **sub**: edges from the first file that do not appear in any of the remaining files

**Examples:**
```bash
# Merge three dates into a single combined topology
uv run topology-ops.py --op add \
  --output output/combined.txt --justify-output \
  output/20230801/topology.txt \
  output/20251201/topology.txt \
  output/20260101/topology.txt

# Find edges present in 2023 but gone by 2025
uv run topology-ops.py --op sub \
  --output output/disappeared.txt \
  output/20230801/topology.txt \
  output/20251201/topology.txt
```

---

### Topology to GML: `topology-to-gml.py`

Converts a topology edge list to a [GML](https://en.wikipedia.org/wiki/Graph_Modelling_Language) file for import into graph analysis tools such as Gephi, yEd, or Cytoscape.

```
uv run topology-to-gml.py --input <file> [--output <file>] [options]
```

| Flag | Description |
|---|---|
| `--input` | Topology edge list file (our `topology.txt` format). **Required.** |
| `--output` | Output `.gml` file. Default: input path with `.gml` extension. |
| `--enrich` | Fetch AS holder names from RIPEstat and use as node labels. Default: off. |
| `--min-degree` | Only enrich nodes with degree at or above this threshold. Default: `3`. |
| `--concurrency` | Max parallel RIPEstat requests when `--enrich` is active. Default: `10`. |
| `--cache` | Path to the local AS name cache. Default: `~/.cache/internet-topology-ris/as-names.json`. |

Without `--enrich`, each node's label is its ASN. With `--enrich`, nodes above the degree threshold are labeled with the AS holder name (e.g. `GOOGLE - Google LLC`); nodes below threshold keep their ASN as label. Holder names are cached locally for 60 days — repeated runs on different topology files reuse the cache instantly.

**Examples:**
```bash
# Basic conversion
uv run topology-to-gml.py --input output/20230801/topology.txt

# With enrichment, default degree filter (≥ 3)
uv run topology-to-gml.py \
  --input output/20230801/topology.txt \
  --output output/20230801/topology.gml \
  --enrich

# Only label well-connected nodes (degree ≥ 50), custom output
uv run topology-to-gml.py \
  --input output/20230801/topology-v4.txt \
  --output output/20230801/topology-v4.gml \
  --enrich --min-degree 50
```

---

### AS Lookup: `lookup-as.py`

Queries the [RIPEstat Data API](https://stat.ripe.net/docs/data_api) to retrieve, for one or more ASNs:
- AS holder name
- Number of currently announced prefixes
- Date/time last seen in the global routing table
- Whether the AS is currently announcing routes

```
uv run lookup-as.py --asn <ASN>
uv run lookup-as.py --file <file>
uv run lookup-as.py --file -
cat asns.txt | uv run lookup-as.py
```

| Flag | Description |
|---|---|
| `--asn` | Single ASN to look up. Mutually exclusive with `--file`. |
| `--file` | File with one ASN per line. Use `-` to read from stdin. Mutually exclusive with `--asn`. |
| `--output` | Write results as TSV to this file in addition to terminal output. Optional. |
| `--concurrency` | Max parallel API requests in batch mode. Default: `10`. |

Input accepts bare ASNs (`15169`) or `AS`-prefixed strings (`AS15169`). Batch lookups run concurrently and show a live progress bar. Results are displayed as a rich table sorted numerically by ASN. If neither `--asn` nor `--file` is given and stdin is not a tty, ASNs are read from stdin automatically.

**Examples:**
```bash
# Single ASN
uv run lookup-as.py --asn 15169

# Batch from file
uv run lookup-as.py --file asns.txt

# Pipe from another command, write TSV
cat output/topology-asns.txt | uv run lookup-as.py --output asn-info.tsv

# Look up ASNs from the dropped list
uv run lookup-as.py --file output/topology-dropped-asns.txt
```

---

## RIS Collectors

| Collector | Location |
|---|---|
| rrc00 | Amsterdam, NL |
| rrc01 | London, UK |
| rrc03 | Amsterdam, NL |
| rrc04 | Geneva, CH |
| rrc05 | Vienna, AT |
| rrc06 | Otemachi, JP |
| rrc07 | Stockholm, SE |
| rrc10 | Milan, IT |
| rrc11 | New York, US |
| rrc12 | Frankfurt, DE |
| rrc13 | Moscow, RU |
| rrc14 | Palo Alto, US |
| rrc15 | São Paulo, BR |
| rrc16 | Miami, US |
| rrc18 | Barcelona, ES |
| rrc19 | Johannesburg, ZA |
| rrc20 | Zurich, CH |
| rrc21 | Paris, FR |
| rrc22 | Bucharest, RO |
| rrc23 | Singapore, SG |
| rrc24 | Montevideo, UY |
| rrc25 | Amsterdam, NL |

Using more collectors gives broader visibility into the global topology, at the cost of more data to download and process.
