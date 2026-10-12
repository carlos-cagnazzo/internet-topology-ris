# Download

Two scripts handle downloading, one per data source. Both follow the same interface and produce files in the same output directory; `extract-paths.py` handles both transparently.

---

## get-mrt.py — RIPE RIS

Downloads the 00:00 UTC RIB snapshot (`bview`) for a given date from one or more RIS collectors. Already-downloaded files are skipped. Failed transfers are reported per-collector and counted in the summary without aborting the run.

```
./run.sh get-mrt.py --collectors <spec> --date <YYYYMMDD> [--output-dir <dir>]
```

| Flag | Required | Description |
|---|---|---|
| `--collectors` | yes | Collector specification (see below) |
| `--date` | yes | Snapshot date in `YYYYMMDD` format |
| `--output-dir` | no | Output directory. Default: `./mrt` |

Output filenames: `bview.rrcXX.YYYYMMDD.0000.gz`

### Collector specification

`--collectors` accepts a comma-separated mix of individual names and ranges:

| Syntax | Example | Expands to |
|---|---|---|
| Individual | `rrc00` | `rrc00` |
| List | `rrc00,rrc04,rrc11` | rrc00, rrc04, rrc11 |
| Range | `rrc00-rrc05` | rrc00 through rrc05 |
| Mixed | `rrc00-rrc03,rrc11` | rrc00–rrc03, rrc11 |

RIS has collectors `rrc00` through `rrc25`. Use `rrc00-rrc25` to collect from all of them.

### Examples

```bash
# All collectors
just date=20260101 collectors=rrc00-rrc25 download

# Single collector
./run.sh get-mrt.py --collectors rrc00 --date 20260101

# Mixed specification
./run.sh get-mrt.py --collectors rrc00-rrc05,rrc11,rrc23 --date 20260101 --output-dir ./mrt/20260101
```

---

## get-routeviews.py — RouteViews

Same interface as `get-mrt.py` but targets the RouteViews archive. Output files are `.bz2` format.

```
./run.sh get-routeviews.py --collectors <list> --date <YYYYMMDD> [--output-dir <dir>]
```

| Flag | Required | Description |
|---|---|---|
| `--collectors` | yes | Comma-separated RouteViews collector IDs |
| `--date` | yes | Snapshot date in `YYYYMMDD` format |
| `--output-dir` | no | Output directory. Default: `./mrt` |

Output filenames: `rib.<collector>.YYYYMMDD.0000.bz2`

RouteViews collectors do not follow a numeric sequence, so range notation is not supported — use a comma-separated list.

### Default collector set

The `download-routeviews` justfile recipe uses a working subset of the ~40 available collectors:

| Collector ID | Region |
|---|---|
| `route-views.amsix` | Europe (AMS-IX) |
| `namex.fco` | Europe (Rome) |
| `hkix.hkg` | Asia (Hong Kong) |
| `route-views.sg` | Asia (Singapore) |
| `route-views.chicago` | North America |
| `route-views2` | North America |
| `pacwave.lax` | North America |
| `crix.sjo` | North America |
| `ix-br2.gru` | Latin America (São Paulo) |
| `route-views.rio` | Latin America (Rio) |
| `route-views.kixp` | Africa (Nairobi) |
| `route-views.perth` | Oceania |

To add more, extend the `--collectors` argument in the `download-routeviews` recipe in the `justfile`. Full collector index: <https://www.routeviews.org/routeviews/index.php/collectors/>

### Examples

```bash
# Default subset via justfile
just date=20260101 download-routeviews

# Custom selection
./run.sh get-routeviews.py \
  --collectors route-views.amsix,route-views2,route-views.sg \
  --date 20260101 \
  --output-dir ./mrt/20260101
```

---

## Downloading a full month of RouteViews data

`download-routeviews-month.sh` downloads one bview per day for an entire month, running up to N days in parallel:

```bash
./fleet/download-routeviews-month.sh YYYYMM [parallel_jobs]
```

```bash
# Download all of January 2026, 4 days in parallel
./fleet/download-routeviews-month.sh 202601 4
```

Output: `./mrt-routeviews/YYYYMMDD/`  
Logs: `./logs/routeviews-YYYYMM/YYYYMMDD.log`
