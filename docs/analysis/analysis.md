# Analysis Tools

---

## hubs.py

Lists ASNs with degree ≥ `--min-degree` from a topology edge list or GML file. Degree is computed in a single pass for `.txt` input — no GML conversion required.

```
./run.sh hubs.py --input <file> --min-degree <N> [OPTIONS]
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
./run.sh hubs.py \
  --input output-combined/20260101/topology-20260101.txt \
  --min-degree 100

# Ranked by degree
./run.sh hubs.py \
  --input output-combined/20260101/topology-20260101.txt \
  --min-degree 50 --wide
```

---

## annotate-topology.py

Enriches a topology edge list by appending four columns to each edge: `cc1 rir1 cc2 rir2` — the country code and RIR for each ASN, sourced from the NRO delegated stats.

```
./run.sh annotate-topology.py --input <file> [OPTIONS]
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
./run.sh annotate-topology.py \
  --input output-combined/20260101/topology-20260101.txt \
  --date 20260101

# With zero-padding
./run.sh annotate-topology.py \
  --input output-combined/20260101/topology-20260101.txt \
  --output output-combined/20260101/topology-20260101-annotated.txt \
  --date 20260101 --justify-output
```

---

## asn-presence.py

Builds a day-by-day ASN presence matrix from `{stem}-asns-YYYYMMDD.txt` files produced by `build-topology.py`. One row per unique ASN, one column per date, values `0`/`1`.

```
./run.sh asn-presence.py --input <glob> [--output <file>]
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
./run.sh asn-presence.py \
  --input "output-combined/*/topology-*-asns.txt" \
  --output output-combined/asn-presence.txt
```

---

## topology-ops.py

Set operations on two or more topology edge list files. Both plain (`6 22773`) and zero-padded (`00000006 00022773`) formats are handled; comparison is always numeric.

```
./run.sh topology-ops.py --op <add|sub> --output <file> [--justify-output] FILE [FILE ...]
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
./run.sh topology-ops.py --op add \
  --output output-combined/combined.txt --justify-output \
  output-combined/20260101/topology-20260101.txt \
  output-combined/20260201/topology-20260201.txt \
  output-combined/20260301/topology-20260301.txt

# Links present in January but gone by March
./run.sh topology-ops.py --op sub \
  --output output-combined/disappeared.txt \
  output-combined/20260101/topology-20260101.txt \
  output-combined/20260301/topology-20260301.txt
```

---

## lookup-as.py

Queries the [RIPEstat Data API](https://stat.ripe.net/docs/data_api) for one or more ASNs. Returns AS holder name, announced prefix count, last-seen timestamp, and announced status.

```
./run.sh lookup-as.py --asn <N>
./run.sh lookup-as.py --file <file>
cat asns.txt | ./run.sh lookup-as.py
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
./run.sh lookup-as.py --asn 15169

# Batch from the dropped-ASNs list
./run.sh lookup-as.py \
  --file output-combined/20260101/topology-20260101-dropped-asns.txt \
  --output output-combined/20260101/dropped-asns-info.tsv

# Pipe the hub list
./run.sh hubs.py \
  --input output-combined/20260101/topology-20260101.txt \
  --min-degree 100 | ./run.sh lookup-as.py
```

---

## path-transit-freq.py

Counts how often each AS appears as a transit hop across all paths in a file. The first ASN (sensor) and last ASN (origin) of each path are ignored; intermediate ASNs are deduplicated per path to collapse prepends.

```
./run.sh path-transit-freq.py --input <file> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Path file (`.txt` or `.txt.gz`) |
| `--output` | input stem + `-transit-freq.txt` | Output file |
| `--justify-output` / `--no-justify-output` | on | Zero-pad ASNs to 8 digits |

Output is sorted by frequency descending. Paths with ≤2 ASNs (no transit hop) are skipped and counted; the total is reported on exit.

### Examples

```bash
# Analyse a combined path file
./run.sh path-transit-freq.py \
  --input paths/20260101/combined/bview.rrc00.20260101.0000.txt.gz

# Without zero-padding
./run.sh path-transit-freq.py \
  --input paths/20260101/combined/bview.rrc00.20260101.0000.txt.gz \
  --no-justify-output
```
