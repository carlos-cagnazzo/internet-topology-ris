# Glossary

Terms used in this project, grouped by domain. Use this as a shared vocabulary when discussing bugs, features, or analysis results.

---

## BGP and Routing

**BGP (Border Gateway Protocol)**
The inter-domain routing protocol of the Internet. BGP routers exchange reachability information for IP prefixes. All topology data in this project comes from BGP.

**AS (Autonomous System)**
An independently administered network or group of networks with a common routing policy, identified by an ASN. The basic unit of Internet routing and the node type in our topology graphs.

**ASN (Autonomous System Number)**
The numeric identifier for an AS (e.g. `15169` for Google). ASNs are 32-bit integers. In our files, ASNs appear as plain integers or zero-padded 8-digit strings (see *justified format*).

**AS path**
The ordered sequence of ASNs a BGP route traverses from origin to destination, as seen by a BGP speaker. Example: `1299 3356 15169` means there is a link between AS 1299 and AS 3356, and between AS 3356 and AS 15169. AS paths are directional (BGP semantics), but edges derived from them are undirected.

**Prefix**
An IP network block (e.g. `192.0.2.0/24` for IPv4, `2001:db8::/32` for IPv6). Each BGP route announces reachability for one prefix via an AS path. We use the prefix field only to detect address family (IPv4 vs. IPv6).

**Prepending**
A BGP traffic engineering technique where an AS repeats its own ASN multiple times in the AS path (e.g. `64500 64500 64500 64501`) to make a path appear longer and less preferred. We collapse consecutive duplicates before extracting edges: `A A B C` → `A B C`.

**AS set**
A notation in AS paths (`{64500,64501}`) indicating that multiple ASes were involved at that point due to route aggregation. We truncate the path at an AS set and keep only edges before it.

**Announcement / Advertisement**
A BGP message that a router sends to its peers to declare reachability for a prefix via an AS path.

**Withdrawal**
A BGP message that a router sends to retract a previously announced prefix. We ignore withdrawals — only announcements are processed.

**Peering (BGP peering)**
A BGP session between two routers. Route collectors peer with many BGP speakers to receive their full routing tables.

**Transit**
A commercial relationship where one AS (the transit provider) carries traffic on behalf of another AS (the customer), offering reachability to the full Internet in exchange for payment. Transit providers typically appear as high-degree nodes in topology.

---

## Data Sources

**RIPE RIS (Routing Information Service)**
RIPE NCC's global network of route collectors (`rrc00`–`rrc25`), each peering with dozens of BGP routers worldwide. Our primary data source. Operated by RIPE NCC. Data: `https://data.ris.ripe.net/`

**RouteViews**
An alternative route collector project operated by the University of Oregon. We also download RouteViews RIB snapshots and merge them with RIS data. Collectors used: `route-views.amsix`, `ix-br2.gru`, `route-views2`, `route-views.sg`.

**Route collector / collector**
A passive BGP router that peers with many networks and records their routing table. Does not inject its own routes. Referred to as `rrc00`, `rrc01`, etc. for RIS collectors.

**RIB (Routing Information Base)**
The routing table held by a BGP router or route collector at a point in time. Contains one entry per reachable prefix, including the best-path AS path to reach it.

**bview (RIB dump / RIB snapshot)**
A binary MRT-format file containing a full dump of a route collector's RIB at a specific time. RIPE RIS dumps are taken at 00:00 UTC daily. These are the primary input files to the pipeline. The bgpreader option to read them is `rib-file=<path>`.

**Update file**
A binary MRT-format file recording incremental BGP announcements and withdrawals over a time window (typically 5 minutes for RIS). Used by `download-ris-day.py`. The bgpreader option is `upd-file=<path>`.

**MRT (Multi-Threaded Routing Toolkit) format**
The binary file format used to store BGP data (both RIB dumps and update files). Both `.gz` (RIPE RIS) and `.bz2` (RouteViews) compressed MRT files are supported.

**bgpreader**
The command-line tool (part of the BGPStream project) that we use to parse MRT files into pipe-delimited text. It handles `.gz` and `.bz2` decompression transparently. Column 11 (0-indexed) is the AS path; column 9 is the prefix; field[1] == `R` for RIB entries, `A` for announcements.

---

## NRO and Registry

