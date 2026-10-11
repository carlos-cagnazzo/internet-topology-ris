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

## Output

Output goes to `./output-combined/YYYYMM/caida-peers-YYYYMM.txt` by default. Format matches the BGP topology edge list: one undirected edge per line, smaller ASN first, sorted numerically.

```
00000001 00005467
00000001 00008641
00001299 00003356
```

Plain integers (no zero-padding) with `--no-justify-output`:

```
1 5467
1 8641
1299 3356
```

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
