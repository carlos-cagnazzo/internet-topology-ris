"""
topo-to-nx.py — Convert an AS-level topology edge list to a NetworkX graph or filtered topology.

This tool reads a two-column topology file (ASN1 ASN2 per line) as produced by
build-topology.py and builds an undirected NetworkX graph from it. The output
format is controlled by the extension of --output: a .gml extension (the
default) writes a NetworkX GML file suitable for import into Gephi, yEd,
Cytoscape, or any other graph tool; a .txt extension writes a two-column
topology edge list in the same format as the input (ASN1 < ASN2, sorted
numerically by ASN1). Both plain and gzip-compressed inputs are accepted.

Zero-padded ASNs are normalised to plain integers. In GML output, each node
carries an 'asn' (int) and a 'label' (plain ASN string) attribute; edges carry
no attributes. Use --min-degree to restrict the output to edges where both
endpoints have degree >= N in the full graph — useful for extracting the dense
core or tier-1/tier-2 subgraphs. Use --justify-output to zero-pad ASNs to 8
digits in .txt output, which enables correct lexicographic sorting with standard
Unix tools (sort, awk, grep).

With --enrich (GML output only), nodes with degree >= --enrich-min-degree have
their label replaced with the AS holder name fetched from the RIPEstat API.
Names are cached locally for 60 days to avoid redundant API calls.
"""

import asyncio
import gzip
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import networkx as nx
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer()
console = Console()

RIPESTAT_BASE = "https://stat.ripe.net/data"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "internet-topology-ris" / "as-names.json"
CACHE_TTL_DAYS = 60
DEFAULT_CONCURRENCY = 10
DEFAULT_ENRICH_MIN_DEGREE = 3


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def load_cache(cache_path: Path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict[str, dict], cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))


def cache_is_fresh(entry: dict) -> bool:
    try:
        cached_at = datetime.fromisoformat(entry["cached_at"])
        return datetime.now(timezone.utc) - cached_at < timedelta(days=CACHE_TTL_DAYS)
    except (KeyError, ValueError):
        return False


# ---------------------------------------------------------------------------
# RIPEstat fetch
# ---------------------------------------------------------------------------

async def fetch_as_name(asn: str, client: httpx.AsyncClient) -> str | None:
    url = f"{RIPESTAT_BASE}/as-overview/data.json?resource=AS{asn}"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "ok":
            return None
        return body.get("data", {}).get("holder") or None
    except Exception:
        return None


