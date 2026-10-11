# CAIDA AS Relationships

`get-caida-peers.py` downloads the [CAIDA AS Relationships dataset](https://publicdata.caida.org/datasets/as-relationships/) for a given month and extracts all peer-to-peer edges (relationship code `0`). The result is a deduplicated, sorted two-column edge list in the same format as the BGP-derived topology.

```
uv run get-caida-peers.py --date YYYYMM [OPTIONS]
```

---

## Flags

| Flag | Default | Description |
|---|---|---|
| `--date` | required | Year-month to fetch, `YYYYMM` format |
| `--output` | `./output-combined/YYYYMM/caida-peers-YYYYMM.txt` | Output file path |
| `--justify-output` / `--no-justify-output` | on | Zero-pad ASNs to 8 digits |
| `--cache-dir` | `./caida-cache` | Where to store downloaded `.bz2` files |

---

## Datasets

CAIDA publishes two dataset series, both available at no cost:

| Series | Coverage | File pattern |
|---|---|---|
| **serial-2** | ~2012 – present | `YYYYMMDD.as-rel2.txt.bz2` |
| **serial-1** | ~1998 – 2013 | `YYYYMMDD.as-rel.txt.bz2` |

The tool **prefers serial-2**. If no serial-2 file exists for the requested month (pre-2012 data), it falls back to serial-1. File names within a month are not predictable (not always the 1st of the month), so the tool fetches the directory index to discover the correct filename.

---

## Relationship codes

| Code | Meaning | Included? |
|---|---|---|
| `0` | Peer-to-peer | ✓ |
| `-1` | Provider → customer | ✗ |

Only `rel=0` edges are written to output. Provider-customer relationships are discarded.

---

## Caching

Downloaded `.bz2` files are cached permanently in `--cache-dir` (default `./caida-cache/`, gitignored). CAIDA files are immutable once published — a cached file is always reused without re-downloading.

---

## Output files

Two files are always written to the same directory:

| File | Contents |
|---|---|
| `caida-peers-YYYYMM.txt` | Peer-to-peer edge list (rel=0) |
| `caida-tier1-YYYYMM.txt` | Potential Tier 1 ASNs — one ASN per line |

### Peer edge list

One undirected edge per line, smaller ASN first, sorted numerically:

```
00000001 00005467
00000001 00008641
00001299 00003356
```

### Potential Tier 1 list

ASNs that provide transit to others (appear as provider in a rel=-1 relationship) but never buy transit themselves (never appear as customer). These are **provider-free transit networks** — the operational definition of Tier 1.

```
00000174
00000701
00001299
00003356
```

The list typically contains ~100–200 ASNs: the ~20 globally recognised Tier 1 networks plus regional/national networks that are provider-free in their own market. Networks that are widely considered Tier 1 but appear as a customer in at least one CAIDA-inferred relationship (e.g. Hurricane Electric, AS6939) will be absent.

Plain integers (no zero-padding) with `--no-justify-output`.

---

## Justfile

```bash
# Fetch peer relationships for a month
just date=202401 caida-peers

# Without zero-padding
just date=202401 no_justify=1 caida-peers
```

---

## Examples

```bash
# January 2024 — uses serial-2
uv run get-caida-peers.py --date 202401

# January 2005 — falls back to serial-1
uv run get-caida-peers.py --date 200501

# Override output path, no zero-padding
uv run get-caida-peers.py \
  --date 202401 \
  --output ./my-peers-202401.txt \
  --no-justify-output
```
