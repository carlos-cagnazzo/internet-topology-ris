# graph-analysis

Graph analysis tools for AS-level Internet topology files. All tools are run via `uv run` from the repository root and share the root `pyproject.toml`.

Input topology files use the two-column `ASN1 ASN2` format produced by `build-topology.py`, with `ASN1 < ASN2` (numerically). Plain and gzip-compressed files are accepted transparently.

---

## Tools

### `topo-to-nx.py` — Topology to GML

Imports a topology edge list into an undirected [NetworkX](https://networkx.org/) graph and writes it as a GML file for use with Gephi, yEd, Cytoscape, or other graph tools.

Zero-padded ASNs are normalised to plain integers. Each node carries an `asn` (integer) and a `label` (plain ASN string) attribute. Edges carry no attributes. With `--enrich`, nodes with degree >= `--min-degree` have their label replaced with the AS holder name from RIPEstat; names are cached at `~/.cache/internet-topology-ris/as-names.json` with a 60-day TTL.

```
uv run graph-analysis/topo-to-nx.py --input <topology.txt> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | Topology edge list (`.txt` or `.txt.gz`) |
| `--output` / `-o` | input stem + `.gml` | GML output path |
| `--enrich/--no-enrich` | off | Fetch AS holder names from RIPEstat |
| `--min-degree` | 3 | With `--enrich`: degree threshold for name lookup |
| `--concurrency` | 10 | Max parallel RIPEstat requests |
| `--cache` | `~/.cache/…/as-names.json` | AS name cache path |

**Examples:**

```bash
# Basic conversion
uv run graph-analysis/topo-to-nx.py \
    --input output/20240101/topology.txt \
    --output output/20240101/topology.gml

# With AS holder name enrichment for high-degree nodes
uv run graph-analysis/topo-to-nx.py \
    --input output/20240101/topology.txt \
    --enrich --min-degree 100
```

---

### `hubs.py` — High-degree ASN list

Reads a GML file and writes a list of all ASNs whose degree is greater than or equal to a given threshold.

Without `--wide`: one ASN per line, sorted numerically.
With `--wide`: two columns (`ASN degree`), sorted by degree descending.

```
uv run graph-analysis/hubs.py --input <topology.gml> --min-degree <N> [--output <out.txt>] [--wide]
```

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | GML file produced by `topo-to-nx.py` |
| `--output` / `-o` | input stem + `-hubs.txt` | Output file |
| `--min-degree` / `-d` | required | Minimum degree (inclusive) |
| `--wide` | off | Add degree column; sort by degree descending |

**Examples:**

```bash
# ASNs with degree >= 1000, sorted numerically
uv run graph-analysis/hubs.py \
    --input output/20240101/topology.gml \
    --min-degree 1000

# Same, with degree column, sorted by degree
uv run graph-analysis/hubs.py \
    --input output/20240101/topology.gml \
    --min-degree 1000 \
    --wide
```

---

### `core.py` — Core subgraph extraction

Filters a topology edge list to retain only edges where **both** endpoints have degree >= a given threshold. The result is a valid topology file (same two-column format, `ASN1 < ASN2`, sorted numerically by ASN1) and can be used as input to any other tool in the pipeline.

Degree is computed from the input file itself (no GML required). Accepts plain or gzip-compressed topology files.

```
uv run graph-analysis/core.py --input <topology.txt> --min-degree <N> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | Topology edge list (`.txt` or `.txt.gz`) |
| `--output` / `-o` | input stem + `-core.txt` | Output file |
| `--min-degree` / `-d` | required | Minimum degree for both endpoints (inclusive) |
| `--wide` | off | Add `DEG1 DEG2` columns |
| `--justify-output` | off | Zero-pad ASNs to 8 digits |

**Examples:**

```bash
# Edges where both endpoints have degree >= 100
uv run graph-analysis/core.py \
    --input output/20240101/topology.txt \
    --min-degree 100

# Same, with degree columns and zero-padded ASNs
uv run graph-analysis/core.py \
    --input output/20240101/topology.txt \
    --min-degree 100 \
    --wide \
    --justify-output
```

---

### `nx-to-topo.py` — GML to topology edge list

The inverse of `topo-to-nx.py`. Reads a GML file and writes a two-column
topology file (`ASN1 ASN2` per line, `ASN1 < ASN2`, sorted numerically by ASN1).
ASNs are always taken from the node `asn` attribute, so enriched GML files
(where node keys may be holder name strings) are handled correctly.
Exits with an error if the input is not a valid GML file.

```
uv run graph-analysis/nx-to-topo.py --input <topology.gml> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | GML file |
| `--output` / `-o` | input stem + `.txt` | Output topology file |
| `--min-degree` / `-d` | off | Only include edges where both endpoints have degree ≥ N |
| `--justify-output` | off | Zero-pad ASNs to 8 digits |

**Examples:**

```bash
# Basic round-trip back to topology format
uv run graph-analysis/nx-to-topo.py \
    --input output/20240101/topology.gml

# Export only the dense core with zero-padded ASNs
uv run graph-analysis/nx-to-topo.py \
    --input output/20240101/topology.gml \
    --min-degree 100 \
    --justify-output
```

---

### `geo-filter.py` — Filter topology by country

Filters a topology to edges where **both** ASNs are assigned to one of the
given ISO 3166-1 alpha-2 country codes, according to the NRO delegated stats.
ASNs not found in the NRO file are excluded. Always produces two output files:
a `.txt` topology edge list and a `.gml` graph (nodes carry a `country`
attribute in addition to `asn` and `label`).

Accepts either a `.txt`/`.txt.gz` topology file or a `.gml` file as input.
The NRO stats file is fetched automatically and cached next to the input file.
With `--date`, the historical snapshot for that date is used (cached
permanently). Without `--date`, the latest file is used (re-fetched if older
than 24 hours).

```
uv run graph-analysis/geo-filter.py --input <file> --countries <CC,...> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | Topology `.txt`/`.txt.gz` or `.gml` file |
| `--countries` / `-c` | required | Comma-separated ISO 3166-1 alpha-2 codes (e.g. `BR,AR,CL`) |
| `--output` / `-o` | input stem + `-geo` | Output base path (without extension); `.txt` and `.gml` are always written |
| `--date` | latest | NRO stats snapshot date `YYYYMMDD` |
| `--justify-output` | off | Zero-pad ASNs to 8 digits in `.txt` output |

**Examples:**

```bash
# Filter to LATAM Southern Cone countries
uv run graph-analysis/geo-filter.py \
    --input output/20240101/topology.txt \
    --countries BR,AR,CL,UY

# Historical NRO snapshot, GML input, justified output
uv run graph-analysis/geo-filter.py \
    --input output/20240101/topology.gml \
    --countries BR \
    --date 20240101 \
    --justify-output
```

---

## Historic

**`topology-to-gml.py`** — An earlier standalone script at the repository root that converted a topology edge list to GML with optional RIPEstat enrichment. Its functionality has been fully merged into `graph-analysis/topo-to-nx.py` (which adds gzip support, progress reporting, and integer `asn` node attributes). The original script was removed in the `v0.2.0` → `v0.3.0` development cycle.

---

## Typical workflow

```bash
# 1. Convert topology to GML (for Gephi / graph tools)
uv run graph-analysis/topo-to-nx.py \
    --input output/20240101/topology.txt

# 2. Find high-degree ASNs (hubs) from the GML
uv run graph-analysis/hubs.py \
    --input output/20240101/topology.gml \
    --min-degree 500 --wide

# 3. Extract the dense core directly from the topology file
uv run graph-analysis/core.py \
    --input output/20240101/topology.txt \
    --min-degree 100

# 4. Convert the core subgraph to GML for further analysis
uv run graph-analysis/topo-to-nx.py \
    --input output/20240101/topology-core.txt
```
