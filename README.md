# Internet Topology from RIPE RIS

Reconstruct the Internet's AS-level topology from publicly available BGP routing data published by [RIPE NCC's Routing Information Service (RIS)](https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris).

The pipeline downloads MRT RIB snapshot files, extracts AS paths from them, and produces a deduplicated undirected edge list where each line represents a peering link between two Autonomous Systems:

```
13335 15169
1299 3356
174 3257
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

---

## The Pipeline

### Step 1 — Download MRT RIB snapshots: `get-mrt.py`

Downloads the 00:00 UTC RIB snapshot (`bview`) for a given date from one or more RIS collectors.

```
usage: get-mrt.py --collectors <rrcXX,...> --date <YYYYMMDD> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--collectors` | Comma-separated list of RIS collectors (e.g. `rrc00,rrc01,rrc04`). **Required.** |
| `--date` | Date of the snapshot in `YYYYMMDD` format. **Required.** |
| `--output-dir` | Directory to store downloaded `.gz` files. Default: `./mrt` |

Files are downloaded from:
```
https://data.ris.ripe.net/rrcXX/YYYY.MM/bview.YYYYMMDD.0000.gz
```

Already-downloaded files are skipped. Progress is shown during multi-file downloads.

**Example:**
```bash
uv run get-mrt.py --collectors rrc00,rrc01,rrc04 --date 20240101
```

---

### Step 2 — Extract AS paths: `process-mrt.py`

Processes downloaded MRT files using `bgpreader`, extracting one AS path per line into sidecar `.txt` files.

```
usage: process-mrt.py --input-files <glob> [--output-dir <dir>]
```

| Flag | Description |
|---|---|
| `--input-files` | Glob pattern matching the MRT `.gz` files to process (e.g. `"./mrt/*.gz"`). **Required.** |
| `--output-dir` | Directory to write `.txt` output files. Default: `./paths` |

Each output file has the same base name as its input MRT file, with a `.txt` extension. Each line contains a single AS path as space-separated ASNs:

```
13335 15169 6461
1299 3356 15169
...
```

Files whose `.txt` counterpart already exists are skipped. Progress is shown during multi-file processing.

**Example:**
```bash
uv run process-mrt.py --input-files "./mrt/*.gz" --output-dir ./paths
```

---

### Step 3 — Build the topology: `build-topology.py`

Reads AS path files, extracts all AS-to-AS links, and writes a deduplicated undirected edge list.

```
usage: build-topology.py --input <glob> [--output <file>]
```

| Flag | Description |
|---|---|
| `--input` | Glob pattern matching `.txt` AS path files. **Required.** |
| `--output` | Output file for the edge list. Default: `./topology.txt` |

**Edge extraction rules:**
- Consecutive duplicate ASNs are collapsed before extracting edges (BGP prepending is removed): `64500 64500 64501` → `64500 64501`.
- AS sets (e.g. `{64500,64501}`) terminate path processing at that segment; edges before the set are kept, the set itself and everything after it are discarded.
- Links are undirected: `AS1 AS2` and `AS2 AS1` are treated as the same edge and deduplicated.

**Example:**
```bash
uv run build-topology.py --input "./paths/*.txt" --output topology.txt
```

---

## Running the Full Pipeline

The following example reconstructs the topology as seen on January 1st, 2024, using four geographically distributed RIS collectors.

```bash
# 1. Download RIB snapshots
uv run get-mrt.py \
  --collectors rrc00,rrc01,rrc04,rrc06 \
  --date 20240101 \
  --output-dir ./mrt

# 2. Extract AS paths from the downloaded files
uv run process-mrt.py \
  --input-files "./mrt/*.gz" \
  --output-dir ./paths

# 3. Build the deduplicated edge list
uv run build-topology.py \
  --input "./paths/*.txt" \
  --output topology.txt
```

The resulting `topology.txt` will contain one undirected AS link per line.

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
