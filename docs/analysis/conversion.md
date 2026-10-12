# Conversion Tools

Tools for converting between topology edge list format and GML.

---

## topology-to-gml.py

Converts a topology edge list (`.txt`) to a [GML](https://en.wikipedia.org/wiki/Graph_Modelling_Language) file for import into Gephi, yEd, Cytoscape, or any graph tool that reads GML.

```
./run.sh topology-to-gml.py --input <file> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Topology edge list (`.txt` or `.txt.gz`) |
| `--output` | input with `.gml` extension | Output GML file |
| `--min-degree` | `3` | Filter: only include edges where both endpoints have degree ≥ N |
| `--enrich` | off | Fetch AS holder names from RIPEstat and use as node labels |
| `--enrich-min-degree` | `3` | Only enrich nodes with degree ≥ N (cheaper than enriching all nodes) |

When `--enrich` is active, holder names are fetched from the RIPEstat API and cached at `~/.cache/internet-topology-ris/as-names.json` with a 60-day TTL. Nodes below `--enrich-min-degree` keep their ASN as label.

To produce a **filtered edge list** (`.txt`) rather than a GML, use `topology-core.py` instead.

### Examples

```bash
# Basic conversion, no filtering
./run.sh topology-to-gml.py \
  --input output-combined/20260101/topology-20260101.txt

# Filter to core (degree ≥ 5) + enrich labels for well-connected nodes
./run.sh topology-to-gml.py \
  --input output-combined/20260101/topology-20260101.txt \
  --output output-combined/20260101/topology-core5.gml \
  --min-degree 5 \
  --enrich --enrich-min-degree 20
```

---

## gml-to-topology.py

Inverse of `topology-to-gml.py`. Reads a GML file and writes a two-column topology edge list. Useful for round-tripping through Gephi (e.g. after manual layout or community detection).

```
./run.sh gml-to-topology.py --input <file> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | GML file |
| `--output` | input with `.txt` extension | Output edge list |
| `--min-degree` | *(none)* | Optional: filter to edges where both endpoints have degree ≥ N |
| `--justify-output` | off | Zero-pad ASNs to 8 digits |

ASNs are always read from the node `asn` attribute (safe for enriched GML files that carry string labels).

### Examples

```bash
# Round-trip: convert back from Gephi export
./run.sh gml-to-topology.py \
  --input output-combined/20260101/topology-gephi.gml \
  --output output-combined/20260101/topology-gephi.txt

# With degree filter
./run.sh gml-to-topology.py \
  --input output-combined/20260101/topology.gml \
  --min-degree 10 \
  --justify-output
```
