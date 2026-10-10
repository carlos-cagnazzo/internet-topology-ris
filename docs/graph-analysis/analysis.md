# Analysis Tools

---

## hubs.py

Lists ASNs with degree ≥ `--min-degree` from a topology edge list or GML file. Degree is computed in a single pass for `.txt` input — no GML conversion required.

```
uv run graph-analysis/hubs.py --input <file> --min-degree <N> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Topology edge list (`.txt`/`.txt.gz`) or `.gml` |
| `--output` | input stem + `-hubs.txt` | Output file |
| `--min-degree` | required | Minimum degree threshold |
| `--wide` | off | Two-column output (`ASN degree`), sorted by degree descending |

Without `--wide`: one ASN per line, sorted numerically. With `--wide`: two columns sorted by degree descending — useful for ranking.

### Examples

```bash
# List all ASNs with degree ≥ 100
uv run graph-analysis/hubs.py \
  --input output/20260101/topology-20260101.txt \
  --min-degree 100

# Ranked by degree
uv run graph-analysis/hubs.py \
  --input output/20260101/topology-20260101.txt \
  --min-degree 50 --wide
```

---

## annotate-topology.py

Enriches a topology edge list by appending four columns to each edge: `cc1 rir1 cc2 rir2` — the country code and RIR for each ASN, sourced from the NRO delegated stats.

```
uv run graph-analysis/annotate-topology.py --input <file> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Topology edge list (`.txt` or `.txt.gz`) |
| `--output` | input stem + `-annotated.txt` | Output file |
| `--date` | latest | NRO stats snapshot date `YYYYMMDD` |
| `--justify-output` | off | Zero-pad ASNs to 8 digits |

Country codes are lowercase ISO 3166-1 alpha-2. RIR names: `arin`, `ripencc`, `apnic`, `lacnic`, `afrinic`. ASNs absent from the NRO file are annotated as `unknown unknown`.

Input sort order is preserved.

### Output format

```
6057 3359 uy lacnic us arin
174 1916 us arin br lacnic
64512 65001 unknown unknown unknown unknown
```

### Examples

```bash
# Annotate with the NRO snapshot matching the topology date
uv run graph-analysis/annotate-topology.py \
  --input output/20260101/topology-20260101.txt \
  --date 20260101

# With zero-padding
uv run graph-analysis/annotate-topology.py \
  --input output/20260101/topology-20260101.txt \
  --output output/20260101/topology-20260101-annotated.txt \
  --date 20260101 --justify-output
```

---

## asn-presence.py

Builds a day-by-day ASN presence matrix from `{stem}-asns-YYYYMMDD.txt` files produced by `build-topology.py`. One row per unique ASN, one column per date, values `0`/`1`.

```
uv run graph-analysis/asn-presence.py --input <glob> [--output <file>]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Glob matching `*-asns-YYYYMMDD.txt` files. Repeat for multiple globs. |
| `--output` | first matched file's directory / `asn-presence.txt` | Output matrix file |

The first line is a header: `ASN YYYYMMDD YYYYMMDD …`. ASNs are zero-padded to 8 digits.

Load in pandas:

```python
import pandas as pd
df = pd.read_csv("asn-presence.txt", sep=r"\s+", index_col=0, dtype=int)
```

### Examples

```bash
uv run graph-analysis/asn-presence.py \
  --input "output/*/topology-*-asns.txt" \
  --output output/asn-presence.txt
```

---

## topology-ops.py

Set operations on two or more topology edge list files. Both plain (`6 22773`) and zero-padded (`00000006 00022773`) formats are handled; comparison is always numeric.

```
uv run topology-ops.py --op <add|sub> --output <file> [--justify-output] FILE [FILE ...]
```

| Argument | Description |
|---|---|
| `FILE ...` | Two or more topology edge list files (positional) |
| `--op add` | Union — all edges present in any input file, deduplicated |
| `--op sub` | Difference — edges in the first file not present in any remaining file |
| `--output` | Output file |
| `--justify-output` | Zero-pad ASNs to 8 digits |

### Examples

```bash
# Merge three dates
uv run topology-ops.py --op add \
  --output output/combined.txt --justify-output \
  output/20260101/topology-20260101.txt \
  output/20260201/topology-20260201.txt \
  output/20260301/topology-20260301.txt

# Links present in January but gone by March
uv run topology-ops.py --op sub \
  --output output/disappeared.txt \
  output/20260101/topology-20260101.txt \
  output/20260301/topology-20260301.txt
```

---

## lookup-as.py

Queries the [RIPEstat Data API](https://stat.ripe.net/docs/data_api) for one or more ASNs. Returns AS holder name, announced prefix count, last-seen timestamp, and announced status.

```
uv run lookup-as.py --asn <N>
uv run lookup-as.py --file <file>
cat asns.txt | uv run lookup-as.py
```

| Flag | Default | Description |
|---|---|---|
| `--asn` | — | Single ASN to look up |
| `--file` | — | File with one ASN per line; `-` for stdin |
| `--output` | — | Write results as TSV alongside terminal output |
| `--concurrency` | `10` | Max parallel API requests (batch mode) |

Batch mode shows a live progress bar. Results are displayed as a rich table.

### Examples

```bash
# Single ASN
uv run lookup-as.py --asn 15169

# Batch from the dropped-ASNs list
uv run lookup-as.py \
  --file output/20260101/topology-20260101-dropped-asns.txt \
  --output output/20260101/dropped-asns-info.tsv

# Pipe the hub list
uv run graph-analysis/hubs.py \
  --input output/20260101/topology-20260101.txt \
  --min-degree 100 | uv run lookup-as.py
```
