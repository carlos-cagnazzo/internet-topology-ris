# Quick Start

## Single machine, one date

The simplest way to run the full pipeline — downloads from all RIS collectors plus the default RouteViews subset, extracts paths, and builds combined + IPv4 + IPv6 topologies.

```bash
just date=20260101 collectors=rrc00-rrc25 pipeline
```

!!! warning "Variable order"
    `just` requires variable assignments **before** the recipe name:
    `just date=20260101 pipeline` ✓  
    `just pipeline date=20260101` ✗

Output lands in `./output-combined/20260101/`:

```
output-combined/20260101/
  topology-20260101.txt        # all-AF edge list
  topology-20260101-asns.txt   # unique ASN list
  topology-20260101-v4.txt     # IPv4 edge list
  topology-20260101-v4-asns.txt
  topology-20260101-v6.txt     # IPv6 edge list
  topology-20260101-v6-asns.txt
```

Each edge list line is a pair of zero-padded ASNs, sorted numerically within the pair and across all lines:

```
00000006 00022773
00001299 00003356
00001299 00022773
```

---

## Step by step

Run steps individually when you need to reprocess or debug:

```bash
# 1. Download RIS snapshots
just date=20260101 collectors=rrc00-rrc25 download

# 2. Download RouteViews snapshots
just date=20260101 download-routeviews

# 3. Extract AS paths from all downloaded files
just date=20260101 process

# 4. Build topology (combined + v4 + v6)
just date=20260101 topology
```

Or build only one address family:

```bash
just date=20260101 topology-v4
```

---

## Three dates, multiple collectors

```bash
for d in 20260101 20260201 20260301; do
  just date=$d collectors=rrc00-rrc25 pipeline
done
```

---

## What's next

- [Pipeline in depth](pipeline/index.md) — all flags, output file details, NRO filtering
- [Fleet Workflow](fleet.md) — distribute processing across multiple machines
- [Analysis Tools](analysis/index.md) — filter, convert, annotate, and analyze topologies
