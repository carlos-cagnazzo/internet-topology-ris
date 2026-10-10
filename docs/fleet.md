# Fleet Workflow

Processing a full day of data (all RIS collectors + RouteViews) can take several hours on a single machine. The fleet workflow distributes the download and extraction steps across multiple machines, then merges the results centrally.

---

## Overview

```
Node A: just date=YYYYMMDD collectors=rrc00-rrc08 slice
Node B: just date=YYYYMMDD collectors=rrc09-rrc17 slice
Node C: just date=YYYYMMDD collectors=rrc18-rrc25 slice

Central: just date=YYYYMMDD collect
Central: just date=YYYYMMDD topology
```

The `slice` recipe runs `download` + `process` only — no topology is built on the node. Path files are named after their collector, so all nodes write into the same destination directory without conflicts when collected centrally.

Optionally, you can also run `just date=YYYYMMDD topology` on each node to inspect a partial topology while the central collection is pending.

---

## Setup

### 1. Create fleet.csv

Copy the example and fill in your machines:

```bash
cp fleet.csv.example fleet.csv
```

Format: `username,hostname,/absolute/path/to/repo` — one machine per line. Lines starting with `#` are ignored.

```
# username,hostname,repo_path
carlos,node1.example.com,/home/carlos/src/internet-topology-ris
carlos,node2.example.com,/home/carlos/src/internet-topology-ris
carlos,mac.local,/Users/carlos/src/internet-topology-ris
```

`fleet.csv` is gitignored — it contains hostnames and paths specific to your deployment. The `fleet.csv.example` template is tracked.

### 2. Ensure SSH access

All machines in `fleet.csv` must be reachable with a shared SSH key from the central machine. Test with:

```bash
ssh carlos@node1.example.com "echo ok"
```

### 3. Clone the repo on each node

Each node needs the repo cloned at the path listed in `fleet.csv`:

```bash
git clone https://github.com/carlos-cagnazzo/internet-topology-ris \
  /home/carlos/src/internet-topology-ris
```

---

## Running a slice

On each node, assign a collector range and run `slice`:

```bash
just date=20260101 collectors=rrc00-rrc08 slice
```

For RouteViews, you can split manually by passing specific collectors to `get-routeviews.py` directly — the `download-routeviews` recipe runs all 12 default collectors as a unit.

---

## Collecting path files

Once all nodes have finished their slices, collect the path files from the central machine:

```bash
just date=20260101 collect
```

This runs `collect.sh`, which rsyncs each node's `paths/20260101/` directory into the local `./paths/20260101/`. Up to `jobs` rsyncs run in parallel (default 2):

```bash
just date=20260101 jobs=4 collect
```

Per-host logs go to `./logs/collect-20260101/<hostname>.log`. Any failed hosts are reported at the end; the exit code is non-zero if any rsync failed.

---

## Building the global topology

After collecting, build the topology from all merged path files:

```bash
just date=20260101 topology
```

---

## Fetching output files from remote machines

`fetch-results.sh` collects **output** files (topologies) rather than path files, using rsync into per-host subdirectories to avoid conflicts:

```bash
./fetch-results.sh
```

Configure `SOURCES`, `INCLUDES`, and `EXCLUDE` at the top of the script. Count unique ASNs across all fetched topologies:

```bash
zcat fetch/*/topology-????????.txt \
  | awk '{print $1; print $2}' \
  | sort -un \
  | wc -l
```

!!! note "Legacy"
    `fetch-results.sh` predates the fleet/collect workflow and may be superseded by it for most use cases. It remains useful for ad-hoc collection without a `fleet.csv`.

---

## Typical three-date workflow across a fleet

```bash
# On each node (different collector slice per node):
for d in 20260101 20260201 20260301; do
  just date=$d collectors=rrc00-rrc08 slice
done

# On the central machine:
for d in 20260101 20260201 20260301; do
  just date=$d jobs=4 collect
  just date=$d topology
done
```