**NRO (Number Resource Organization)**
The coordinating body for the five Regional Internet Registries (RIRs). Publishes the *NRO delegated extended stats* file, which is the authoritative source for ASN-to-country and ASN-to-RIR assignments.

**NRO delegated stats**
A `|`-delimited flat file published by the NRO listing all allocated and assigned Internet number resources (ASNs, IPv4, IPv6) per RIR. We use it to map ASNs to country codes and RIRs.
- Latest: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats`
- Historical: `https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{YYYYMMDD}/nro-delegated-stats`
- Only records with `status=assigned` are used; `available` and `reserved` are discarded.
- Cached next to the input file; re-downloaded if older than 24 hours (latest) or permanently (historical).

**RIR (Regional Internet Registry)**
One of five organizations responsible for allocating Internet number resources in their region. Names as used in NRO stats (and in our output):

| Name in our files | Full name | Region |
|---|---|---|
| `arin` | American Registry for Internet Numbers | North America |
| `ripencc` | RIPE Network Coordination Centre | Europe, Middle East, Central Asia |
| `apnic` | Asia-Pacific Network Information Centre | Asia-Pacific |
| `lacnic` | Latin America and Caribbean Network Information Centre | Latin America & Caribbean |
| `afrinic` | African Network Information Centre | Africa |

**Assigned ASN**
An ASN with `status=assigned` in the NRO stats — formally delegated to an organization. Our `--filter-registered` flag drops paths containing any non-assigned ASN.

**Private / reserved ASN**
ASNs not in the NRO stats, or with status `available` or `reserved`. Examples: 64512–65534 (old 16-bit private range), 4200000000–4294967294 (32-bit private range). Annotated as `unknown` in `annotate-topology.py`.

**Country code (cc)**
ISO 3166-1 alpha-2 two-letter code (e.g. `uy`, `br`, `us`). Always lowercase in our output. Comes from the NRO stats `country` field.

**Holder name**
The organization name registered as the holder of an ASN, as returned by the RIPEstat `as-overview` API endpoint. Used as node labels in enriched GML files.

---

## Pipeline and Files

**Topology file / edge list**
The canonical output format of this project and the primary input to all graph-analysis tools. A plain-text file where each line represents one undirected AS-level link observed in the BGP data.

Format rules:
- **Two space-separated columns per line:** `ASN1 ASN2`
- **`ASN1 < ASN2` numerically** — the smaller ASN always comes first. This is enforced at write time so each undirected edge has exactly one canonical representation and the file is free of duplicates. Comparison is always numeric, never lexicographic (`"9" > "22773"` as strings but `9 < 22773` as integers — we always use integer comparison).
- **Sorted numerically by ASN1** (then by ASN2 within the same ASN1).
- **Deduplicated** — each edge appears at most once, regardless of how many collectors or paths it was observed in.
- **`#` lines are comments** and are skipped by all tools. Blank lines are also skipped.
- **Extension is always `.txt`**, even when the file is gzip-compressed. Compression is detected by magic bytes (`\x1f\x8b`), not by the extension. All tools handle both plain and compressed files transparently.

Example (plain integers):
```
174 1916
174 3356
1299 3356
1299 15169
3356 15169
```

Example with `--justify-output` (zero-padded to 8 digits — same data, same rules):
```
00000174 00001916
00000174 00003356
00001299 00003356
00001299 00015169
00003356 00015169
```

The justified variant is the same format — just with fixed-width ASN fields. All tools that read topology files handle both variants transparently by parsing columns as integers before comparing.

**Path file**
A plain-text file (gzip-compressed, detected by magic bytes) with one AS path per line as extracted from MRT files. Input to `build-topology.py`. Three variants per input MRT: combined (`.gz.txt`), IPv4-only (`.gz.v4.txt`), IPv6-only (`.gz.v6.txt`).

**Annotated topology**
A topology file with four additional columns per edge: `cc1 rir1 cc2 rir2`. Produced by `annotate-topology.py`. Example line: `6057 3359 uy lacnic us arin`.

**GML file**
A topology represented as a NetworkX GML graph file, suitable for import into Gephi, yEd, or Cytoscape. Nodes carry `asn` (integer) and `label` (string) attributes; enriched nodes have their AS holder name as label.

