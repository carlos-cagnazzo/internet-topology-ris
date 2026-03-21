# Changelog

All notable changes to this project are documented here, in reverse chronological order. Each entry references the commit it corresponds to.

---

## [pending] — New tool: topology-ops.py

Adds `topology-ops.py` for set operations on topology edge list files. Supports `--op add` (union) and `--op sub` (difference). Edges are compared numerically after stripping leading zeros, so plain and zero-padded inputs are handled transparently. Output format follows the same `--justify-output` convention as the rest of the pipeline.

---

## [9dc69e4] — New tool: topology-to-gml.py

Converts a topology edge list to GML format for import into Gephi, yEd, Cytoscape, etc. With `--enrich`, nodes above a configurable degree threshold (`--min-degree`, default 3) are labeled with their AS holder name from RIPEstat. Holder names are cached locally for 60 days (`~/.cache/internet-topology-ris/as-names.json`) to avoid redundant API calls across runs. networkx is used for graph construction and GML serialization.

---

## [6ded21d] — Scope output directory by date

Topology output files are now written to `./output/<date>/` instead of `./output/`, consistent with the MRT and paths directories. Each pipeline run is now fully isolated across all three directory trees.

---

## [f4c94e5] — Date-scoped subdirectories for MRT and path files

The justfile now routes each run into date-stamped subdirectories (`./mrt/<date>/`, `./paths/<date>/`) so that files from different dates never interfere with each other. All three pipeline steps (`download`, `process`, `topology-*`) use `{{ date }}` to scope their input and output directories. README and CLAUDE.md updated accordingly.

---

## [84eb077] — README: remove Scale Reference section

Removed the Scale Reference section from the README as it was not useful.

---

## [2d781b5] — Document lookup-as.py

Updated README with a dedicated Helper Tools section covering all flags, input modes, and practical usage examples. Updated CLAUDE.md with API endpoint reference and concurrency model notes.

## [3c6709d] — lookup-as.py: progress bar and stdin support

Batch lookups now show a live progress bar that advances as each ASN completes (driven by an asyncio queue). Added stdin as an input source: pipe ASNs implicitly or pass `--file -` explicitly.

## [c559143] — New tool: lookup-as.py

Added `lookup-as.py`, a helper for debugging the topology. Queries the RIPEstat Data API to retrieve AS holder name, announced prefix count, and last-seen timestamp for one or more ASNs. Supports single lookup (`--asn`), batch from file (`--file`), and optional TSV output (`--output`). Batch requests run concurrently via asyncio + httpx.

## [2747764] — IPv4/IPv6 address family separation

`process-mrt.py` now produces three output files per MRT input: combined (`.gz.txt`), IPv4-only (`.gz.v4.txt`), and IPv6-only (`.gz.v6.txt`). Address family is detected from the BGP prefix field. The justfile gains `topology-v4` and `topology-v6` recipes alongside the existing combined `topology`. Fixed a latent bug where the combined topology glob (`*.txt`) would have matched the new AF sidecar files — tightened to `*.gz.txt`.

## [9781373] — Collector range notation; fix failed transfer counting

`get-mrt.py` now accepts range notation for `--collectors` (e.g. `rrc00-rrc25`), expanding to individual collector IDs. Fixed two bugs: failed HTTP transfers were not counted in the run summary, and the error message repeated the URL causing line wrapping.

## [141a8dd] — Replace subprocess sort with pure-Python heapq merge

Replaced the external `sort` call (which only sorted numerically on the first field) with a pure-Python chunked sort + `heapq.merge` k-way merge. Sorting is now fully numeric across all ASN fields in a path. Eliminates the OOM crash that occurred when processing all collectors simultaneously.

## [f9bde75] — Unique paths output product

`build-topology.py` now always writes a `{stem}-paths.txt` file containing the deduplicated list of all unique AS paths seen across input files, sorted fully numerically by leading ASN. Paths are directional (BGP semantics). Initial implementation used an in-memory set (later replaced by disk-based sort, see above).

## [e182e76] — ASN list output and --justify-output flag

`build-topology.py` now always writes a `{stem}-asns.txt` file listing every unique ASN present in the final topology. Added `--justify-output` to zero-pad all ASNs to 8 digits in every output file, making them suitable for lexicographic sorting tools. Added `--filter-registered` to exclude paths containing ASNs not formally assigned per the NRO delegated extended stats (cached locally, refreshed every 24 hours); dropped ASNs are written to `{stem}-dropped-asns.txt`.

## [b986e27] — Initial build-topology.py and justfile; fix edge ordering bug

Added `build-topology.py` (step 3 of the pipeline) and the `justfile` orchestrating all three steps. Fixed a critical edge ordering bug: `min()`/`max()` on ASN strings gives lexicographic order, causing e.g. AS6 to sort after AS22773. Fixed by using integer comparison: `(a, b) if int(a) < int(b) else (b, a)`.

## [fab9940] — Initial pipeline: get-mrt.py and process-mrt.py

Implemented steps 1 and 2 of the pipeline. `get-mrt.py` downloads 00:00 UTC RIB snapshots (`bview` files) from RIPE RIS collectors, with streaming downloads, skip-if-exists logic, and per-collector error handling. `process-mrt.py` invokes `bgpreader` on each file to extract AS paths, collapsing prepended ASNs and truncating at AS sets.
