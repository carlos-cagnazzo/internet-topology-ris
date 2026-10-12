# Analysis Tools

The `analysis/` directory contains tools for analysing and transforming topology files. All run via `./run.sh <tool>` from the repo root (or directly as `uv run analysis/<tool>`).

---

## Tools at a glance

| Tool | Input | Output | Purpose |
|---|---|---|---|
| [`topology-to-gml.py`](conversion.md#topology-to-gmlpy) | `.txt` edge list | `.gml` | Convert to GML for Gephi/yEd |
| [`gml-to-topology.py`](conversion.md#gml-to-topologypy) | `.gml` | `.txt` edge list | Convert GML back to edge list |
| [`topology-core.py`](filtering.md#topology-corepy) | `.txt` edge list | `.txt` edge list | Filter to high-degree nodes |
| [`geo-filter.py`](filtering.md#geo-filterpy) | `.txt` or `.gml` | `.txt` + `.gml` | Filter to one or more countries |
| [`hubs.py`](analysis.md#hubspy) | `.txt` or `.gml` | `.txt` hub list | List high-degree ASNs |
| [`annotate-topology.py`](analysis.md#annotate-topologypy) | `.txt` edge list | `.txt` with CC+RIR | Add country/RIR columns |
| [`asn-presence.py`](analysis.md#asn-presencepy) | `*-asns-YYYYMMDD.txt` files | matrix `.txt` | Day-by-day ASN presence matrix |
| [`topology-ops.py`](analysis.md#topology-opspy) | two or more `.txt` files | `.txt` edge list | Set operations (union / difference) |
| [`lookup-as.py`](analysis.md#lookup-aspy) | ASN(s) | table / TSV | Look up ASN holder info via RIPEstat |
| [`path-transit-freq.py`](analysis.md#path-transit-freqpy) | path `.txt[.gz]` file | freq `.txt` | Count transit AS frequency |

---

## Common patterns

### Reduce before visualising

Large topologies (200k+ edges) are slow to render in Gephi. Filter to a core first:

```bash
# Keep only nodes with degree ≥ 10
./run.sh topology-core.py \
  --input output-combined/20260101/topology-20260101.txt \
  --output output-combined/20260101/topology-core10.txt \
  --min-degree 10

# Convert core to GML with enriched labels
./run.sh topology-to-gml.py \
  --input output-combined/20260101/topology-core10.txt \
  --enrich --min-degree 10
```

### Regional analysis

```bash
# Latin America topology
./run.sh geo-filter.py \
  --input output-combined/20260101/topology-20260101.txt \
  --countries ar,br,cl,co,mx,pe,uy,ve \
  --output output-combined/20260101/latam

# Annotate with country/RIR for further analysis
./run.sh annotate-topology.py \
  --input output-combined/20260101/topology-20260101.txt \
  --date 20260101
```

### Track ASN stability over time

```bash
# Build topologies for several dates, then build the presence matrix
./run.sh asn-presence.py \
  --input "output-combined/*/topology-*-asns.txt" \
  --output output-combined/asn-presence.txt
```
