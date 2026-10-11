# Build Topology

`build-topology.py` reads AS path files, extracts edges, deduplicates, and writes the topology. It accepts multiple `--input` globs and merges RIS and RouteViews files seamlessly. Workers process files in parallel.

```
uv run build-topology.py --input <glob> [--input <glob> ...] [OPTIONS]
```

---

## Flags

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Glob matching path `.txt` files. Repeat to add more patterns. |
| `--output` | `./topology.txt` | Output file for the edge list. |
| `--date` | *(none)* | Snapshot date `YYYYMMDD`. Required when using `--filter-registered` with a historical NRO snapshot. |
| `--filter-registered` | off | Exclude paths containing any non-assigned ASN (see below). |
| `--justify-output` | off | Zero-pad all ASNs to 8 digits in all output files. |
| `--paths` | off | Also write a deduplicated path list `{stem}-paths.txt`. Large and expensive; off by default. Checkpoint/resume aware — writes `.paths.gz` sidecars alongside `.edges`. |
| `--workers` | `cpu_count` | Number of parallel worker processes. |
| `--keep-edges` | off | Retain `.edges` and `.paths.gz` checkpoint sidecars after a successful merge (useful to re-run with different flags without reprocessing). |

---

## Output files

All files are written to the same directory as `--output`, named after its stem.

| File | Description |
|---|---|
| `{stem}.txt` | Deduplicated undirected edge list. One `AS1 AS2` per line, `AS1 < AS2`, sorted numerically. |
| `{stem}-asns.txt` | Sorted list of all unique ASNs in the topology. |
| `{stem}-paths.txt` | *(only with `--paths`)* Deduplicated AS paths, sorted numerically by leading ASN. |
| `{stem}-dropped-asns.txt` | *(only with `--filter-registered`)* ASNs excluded because they are not `assigned` in the NRO stats. |

---

## --filter-registered

Filters at the **path level**: a path is excluded entirely if *any* of its ASNs is not `assigned` in the [NRO delegated extended stats](https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats). This removes paths transiting unallocated, reserved, or private ASNs.

The NRO stats file is cached next to the input path files:

- **Historical** (when `--date` is provided): `nro-delegated-stats-YYYYMMDD` — fetched once and cached permanently (the historical file never changes).
- **Latest** (no `--date`): `nro-delegated-stats` — re-downloaded if older than 24 hours.

---

## --justify-output

Zero-pads all ASN numbers to 8 digits in every output file, making them fixed-width:

```
# Without --justify-output   # With --justify-output
6 22773                       00000006 00022773
1299 3356                     00001299 00003356
```

Fixed-width output is useful for lexicographic sorting tools and for consistent alignment in downstream processing.

---

## Edge ordering

Edges are stored as integer-ordered tuples: the smaller ASN always comes first. String ordering is **not** used — `"22773" < "6"` as strings but `22773 > 6` as integers.

---

## Justfile

The `topology` recipe runs `build-topology.py` three times (combined, v4, v6):

```bash
just date=20260101 topology

# Individual variants
just date=20260101 topology-combined
just date=20260101 topology-v4
just date=20260101 topology-v6

# With consolidated paths file (combined only)
just date=20260101 paths=1 topology-combined

# Limit workers to avoid OOM on large datasets
just date='202607*' workers=4 topology-combined

# Glob date — all of July
just date='202607*' topology
```

### Justfile variables for topology

| Variable | Default | Description |
|---|---|---|
| `workers` | *(empty = cpu_count)* | Worker count for `build-topology.py`. Set lower to avoid OOM. |
| `paths` | *(empty = off)* | Set to any non-empty value (e.g. `1`) to write a consolidated path file for `topology-combined`. |

---

## Examples

```bash
# Combined topology from a single date (RIS + RouteViews)
uv run build-topology.py \
  --input "./paths/20260101/*.txt.gz" \
  --output ./output/20260101/topology-20260101.txt \
  --filter-registered \
  --justify-output \
  --date 20260101

# Also write the path list, use 8 workers
uv run build-topology.py \
  --input "./paths/20260101/*.txt.gz" \
  --output ./output/20260101/topology-20260101.txt \
  --paths \
  --workers 8
```
