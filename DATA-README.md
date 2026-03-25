# Internet AS-Level Topology Data

This archive contains a snapshot of the Internet's Autonomous System (AS) level topology reconstructed from BGP routing data collected on **{date}** by [RIPE NCC's Routing Information Service (RIS)](https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris) and [RouteViews](https://www.routeviews.org/).

## What this data represents

BGP routers exchange reachability information as **AS paths** — sequences of Autonomous System Numbers (ASNs) that a route traverses. The path `1299 3356 15169` implies a peering link between AS 1299 and AS 3356, and between AS 3356 and AS 15169. This data aggregates millions of such paths observed across all available route collectors to produce a deduplicated map of observed AS-level interconnections.

Only ASNs formally assigned by one of the five Regional Internet Registries (RIRs), as recorded in the NRO delegated extended statistics for the snapshot date, are included.

## File format

Edge list files contain one link per line, two space-separated zero-padded ASNs:

```
00001299 00003356
00001299 00022773
00003356 00015169
```

ASN list files contain one ASN per line. Path files contain one AS path per line, space-separated, preserving BGP directionality.

## Output files

| File | Description |
|---|---|
| `topology-{date}.txt` | Deduplicated undirected edge list, all address families combined |
| `topology-{date}-asns.txt` | All unique ASNs present in the combined topology |
| `topology-{date}-paths.txt` | All unique AS paths observed, sorted numerically |
| `topology-{date}-dropped-asns.txt` | ASNs excluded because they are not formally assigned |
| `topology-{date}-v4.txt` | Edge list — IPv4 prefixes only |
| `topology-{date}-v4-asns.txt` | Unique ASNs — IPv4 topology |
| `topology-{date}-v4-paths.txt` | Unique AS paths — IPv4 |
| `topology-{date}-v4-dropped-asns.txt` | Dropped ASNs — IPv4 |
| `topology-{date}-v6.txt` | Edge list — IPv6 prefixes only |
| `topology-{date}-v6-asns.txt` | Unique ASNs — IPv6 topology |
| `topology-{date}-v6-paths.txt` | Unique AS paths — IPv6 |
| `topology-{date}-v6-dropped-asns.txt` | Dropped ASNs — IPv6 |

## Data sources

- **RIPE RIS** collectors `rrc00`–`rrc25`, 00:00 UTC RIB snapshots
- **RouteViews** collectors `route-views.amsix` (AMS-IX) and `ix-br2.gru` (São Paulo)
