# Internet Topology from RIPE RIS

Reconstruct the Internet's AS-level topology from publicly available BGP routing data published by [RIPE NCC's Routing Information Service (RIS)](https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris) and [RouteViews](https://www.routeviews.org/).

The pipeline downloads MRT RIB snapshot files from route collectors, extracts AS paths, and produces a set of output files describing the observed AS-level topology — including a deduplicated edge list, a unique ASN list, and optionally a filtered list of ASNs dropped against the NRO registry.

```
00000006 00022773
00001299 00003356
00001299 00022773
...
```

**[Full documentation](https://carlos-cagnazzo.github.io/internet-topology-ris)** &nbsp;·&nbsp; **[Tool quick reference](https://carlos-cagnazzo.github.io/internet-topology-ris/tools-qr.html)**

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

## Repo Layout

```
pipeline/        ← core pipeline scripts (Python)
analysis/        ← graph analysis + utility scripts (Python)
fleet/           ← fleet orchestration scripts (shell) + CSV examples
eda/             ← exploratory notebooks
justfile         ← recipe orchestration (repo root)
run.sh           ← Python script runner: ./run.sh <script.py> [args...]
```

`run.sh` searches `pipeline/`, `analysis/`, and `fleet/` in order and executes the script via `uv run`. Direct invocation (`uv run pipeline/script.py`) is always also valid.

---

## Quick Start

```bash
# Full pipeline: all RIS collectors + default RouteViews subset, Jan 1st 2026
just date=20260101 collectors=rrc00-rrc25 pipeline
```

> **Note:** variable assignments must come **before** the recipe name in `just`.

Output lands in `./output-combined/20260101/`:

```
output-combined/20260101/
  topology-20260101.txt        # all-AF edge list
  topology-20260101-asns.txt   # unique ASN list
  topology-20260101-v4.txt     # IPv4-only edge list
  topology-20260101-v4-asns.txt
  topology-20260101-v6.txt     # IPv6-only edge list
  topology-20260101-v6-asns.txt
```

---

## The Pipeline

### Step 1a — Download RIS snapshots: `pipeline/get-mrt.py`

Downloads the 00:00 UTC RIB snapshot (`bview`) for a given date from one or more RIS collectors. Already-downloaded files are skipped. Failed transfers are reported per-collector without aborting the run.

```
./run.sh get-mrt.py --collectors <spec> --date <YYYYMMDD> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--collectors` | Collector specification. **Required.** See range notation below. |
| `--date` | Snapshot date in `YYYYMMDD` format. **Required.** |
| `--output-dir` | Directory to store downloaded `.gz` files. Default: `./mrt` |

#### Collector specification

`--collectors` accepts a comma-separated mix of individual names and ranges:

| Syntax | Example | Expands to |
|---|---|---|
| Individual | `rrc00` | `rrc00` |
| List | `rrc00,rrc04,rrc11` | `rrc00`, `rrc04`, `rrc11` |
| Range | `rrc00-rrc05` | `rrc00` through `rrc05` inclusive |
| Mixed | `rrc00-rrc03,rrc11,rrc23` | `rrc00`–`rrc03`, `rrc11`, `rrc23` |

```bash
./run.sh get-mrt.py --collectors rrc00-rrc25 --date 20260101
./run.sh get-mrt.py --collectors rrc00-rrc05,rrc11,rrc23 --date 20260101 --output-dir ./mrt/20260101
```

---

### Step 1b — Download RouteViews snapshots: `pipeline/get-routeviews.py`

Same interface as `get-mrt.py` but targets the RouteViews archive. Output files are `.bz2` format, processed transparently by step 2.

```
./run.sh get-routeviews.py --collectors <list> --date <YYYYMMDD> [--output-dir <dir>]
```

The `download-routeviews` justfile recipe uses a built-in working subset of ~40 available collectors. The `pipeline` recipe runs both `download` and `download-routeviews` automatically.

---

### Step 2 — Extract AS paths: `pipeline/extract-paths.py`

Calls `bgpreader` on each MRT file and writes three sidecar files per input into address-family subdirectories. A file set is skipped if all three outputs already exist.

AS path cleaning:
- **Prepending removed**: consecutive duplicate ASNs are collapsed (`64500 64500 64501` → `64500 64501`)
- **AS sets truncated**: paths containing AS sets (e.g. `{64500,64501}`) are truncated at the set; edges before it are kept

```
./run.sh extract-paths.py --input-files <glob> [--output-dir <dir>]
```

Output per input file (under `--output-dir`):

| Subdirectory | Suffix | Contents |
|---|---|---|
| `combined/` | `.txt.gz` | All paths (IPv4 + IPv6) |
| `v4/` | `.v4.txt.gz` | IPv4-only paths |
| `v6/` | `.v6.txt.gz` | IPv6-only paths |

```bash
./run.sh extract-paths.py --input-files "./mrt/20260101/*.gz" --output-dir ./paths/20260101
# Writes: paths/20260101/combined/*.txt.gz
#         paths/20260101/v4/*.v4.txt.gz
#         paths/20260101/v6/*.v6.txt.gz
```

---

### Step 3 — Build the topology: `pipeline/build-topology.py`

Reads AS path files, extracts edges, deduplicates, and writes the topology. Accepts multiple `--input` globs; workers process files in parallel.

```
./run.sh build-topology.py --input <glob> [--input <glob> ...] [OPTIONS]
```

| Flag | Description |
|---|---|
| `--input` | Glob matching path `.txt.gz` files. **Required.** Repeat to add patterns. |
| `--output` | Output edge list file. Default: `./topology.txt` |
| `--date` | Snapshot date `YYYYMMDD`. When set, the matching historical NRO stats are used for filtering. |
| `--filter-registered` | Drop any path containing a non-`assigned` ASN per NRO delegated stats. Default: off. |
| `--justify-output` | Zero-pad all ASNs to 8 digits in all output files. Default: off. |
| `--paths` | Also write a deduplicated path list. Large and expensive; off by default. |
| `--workers` | Number of parallel worker processes. Default: `cpu_count`. |

Always produces `{stem}.txt` (edge list) and `{stem}-asns.txt` (unique ASN list).

```bash
./run.sh build-topology.py \
  --input "./paths/20260101/combined/*.txt.gz" \
  --output ./output-combined/20260101/topology-20260101.txt \
  --filter-registered --justify-output --date 20260101
```

---

## Running the Full Pipeline

### Using `just` (recommended)

```bash
# Full pipeline: all RIS collectors + RouteViews
just date=20260101 collectors=rrc00-rrc25 pipeline

# Individual steps
just date=20260101 collectors=rrc00-rrc25 download
just date=20260101 download-routeviews
just date=20260101 process
just date=20260101 topology           # combined + v4 + v6
just date=20260101 topology-combined
just date=20260101 topology-v4
just date=20260101 topology-v6
```

Key `just` variables:

| Variable | Default | Description |
|---|---|---|
| `collectors` | `rrc00` | Collector spec (range notation supported) |
| `date` | *(required)* | Snapshot date `YYYYMMDD` |
| `mrt_dir` | `./mrt` | Root for downloaded MRT files |
| `paths_dir` | `./paths` | Root for extracted path files |
| `output_dir` | `./output-combined` | Root for topology output files |
| `workers` | *(cpu_count)* | Worker count for `build-topology.py` |
| `paths` | *(off)* | Set to `1` to write a consolidated paths file |
| `no_justify` | *(off)* | Set to `1` to disable zero-padding in `caida-peers` |

---

## Helper Tools

### CAIDA Peer Relationships: `pipeline/get-caida-peers.py`

Downloads the CAIDA AS relationships dataset for a given month and extracts peer-to-peer edges (`rel=0`). Always writes two files:
- `caida-peers-YYYYMM.txt` — peer-to-peer edge list
- `caida-tier1-YYYYMM.txt` — provider-free transit ASNs (~100–200 potential Tier 1 networks)

```bash
just date=202401 caida-peers
./run.sh get-caida-peers.py --date 202401
```

### Transit Frequency: `analysis/path-transit-freq.py`

Counts how often each AS appears as a transit hop. Strips the first (sensor) and last (origin) ASN; deduplicates intermediates per path (collapsing prepends).

```bash
./run.sh path-transit-freq.py --input paths/20260101/combined/bview.rrc00.20260101.0000.txt.gz
```

### Set Operations: `analysis/topology-ops.py`

Union or difference of two or more topology edge list files.

```bash
./run.sh topology-ops.py --op add --output combined.txt --justify-output file1.txt file2.txt file3.txt
./run.sh topology-ops.py --op sub --output disappeared.txt jan.txt mar.txt
```

### AS Lookup: `analysis/lookup-as.py`

Queries the RIPEstat Data API for holder name, announced prefix count, and last-seen timestamp.

```bash
./run.sh lookup-as.py --asn 15169
./run.sh lookup-as.py --file topology-dropped-asns.txt --output dropped-info.tsv
cat asns.txt | ./run.sh lookup-as.py
```

---

## Analysis Tools (`analysis/`)

| Tool | Purpose |
|---|---|
| `topology-to-gml.py` | Convert edge list to GML (Gephi, yEd, Cytoscape) |
| `gml-to-topology.py` | Convert GML back to edge list |
| `topology-core.py` | Filter to edges where both endpoints have degree ≥ N |
| `geo-filter.py` | Filter to edges where both ASNs are in given countries |
| `annotate-topology.py` | Add country + RIR columns to every edge |
| `hubs.py` | List ASNs with degree ≥ N |
| `asn-presence.py` | Build day-by-day ASN presence matrix |

All run via `./run.sh <tool>` or directly as `uv run analysis/<tool>`. See [Analysis Tools docs](https://carlos-cagnazzo.github.io/internet-topology-ris/analysis/) for full flag reference and examples.

---

## Fleet / Distributed Workflow

Process a full month of data distributed across multiple machines:

```bash
# Copy CSV templates
cp fleet/fleet.csv.example fleet.csv
cp fleet/assignments.csv.example assignments.csv

# Dispatch, monitor, collect, build
just dispatch                          # start slice jobs on all nodes
just status                            # check progress
just date='202607*' jobs=4 collect     # rsync path files back
just date='202607*' workers=4 topology # build the global topology
```

See [Fleet Workflow docs](https://carlos-cagnazzo.github.io/internet-topology-ris/fleet.html) for full setup instructions.

---

## RIS Collectors

| Collector | Location | | Collector | Location |
|---|---|---|---|---|
| rrc00 | Amsterdam, NL | | rrc12 | Frankfurt, DE |
| rrc01 | London, UK | | rrc13 | Moscow, RU |
| rrc03 | Amsterdam, NL | | rrc14 | Palo Alto, US |
| rrc04 | Geneva, CH | | rrc15 | São Paulo, BR |
| rrc05 | Vienna, AT | | rrc16 | Miami, US |
| rrc06 | Otemachi, JP | | rrc18 | Barcelona, ES |
| rrc07 | Stockholm, SE | | rrc19 | Johannesburg, ZA |
| rrc10 | Milan, IT | | rrc21 | Paris, FR |
| rrc11 | New York, US | | rrc23 | Singapore, SG |
| | | | rrc24 | Montevideo, UY |
