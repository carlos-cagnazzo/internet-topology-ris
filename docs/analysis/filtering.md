# Filtering & Core Tools

---

## topology-core.py

Filters a topology edge list to edges where **both** endpoints have degree ≥ `--min-degree`. Produces a valid topology file in the same two-column format.

Useful before visualisation (large topologies are slow in Gephi) or before analysis steps you want to run only on well-connected ASNs.

```
uv run graph-analysis/topology-core.py --input <file> --min-degree <N> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Topology edge list (`.txt` or `.txt.gz`) |
| `--output` | input stem + `-core.txt` | Output filtered edge list |
| `--min-degree` | required | Minimum degree (both endpoints must qualify) |
| `--wide` | off | Add `DEG1 DEG2` columns to the output |
| `--justify-output` | off | Zero-pad ASNs to 8 digits |

Degree is computed from the input file directly — no GML conversion required.

### Examples

```bash
# Keep only edges where both ASNs have degree ≥ 10
uv run graph-analysis/topology-core.py \
  --input output/20260101/topology-20260101.txt \
  --min-degree 10

# Same, but annotate with degrees and zero-pad
uv run graph-analysis/topology-core.py \
  --input output/20260101/topology-20260101.txt \
  --output output/20260101/topology-core10.txt \
  --min-degree 10 --wide --justify-output
```

---

## geo-filter.py

Filters a topology to edges where **both** ASNs are assigned to one of the given ISO 3166-1 alpha-2 country codes, according to the NRO delegated stats. ASNs absent from the NRO file are excluded.

Always produces two output files:

- `{output}.txt` — filtered edge list
- `{output}.gml` — filtered graph with a `country` node attribute

```
uv run graph-analysis/geo-filter.py --input <file> --countries <cc,...> [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Topology edge list (`.txt`/`.txt.gz`) or `.gml` |
| `--countries` | required | Comma-separated ISO 3166-1 alpha-2 country codes (lowercase) |
| `--output` | input stem + `-geo` | Base output path (no extension — both `.txt` and `.gml` written) |
| `--date` | latest | NRO stats snapshot date `YYYYMMDD` for reproducible filtering |
| `--justify-output` | off | Zero-pad ASNs to 8 digits |

NRO stats are fetched and cached next to the input file.

### Examples

```bash
# Latin American topology
uv run graph-analysis/geo-filter.py \
  --input output/20260101/topology-20260101.txt \
  --countries ar,br,cl,co,mx,pe,uy,ve \
  --output output/20260101/latam \
  --date 20260101

# Single country
uv run graph-analysis/geo-filter.py \
  --input output/20260101/topology-20260101.txt \
  --countries br \
  --output output/20260101/brazil
```
