# Pipeline Overview

The pipeline is a linear three-step process orchestrated by `just`.

```
get-mrt.py          ──┐
                       ├──▶  extract-paths.py  ──▶  build-topology.py
get-routeviews.py   ──┘

./mrt/<date>/       ──▶  ./paths/<date>/       ──▶  ./output/<date>/
  *.gz (RIS)              *.txt.gz
  *.bz2 (RouteViews)      *.v4.txt.gz
                          *.v6.txt.gz
```

---

## Justfile recipes

| Recipe | What it runs |
|---|---|
| `pipeline` | `download` + `download-routeviews` + `process` + `topology` |
| `download` | `get-mrt.py` for the given collectors |
| `download-routeviews` | `get-routeviews.py` for the default RouteViews subset |
| `process` | `extract-paths.py` on all `.gz` and `.bz2` files |
| `topology` | `topology-combined` + `topology-v4` + `topology-v6` |
| `topology-combined` | `build-topology.py` on combined path files |
| `topology-v4` | `build-topology.py` on IPv4 path files |
| `topology-v6` | `build-topology.py` on IPv6 path files |
| `slice` | `download` + `download-routeviews` + `process` (self-contained, for fleet nodes) |
| `dispatch` | dispatch slice jobs to all fleet nodes via `assignments.csv` + `fleet.csv` |
| `status` | report per-date progress for all assigned fleet nodes |
| `collect` | rsync path files from all fleet nodes |
| `pack-and-publish` | tar + copy to a publish point |

## Justfile variables

| Variable | Default | Description |
|---|---|---|
| `date` | *(empty)* | Snapshot date `YYYYMMDD`. Required for `download` and `topology`. |
| `collectors` | `rrc00` | RIS collector spec — individual, list, or range (e.g. `rrc00-rrc25`). |
| `mrt_dir` | `./mrt` | Root for downloaded MRT files. Date subdir created automatically. |
| `paths_dir` | `./paths` | Root for extracted path files. Date subdir created automatically. |
| `output_dir` | `./output` | Root for topology output. Date subdir created automatically. |
| `output` | `topology-<date>.txt` | Combined output filename. |
| `output_v4` | `topology-<date>-v4.txt` | IPv4 output filename. |
| `output_v6` | `topology-<date>-v6.txt` | IPv6 output filename. |
| `jobs` | `2` | Parallel connections for `collect` and `dispatch`. |
| `workers` | *(empty)* | Worker count for `build-topology.py` (topology recipes). Omit for `cpu_count`. Set low (e.g. `2`) to avoid OOM on large datasets. |
| `pubpoint` | `/var/www/html/topo` | Destination for `pack-and-publish`. |

---

## Pages in this section

- [Download](download.md) — `get-mrt.py` and `get-routeviews.py`
- [Extract Paths](extract.md) — `extract-paths.py`
- [Build Topology](topology.md) — `build-topology.py`
