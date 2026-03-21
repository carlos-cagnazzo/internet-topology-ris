"""
topology-to-gml.py — Convert a topology edge list to GML format.

Reads an AS-level topology edge list (as produced by build-topology.py) and
writes a GML file suitable for import into Gephi, yEd, Cytoscape, or any
other graph analysis tool.

Each node carries an 'asn' attribute. When --enrich is active, nodes with
degree >= --min-degree also receive a 'label' attribute containing the AS
holder name from RIPEstat. Holder names are cached locally for 60 days to
avoid redundant API calls across runs.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import networkx as nx
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer(help=__doc__)
console = Console()

RIPESTAT_BASE = "https://stat.ripe.net/data"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "internet-topology-ris" / "as-names.json"
CACHE_TTL_DAYS = 60
DEFAULT_CONCURRENCY = 10
DEFAULT_MIN_DEGREE = 3


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def load_cache(cache_path: Path) -> dict[str, dict]:
    """Load the AS name cache from disk.

    Args:
        cache_path: Path to the JSON cache file.

    Returns:
        Dict mapping ASN string to {'name': str, 'cached_at': ISO str}.
        Empty dict if the file does not exist or cannot be parsed.
    """
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict[str, dict], cache_path: Path) -> None:
    """Persist the AS name cache to disk.

    Args:
        cache:      Cache dict to write.
        cache_path: Destination path; parent directories are created as needed.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))


def cache_is_fresh(entry: dict) -> bool:
    """Return True if a cache entry is within the TTL window.

    Args:
        entry: Cache entry dict with a 'cached_at' ISO timestamp key.

    Returns:
        True if the entry is less than CACHE_TTL_DAYS old.
    """
    try:
        cached_at = datetime.fromisoformat(entry["cached_at"])
        return datetime.now(timezone.utc) - cached_at < timedelta(days=CACHE_TTL_DAYS)
    except (KeyError, ValueError):
        return False


# ---------------------------------------------------------------------------
# RIPEstat fetch
# ---------------------------------------------------------------------------

