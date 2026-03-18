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

### Step 2 — Extract AS paths: `process-mrt.py`

Processes downloaded MRT files using `bgpreader`, extracting one AS path per line into sidecar `.txt` files. Already-processed files are skipped.

AS path cleaning is applied before writing:
- **Prepending removed**: consecutive duplicate ASNs are collapsed (`64500 64500 64501` → `64500 64501`).
- **AS sets truncated**: paths containing AS sets (e.g. `{64500,64501}`) are truncated at the set; edges before it are kept.

```
uv run process-mrt.py --input-files <glob> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--input-files` | Glob pattern matching MRT `.gz` files to process. **Required.** |
| `--output-dir` | Directory to write `.txt` output files. Default: `./paths` |

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
| `--input` | Glob pattern matching AS path `.txt` files. **Required.** |
| `--output` | Output file for the edge list. Default: `./topology.txt` |
| `--filter-registered` | Drop any path containing an unregistered ASN (see below). Default: off. |
| `--justify-output` | Zero-pad all ASNs to 8 digits in all output files. Default: off. |

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
# Basic
uv run build-topology.py --input "./paths/*.txt" --output ./output/topology.txt

# With filtering and zero-padding
uv run build-topology.py \
  --input "./paths/*.txt" \
  --output ./output/topology-20251201.txt \
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
just topology
```

Available `just` variables:

| Variable | Default | Description |
|---|---|---|
| `collectors` | `rrc00` | Collector specification (supports range notation) |
| `date` | *(required for download)* | Snapshot date in `YYYYMMDD` format |
| `mrt_dir` | `./mrt` | Directory for downloaded MRT files |
| `paths_dir` | `./paths` | Directory for extracted AS path files |
| `output_dir` | `./output` | Directory for topology output files |
| `output` | `topology.txt` | Output filename (stem used for all sidecar files) |

### Using scripts directly

```bash
# 1. Download RIB snapshots from all collectors
uv run get-mrt.py \
  --collectors rrc00-rrc25 \
  --date 20251201 \
  --output-dir ./mrt

# 2. Extract AS paths
uv run process-mrt.py \
  --input-files "./mrt/*.gz" \
  --output-dir ./paths

# 3. Build topology with filtering and zero-padding
uv run build-topology.py \
  --input "./paths/*.txt" \
  --output ./output/topology-20251201.txt \
  --filter-registered \
  --justify-output
```

---

## Scale Reference

Processing rrc00's RIB snapshot for 2024-01-01 (single collector):

| Metric | Value |
|---|---|
| AS paths extracted | ~55 million |
| Unique edges | ~237,000 |
| Unique ASNs | ~83,000 |
| Unique paths | ~millions |
| Step 2 time | ~3 min |
| Step 3 time | ~2–3 min |

Using all 22 active collectors multiplies the input volume proportionally, though unique edge and ASN counts grow sub-linearly as collectors share significant overlap in routing tables.

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
