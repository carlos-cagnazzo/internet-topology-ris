# Fleet Workflow

Processing a full day of data (all RIS collectors + RouteViews) can take several hours on a single machine. The fleet workflow distributes download and extraction across multiple machines, then merges the results centrally.

---

## Overview

```
Central: just dispatch
  → Node A: tmux slice-20260701-20260715  (rrc00-rrc12, serially)
  → Node B: tmux slice-20260716-20260731  (rrc13-rrc25, serially)
  → Node B: tmux slice-20260801-20260815  (rrc13-rrc25, serially)  ← parallel session

Central: just status            # check progress at any time

Central: just date='202607*' collect
Central: just date='202607*' topology
```

Each fleet node runs `slice` (download RIS + RouteViews + extract paths) for its assigned dates independently. The central machine dispatches, monitors, collects, and builds the final topology.

---

## Setup

### 1. Create fleet.csv

```bash
cp fleet.csv.example fleet.csv
```

Format: `username,hostname,/absolute/path/to/repo` — one machine per line.

```
# username,hostname,repo_path
carlos,gauss.xt6labs.io,/home/carlos/src/internet-topology-ris
carlos,node2.example.com,/home/carlos/src/internet-topology-ris
carlos,mac.local,/Users/carlos/src/internet-topology-ris
```

`fleet.csv` is gitignored — specific to your deployment. The `fleet.csv.example` template is tracked.

### 2. Create assignments.csv

```bash
cp assignments.csv.example assignments.csv
```

Format: `hostname,start_date,end_date,collectors` — one line per tmux session.

```
# hostname,start_date,end_date,collectors
gauss.xt6labs.io,20260701,20260715,rrc00-rrc12
gauss.xt6labs.io,20260720,20260725,rrc00-rrc12
node2.example.com,20260716,20260719,rrc13-rrc25
node2.example.com,20260726,20260731,rrc13-rrc25
```

- **One line = one tmux session** on that host, iterating its date range serially
- **Multiple lines per host** = multiple parallel sessions on that host
- Ranges can be discontinuous — just add more lines
- `assignments.csv` is gitignored; edit it freely without committing

### 3. Ensure SSH access

All machines must be reachable with a shared SSH key from the central machine:

```bash
ssh carlos@gauss.xt6labs.io "echo ok"
```

### 4. Clone the repo on each node

```bash
git clone https://github.com/carlos-cagnazzo/internet-topology-ris \
  /home/carlos/src/internet-topology-ris
```

---

## Dispatching work

```bash
just dispatch           # dispatch all assigned sessions (2 parallel SSH connections)
just jobs=4 dispatch    # more parallelism
```

For each line in `assignments.csv`, `dispatch.sh`:

1. Looks up `user` and `repo` from `fleet.csv`
2. SSHes to the node and checks whether a tmux session named `slice-START-END` already exists
3. If not: writes a dated slice script to `/tmp/dispatch-slice-START-END.sh` on the remote and starts it in a new tmux session

The session runs a loop like:
```bash
cd /repo && git pull -q
for d in 20260701 20260702 … 20260715; do
    just date=$d collectors=rrc00-rrc12 slice
done
```

`slice` is self-contained: it downloads RIS collectors, downloads RouteViews, and extracts paths — all for that date.

**Re-running `just dispatch` is safe** — sessions that already exist are skipped.

---

## Checking progress

```bash
just status
```

SSHes to each assigned host in one round-trip, checks running tmux sessions and existing `paths/` directories, and prints a table:

```
gauss.xt6labs.io
  slice-20260701-20260715  rrc00-rrc12    [running  8/15]
     20260701✓  20260702✓  20260703✓  20260704✓  20260705✓  20260706✓  20260707✓
     20260708✓  20260709·  20260710·  20260711·  20260712·  20260713·  20260714·
     20260715·

node2.example.com
  slice-20260716-20260719  rrc13-rrc25    [done     4/4]
     20260716✓  20260717✓  20260718✓  20260719✓
  slice-20260726-20260731  rrc13-rrc25    [pending  0/6]
     20260726·  20260727·  20260728·  20260729·  20260730·  20260731·
```

Status values: `running`, `done`, `partial` (some dates complete, session gone), `pending`.

---

## Collecting path files

Once nodes are done, collect from the central machine:

```bash
just date='202607*' collect          # all of July
just date='202607*' jobs=4 collect   # with more parallelism
```

`date` accepts glob patterns. Files already present locally are skipped (`--ignore-existing`). Per-host logs go to `./logs/collect-202607/<hostname>.log`.

---

## Building the global topology

```bash
just date='202607*' topology          # combined + v4 + v6
just date='202607*' topology-combined # combined only
```

!!! tip "OOM on large datasets"
    `build-topology.py` defaults to `cpu_count` workers. On machines with many cores this can exhaust memory. Use `workers` to limit it:
    ```bash
    just date='202607*' workers=2 topology-combined
    ```

---

## Typical full-month workflow

```bash
# 1. Edit assignments.csv with the month's ranges and collector splits
#    (each line = one tmux session)

# 2. Dispatch from the central machine
just dispatch

# 3. Check progress periodically
just status

# 4. Once all done, collect and build
just date='202607*' jobs=4 collect
just date='202607*' workers=4 topology
```

---

## Fetching output files from remote machines

`fetch-results.sh` collects topology **output** files (not path files) from remote machines via rsync into per-host subdirectories. Configure `SOURCES`, `INCLUDES`, and `EXCLUDE` at the top of the script.

!!! note "Legacy"
    `fetch-results.sh` predates the dispatch/collect workflow. It remains useful for ad-hoc collection without `fleet.csv` / `assignments.csv`.
