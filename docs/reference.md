# Reference

---

## RIS Collectors

RIPE RIS operates collectors `rrc00` through `rrc25`. Use `rrc00-rrc25` in `--collectors` to include all of them.

| Collector | Location |
|---|---|
| rrc00 | Amsterdam, NL |
| rrc01 | London, UK |
| rrc03 | Amsterdam, NL |
| rrc04 | Geneva, CH |
| rrc05 | Vienna, AT |
| rrc06 | Otemachi, JP |
| rrc07 | Stockholm, SE |
| rrc10 | Milan, IT |
| rrc11 | New York, US |
| rrc12 | Frankfurt, DE |
| rrc13 | Moscow, RU |
| rrc14 | Palo Alto, US |
| rrc15 | São Paulo, BR |
| rrc16 | Miami, US |
| rrc18 | Barcelona, ES |
| rrc19 | Johannesburg, ZA |
| rrc20 | Zurich, CH |
| rrc21 | Paris, FR |
| rrc22 | Bucharest, RO |
| rrc23 | Singapore, SG |
| rrc24 | Montevideo, UY |
| rrc25 | Amsterdam, NL |

---

## RouteViews Collectors (default set)

The `download-routeviews` recipe uses a working subset of ~40 available collectors. Full index: <https://www.routeviews.org/routeviews/index.php/collectors/>

| Collector ID | Region |
|---|---|
| `route-views.amsix` | Europe (AMS-IX) |
| `namex.fco` | Europe (Rome) |
| `hkix.hkg` | Asia (Hong Kong) |
| `route-views.sg` | Asia (Singapore) |
| `route-views.chicago` | North America |
| `route-views2` | North America |
| `pacwave.lax` | North America |
| `crix.sjo` | North America |
| `ix-br2.gru` | Latin America (São Paulo) |
| `route-views.rio` | Latin America (Rio) |
| `route-views.kixp` | Africa (Nairobi) |
| `route-views.perth` | Oceania |

---

## Output File Formats

### Edge list (`topology.txt`)

One undirected edge per line. Both ASNs are plain integers (or zero-padded to 8 digits with `--justify-output`). The smaller ASN always appears first. Lines are sorted numerically by the first ASN, then the second.

```
6 22773
1299 3356
1299 22773
```

With `--justify-output`:

```
00000006 00022773
00001299 00003356
00001299 00022773
```

### ASN list (`topology-asns.txt`)

One ASN per line, sorted numerically. Zero-padded if `--justify-output` was used.

### Path list (`topology-paths.txt`)

One AS path per line (space-separated ASNs), sorted numerically by leading ASN. Written only when `--paths` is passed to `build-topology.py`.

### Annotated topology (`topology-annotated.txt`)

Six columns per line: `ASN1 ASN2 CC1 RIR1 CC2 RIR2`. Country codes are lowercase ISO 3166-1 alpha-2. RIR names: `arin`, `ripencc`, `apnic`, `lacnic`, `afrinic`. Absent ASNs annotated as `unknown unknown`.

---

## NRO Delegated Stats

Used by `--filter-registered` in `build-topology.py` and by the `geo-filter.py` and `annotate-topology.py` graph analysis tools.

| | URL |
|---|---|
| Latest | `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats` |
| Historical | `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/YYYYMMDD/nro-delegated-stats` |

Relevant statuses: `assigned` (keep), `available` / `reserved` (discard).

---

## bgpreader

`bgpreader` is the system binary used by `extract-paths.py` to parse MRT files. It handles both `.gz` and `.bz2` inputs transparently.

Output is `|`-delimited. Relevant columns (0-indexed):

| Column | Field |
|---|---|
| 1 | Element type (`R` = RIB entry, `B` = block start — skip `B` lines) |
| 9 | Prefix (colon present → IPv6) |
| 11 | AS path |

Only `R` lines are processed. The option to read a single file is `rib-file`:

```bash
bgpreader -d singlefile -o rib-file=<path>
```

---

## CAIDA AS Relationships

CAIDA publishes monthly AS relationship inferences derived from BGP data. The tool `get-caida-peers.py` uses these to extract peer-to-peer (p2p) edges.

| | URL |
|---|---|
| Serial-2 index | `https://publicdata.caida.org/datasets/as-relationships/serial-2/` |
| Serial-1 index | `https://publicdata.caida.org/datasets/as-relationships/serial-1/` |

File format (`|`-delimited, lines starting with `#` are comments):

```
AS1|AS2|rel          # serial-1
AS1|AS2|rel|source   # serial-2
```

Relationship codes: `0` = peer-to-peer, `-1` = provider→customer. Only `rel=0` is extracted.

Downloaded `.bz2` files are cached in `./caida-cache/` (gitignored). Serial-2 is preferred; serial-1 is used as fallback for pre-2012 months.

---

## .gitignore summary

The following are gitignored and must not be committed:

| Path | Reason |
|---|---|
| `mrt/` | Downloaded MRT files (large binary data) |
| `paths/` | Extracted AS path files (large) |
| `output-combined/` | Generated topology and peer output files |
| `caida-cache/` | Cached CAIDA `.bz2` downloads |
| `topology*.txt` | Any topology edge list at repo root |
| `nro-delegated-stats*` | Cached NRO stats |
| `fleet.csv` | Deployment-specific; copy from `fleet.csv.example` |
| `fetch/` | Rsync staging from `fetch-results.sh` |
