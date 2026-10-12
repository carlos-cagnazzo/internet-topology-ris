# Internet Topology Pipeline

Reconstruct the Internet's AS-level topology from publicly available BGP routing data published by [RIPE NCC's Routing Information Service (RIS)](https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris) and [RouteViews](https://www.routeviews.org/).

The pipeline downloads MRT RIB snapshot files from route collectors, extracts AS paths, and produces a deduplicated edge list where each line is a pair of ASNs observed to be directly connected:

```
00001299 00003356
00001299 00022773
00003356 00015169
```

---

## How It Works

BGP routers exchange reachability information as **AS paths** — ordered sequences of Autonomous System Numbers (ASNs) that a route traverses. The path `1299 3356 15169` means links exist between AS 1299↔3356 and AS 3356↔15169.

RIPE RIS operates a global network of **route collectors** (`rrc00`–`rrc25`), each peering with many BGP routers. Periodically, each collector dumps a full snapshot of its routing table into an MRT-format binary file. This pipeline processes those snapshots to reconstruct the observed AS-level topology.

RouteViews provides additional vantage points across ~40 collectors worldwide, processed identically to RIS data.

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| Python 3.12+ | Runtime | [uv](https://github.com/astral-sh/uv) manages this |
| [`uv`](https://github.com/astral-sh/uv) | Python package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [`just`](https://github.com/casey/just) | Pipeline orchestration | `cargo install just` or system package |
| [`bgpreader`](https://bgpstream.caida.org/) | MRT file parser | Part of BGPStream; install via system package |
| bash 4+ | Required for `collect.sh` | macOS: `brew install bash` |

!!! note "macOS bash"
    macOS ships with bash 3.2. The `collect.sh` fleet script requires bash 4+ for `export -f`.
    Install a newer version with `brew install bash`. This is only needed on the **central machine** that runs `collect`; remote nodes only need ssh and rsync.

---

## Installation

```bash
git clone https://github.com/carlos-cagnazzo/internet-topology-ris
cd internet-topology-ris
uv sync
```

Verify `bgpreader` is available:

```bash
bgpreader --version
```

---

## Pipeline at a Glance

```
get-mrt.py          ──┐
                       ├──▶  extract-paths.py  ──▶  build-topology.py
get-routeviews.py   ──┘
```

1. **Download** — fetch 00:00 UTC RIB snapshots (`.gz` from RIS, `.bz2` from RouteViews)
2. **Extract** — run `bgpreader` on each file, write per-file AS path lists
3. **Build** — read all path files, extract edges, deduplicate, write topology

See [Quick Start](quickstart.md) to run it, or [Pipeline](pipeline/index.md) for a deep dive.