async def fetch_names_batch(
    asns: list[str],
    concurrency: int,
    cache: dict[str, dict],
) -> None:
    if not asns:
        return

    sem = asyncio.Semaphore(concurrency)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    async def fetch_one(asn: str, client: httpx.AsyncClient) -> None:
        async with sem:
            name = await fetch_as_name(asn, client)
        cache[asn] = {
            "name": name,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        progress.advance(task)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        with progress:
            task = progress.add_task("  Fetching AS names", total=len(asns))
            await asyncio.gather(*(fetch_one(asn, client) for asn in asns))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@app.command(help=__doc__)
def main(
    input: Path = typer.Option(..., "--input", "-i", help="Topology edge list file (.txt or .txt.gz)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path; .gml writes GML, .txt writes topology edge list (default: input stem + .gml)"),
    min_degree: int = typer.Option(None, "--min-degree", "-d", help="Only write edges where both endpoints have degree >= N"),
    justify_output: bool = typer.Option(False, "--justify-output", help="Zero-pad ASNs to 8 digits (only applies to .txt output)"),
    enrich: bool = typer.Option(False, "--enrich/--no-enrich", help="Fetch AS holder names from RIPEstat and use as node labels (GML output only)"),
    enrich_min_degree: int = typer.Option(DEFAULT_ENRICH_MIN_DEGREE, "--enrich-min-degree", help="With --enrich: only fetch names for nodes with degree >= this value", show_default=True, min=1),
    concurrency: int = typer.Option(DEFAULT_CONCURRENCY, "--concurrency", help="Max parallel RIPEstat requests (only used with --enrich)", show_default=True, min=1, max=50),
    cache_file: Path = typer.Option(DEFAULT_CACHE_PATH, "--cache", help=f"AS name cache path (JSON, TTL {CACHE_TTL_DAYS} days)", show_default=True),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        for suffix in (".gz", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        output = input.parent / (stem + ".gml")

    write_txt = output.suffix == ".txt"

    opener = gzip.open if _is_gzip(input) else open

    G = nx.Graph()
    skipped = edge_count = 0

    console.print(f"[bold]Reading[/bold] {input}")
    with opener(input, "rt") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                skipped += 1
                continue
            try:
                a, b = int(parts[0]), int(parts[1])
            except ValueError:
                skipped += 1
                continue
            for asn in (a, b):
                if asn not in G:
                    G.add_node(asn, asn=asn, label=str(asn))
            G.add_edge(a, b)
            edge_count += 1
            if edge_count % 100_000 == 0:
                console.print(f"  {edge_count:,} edges read…")

    if skipped:
        console.print(f"[yellow]Skipped {skipped} malformed lines[/yellow]")

    console.print(f"  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    # -----------------------------------------------------------------------
    # Degree filter
    # -----------------------------------------------------------------------
    if min_degree is not None:
        before = G.number_of_edges()
        remove = [(u, v) for u, v in G.edges() if G.degree(u) < min_degree or G.degree(v) < min_degree]
        G.remove_edges_from(remove)
        # Drop isolated nodes
        G.remove_nodes_from(list(nx.isolates(G)))
        console.print(
            f"  [bold]Degree filter[/bold] >= {min_degree}: "
            f"{G.number_of_edges():,} edges kept, {before - G.number_of_edges():,} dropped"
        )

    # -----------------------------------------------------------------------
    # Enrichment (GML only)
    # -----------------------------------------------------------------------
    if enrich:
        if write_txt:
            console.print("[yellow]--enrich is ignored for .txt output[/yellow]")
        else:
            cache = load_cache(cache_file)

            above = [str(n) for n in G.nodes if G.degree(n) >= enrich_min_degree]
            below_count = G.number_of_nodes() - len(above)

            fresh = [asn for asn in above if asn in cache and cache_is_fresh(cache[asn])]
            stale = [asn for asn in above if asn not in cache or not cache_is_fresh(cache[asn])]

            console.print(
                f"\n[bold]Enriching[/bold] {len(above):,} nodes (degree >= {enrich_min_degree}): "
                f"[green]{len(fresh):,} cached[/green], [cyan]{len(stale):,} to fetch[/cyan]"
                f" — {below_count:,} below threshold keep ASN as label"
            )

            if stale:
                asyncio.run(fetch_names_batch(stale, concurrency, cache))
                save_cache(cache, cache_file)
                console.print(f"  Cache saved → [dim]{cache_file}[/dim]")

            enriched = 0
            for node in G.nodes:
                asn_str = str(node)
                name = cache.get(asn_str, {}).get("name") if asn_str in cache else None
                if name and G.degree(node) >= enrich_min_degree:
                    G.nodes[node]["label"] = name
                    enriched += 1

            console.print(f"  {enriched:,} nodes labelled with holder name")

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------
    console.print(f"[bold]Writing[/bold] {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    if write_txt:
        fmt = "{:08d}" if justify_output else "{}"
        edges = sorted(
            (min(int(G.nodes[u]["asn"]), int(G.nodes[v]["asn"])),
             max(int(G.nodes[u]["asn"]), int(G.nodes[v]["asn"])))
            for u, v in G.edges()
        )
        with open(output, "w") as fh:
            for a, b in edges:
                fh.write(f"{fmt.format(a)} {fmt.format(b)}\n")
    else:
        nx.write_gml(G, output)

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {G.number_of_edges():,} edges written, {elapsed:.2f}s")


def _is_gzip(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


if __name__ == "__main__":
    app()