**Sidecar file**
A file written alongside an input file with a related name (e.g. `topology-asns.txt` next to `topology.txt`, or `nro-delegated-stats` next to an annotated topology). Not a separate concept in the tools — just a naming convention.

**topcache**
A per-input-file pickle cache written by `build-topology.py` (as `<name>.topcache`), recording the edges, ASNs, dropped ASNs, and raw path count. Invalidated if the input file or NRO stats file changes. Speeds up repeated runs.

**Justified format / zero-padded ASNs**
ASNs written as 8-digit zero-padded strings (e.g. `00006057` instead of `6057`). Enabled by `--justify-output`. Useful for lexicographic sorting tools that do not understand numeric ordering.

---

## Graph Concepts

**Degree**
The number of direct neighbours of a node (AS) in the topology graph — i.e. the count of distinct ASes it is directly connected to.

**Hub**
An AS with a very high degree. In Internet topology, hubs are typically transit providers, large IXPs, or major content networks (Tier-1 and Tier-2 operators). Extracted by `hubs.py`.

**Core subgraph / dense core**
The induced subgraph containing only edges where *both* endpoints have degree ≥ a threshold. Computed by `topology-core.py`. Removes stub networks and exposes the high-connectivity backbone.

**Stub AS**
An AS with low degree (often 1 or 2) — typically an end-user network or small ISP with a single upstream provider.

**Enrichment**
The process of replacing ASN labels with AS holder names from RIPEstat in a GML file. Done by `topology-to-gml.py --enrich`. Only applied to nodes above a degree threshold to avoid fetching thousands of names for stubs.

**Geo-filtering**
Filtering the topology to retain only edges where *both* endpoints are assigned to one or more specified countries (per NRO stats). Done by `geo-filter.py`.

**Address family (AF)**
IPv4 or IPv6. Detected from the prefix field in bgpreader output (presence of `:` → IPv6). We build separate topology files per address family and a combined file.

---

## Tools Quick Reference

| Script | What it does |
|---|---|
| `get-mrt.py` | Download RIPE RIS bview files |
| `get-routeviews.py` | Download RouteViews bview files |
| `download-ris-day.py` | Download RIS bview + all updates for a date, extract paths in one shot |
| `extract-paths.py` | Extract AS paths from MRT files via bgpreader |
| `build-topology.py` | Build edge list + ASN list + paths list from path files |
| `topology-ops.py` | Set operations (union, difference) on topology files |
| `lookup-as.py` | Query RIPEstat for ASN holder name, prefix count, last-seen |
| `graph-analysis/topology-to-gml.py` | Convert topology edge list to GML graph |
| `graph-analysis/gml-to-topology.py` | Convert GML back to topology edge list |
| `graph-analysis/topology-core.py` | Extract degree-filtered core subgraph as topology file |
| `graph-analysis/hubs.py` | List ASNs with degree ≥ threshold |
| `graph-analysis/geo-filter.py` | Filter topology to edges within specified countries |
| `graph-analysis/annotate-topology.py` | Enrich each edge with country and RIR columns |

---

## Conventions

**`ASN1 < ASN2`**
Edges are always stored with the numerically smaller ASN first. Ensures each undirected edge appears exactly once and sorting is consistent. Comparison is always numeric — not lexicographic (string `"22773" < "6"` but integer `22773 > 6`).

**Collector spec / range notation**
The format accepted by `--collectors`: individual names (`rrc00`), comma-separated lists (`rrc00,rrc04`), inclusive ranges (`rrc00-rrc10`), or mixed (`rrc00-rrc05,rrc11`).

**`--date YYYYMMDD`**
When passed to pipeline tools, selects the historical NRO stats snapshot for that date instead of the latest. Historical files are permanently cached (they never change). Recommended when annotating or filtering a topology built from a specific date's data, for reproducibility.

**`--justify-output`**
Zero-pads all ASNs to 8 digits. Present on all tools that write topology files. Has no effect on terminal output or filtering logic.

**`--wide`**
On `hubs.py` and `topology-core.py`: adds degree column(s) to the output and sorts by degree descending (hubs) or preserves numeric sort (core).

**`--filter-registered`**
On `build-topology.py`: excludes any AS path containing an ASN not formally `assigned` per NRO stats. Dropped ASNs are written to `topology-dropped-asns.txt`.
