# graph-analysis

Graph analysis tools for AS-level Internet topology files. All tools are run via `uv run` from the repository root and share the root `pyproject.toml`.

Input topology files use the two-column `ASN1 ASN2` format produced by `build-topology.py`, with `ASN1 < ASN2` (numerically). Plain and gzip-compressed files are accepted transparently.

---

## Tools

### `topo-to-nx.py` — Topology to GML

Imports a topology edge list into an undirected [NetworkX](https://networkx.org/) graph and writes it as a GML file for use with Gephi, yEd, Cytoscape, or other graph tools.

Zero-padded ASNs are normalised to plain integers. Each node carries an `asn` (integer) and a `label` (plain ASN string) attribute. Edges carry no attributes.

```
uv run graph-analysis/topo-to-nx.py --input <topology.txt> [--output <out.gml>]
```

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | Topology edge list (`.txt` or `.txt.gz`) |
| `--output` / `-o` | input stem + `.gml` | GML output path |

**Example:**

```bash
uv run graph-analysis/topo-to-nx.py \
    --input output/20240101/topology.txt \
    --output output/20240101/topology.gml
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