async def fetch_as_name(asn: str, client: httpx.AsyncClient) -> str | None:
    """Fetch the AS holder name from RIPEstat for a single ASN.

    Args:
        asn:    ASN as a plain string (e.g. '15169').
        client: Shared async HTTP client.

    Returns:
        Holder name string, or None if unavailable.
    """
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
) -> dict[str, str | None]:
    """Fetch AS holder names for a list of ASNs concurrently.

    Results are merged into *cache* in-place with fresh timestamps.

    Args:
        asns:        ASNs to fetch (already filtered: not in cache or expired).
        concurrency: Max simultaneous requests.
        cache:       Live cache dict; updated in-place with fetched results.

    Returns:
        Dict mapping ASN string to holder name (or None on failure).
    """
    if not asns:
        return {}

    sem = asyncio.Semaphore(concurrency)
    results: dict[str, str | None] = {}

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
        results[asn] = name
        cache[asn] = {
            "name": name,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        progress.advance(task)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        with progress:
            task = progress.add_task("  Fetching AS names", total=len(asns))
            await asyncio.gather(*(fetch_one(asn, client) for asn in asns))

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@app.command()
def main(
    input: Path = typer.Option(
        ...,
        "--input",
        help="Topology edge list file produced by build-topology.py.",
        metavar="FILE",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Output GML file. Default: input path with .gml extension.",
        metavar="FILE",
    ),
    enrich: bool = typer.Option(
        False,
        "--enrich/--no-enrich",
        help="Fetch AS holder names from RIPEstat and attach as node labels.",
    ),
    min_degree: int = typer.Option(
        DEFAULT_MIN_DEGREE,
        "--min-degree",
        help=(
            "When --enrich is active, only fetch names for nodes with degree "
            "at or above this threshold. Lower-degree nodes receive their ASN "
            "as label. Limits API calls for large topologies."
        ),
        show_default=True,
        min=1,
    ),
    concurrency: int = typer.Option(
        DEFAULT_CONCURRENCY,
        "--concurrency",
        help="Max parallel RIPEstat requests (only used with --enrich).",
        show_default=True,
        min=1,
        max=50,
    ),
    cache_file: Path = typer.Option(
        DEFAULT_CACHE_PATH,
        "--cache",
        help=f"Path to the local AS name JSON cache. TTL: {CACHE_TTL_DAYS} days.",
        show_default=True,
        metavar="FILE",
    ),
) -> None:
    """Convert a topology edge list to a GML graph file."""
    start = time.monotonic()

    if not input.exists():
        console.print(f"[red]Error:[/red] File not found: {input}")
        raise typer.Exit(1)

    if output is None:
        output = input.with_suffix(".gml")

    # ------------------------------------------------------------------
    # Parse edge list
    # ------------------------------------------------------------------
    console.print(f"\n[bold]Reading edge list:[/bold] {input}\n")

    edges: list[tuple[int, int]] = []
    skipped = 0
    with input.open() as fh:
        for line in fh:
            tokens = line.split()
            if len(tokens) < 2:
                skipped += 1
                continue
            try:
                a, b = int(tokens[0]), int(tokens[1])
            except ValueError:
                skipped += 1
                continue
            edges.append((a, b))

    if not edges:
        console.print("[red]Error:[/red] No valid edges found in input file.")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Build graph
    # ------------------------------------------------------------------
    G = nx.Graph()
    G.add_edges_from(edges)

    for node in G.nodes:
        G.nodes[node]["asn"] = str(node)

    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()
    console.print(f"  Nodes : [bold]{node_count:,}[/bold]")
    console.print(f"  Edges : [bold]{edge_count:,}[/bold]")

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------
    enriched = 0
    from_cache = 0
    skipped_degree = 0

    if enrich:
        cache = load_cache(cache_file)

        # Separate nodes by degree threshold
        above = [str(n) for n in G.nodes if G.degree(n) >= min_degree]
        below = [str(n) for n in G.nodes if G.degree(n) < min_degree]
        skipped_degree = len(below)

        console.print(
            f"\n  [bold]Enrichment:[/bold] {len(above):,} nodes with degree ≥ {min_degree} "
            f"will be looked up; {skipped_degree:,} below threshold will use ASN as label."
        )

        # Split above into cache hits and misses
        fresh = [asn for asn in above if asn in cache and cache_is_fresh(cache[asn])]
        stale = [asn for asn in above if asn not in cache or not cache_is_fresh(cache[asn])]
        from_cache = len(fresh)

        console.print(
            f"  Cache hits: [green]{from_cache:,}[/green]  "
            f"Fetching from RIPEstat: [cyan]{len(stale):,}[/cyan]\n"
        )

        # Fetch stale/missing names
        if stale:
            asyncio.run(fetch_names_batch(stale, concurrency, cache))
            save_cache(cache, cache_file)
            console.print(f"  Cache saved → [dim]{cache_file}[/dim]\n")

        # Build relabel mapping: int node → display string
        # networkx uses the node key as GML label, so we relabel nodes
        # to their holder names. The original ASN is preserved as the
        # 'asn' attribute set earlier.
        label_map: dict[int, str] = {}
        for node in G.nodes:
            asn_str = str(node)
            name = cache.get(asn_str, {}).get("name") if asn_str in cache else None
            label_map[node] = name if name else asn_str
            if name and asn_str in above:
                enriched += 1

        G = nx.relabel_nodes(G, label_map)

    # ------------------------------------------------------------------
    # Write GML
    # ------------------------------------------------------------------
    output.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"  Writing GML → [green]{output}[/green] ...")
    nx.write_gml(G, str(output))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    elapsed = time.monotonic() - start
    console.print(f"\n[bold]Done.[/bold]")
    console.print(f"  Nodes          : {node_count:,}")
    console.print(f"  Edges          : {edge_count:,}")
    if enrich:
        console.print(f"  Enriched       : {enriched:,}")
        console.print(f"  From cache     : {from_cache:,}")
        console.print(f"  Below threshold: {skipped_degree:,}")
    console.print(f"  Output         : {output}")
    console.print(f"  Elapsed        : {elapsed:.1f}s")


if __name__ == "__main__":
    app()
