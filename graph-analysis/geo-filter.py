"""
geo-filter.py — Filter an AS-level topology to a set of countries.

This tool filters a topology so that only edges where both ASNs are assigned
to one of the specified countries are retained. Country assignment is determined
by the NRO delegated extended statistics file, which maps each registered ASN to
the ISO 3166-1 alpha-2 country code of the RIR member that received the
allocation. ASNs not present in the NRO file (unregistered, private, or
reserved) are treated as having no country and are excluded.

The tool accepts either a two-column topology edge list (.txt or .txt.gz) or a
NetworkX GML file as input, and always produces two output files: a .txt
topology edge list and a .gml graph. In the GML output, each node carries a
'country' attribute in addition to 'asn' and 'label', which is useful for
visualisation and further analysis.

The NRO delegated stats file is fetched automatically from the RIPE NCC FTP
server and cached next to the input file. Without --date, the latest available
file is used and re-fetched if the cache is older than 24 hours. With --date
(YYYYMMDD), the historical snapshot for that date is used instead and cached
permanently, since historical files never change. This allows reproducible
filtering tied to a specific point in time.
"""

import gzip
import time
from pathlib import Path

import httpx
import networkx as nx
import typer
from rich.console import Console

app = typer.Typer()
console = Console()

NRO_STATS_URL_LATEST = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats"
NRO_STATS_URL_HISTORICAL = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{date}/nro-delegated-stats"
NRO_CACHE_LATEST = "nro-delegated-stats"
NRO_CACHE_DATED = "nro-delegated-stats-{date}"
NRO_MAX_AGE_SECONDS = 86400


# ---------------------------------------------------------------------------
# NRO stats
# ---------------------------------------------------------------------------

def fetch_nro_stats(cache_dir: Path, date: str | None) -> Path:
    if date:
        url = NRO_STATS_URL_HISTORICAL.format(date=date)
        cache_path = cache_dir / NRO_CACHE_DATED.format(date=date)
        if cache_path.exists():
            console.print(f"  [dim]NRO stats ({date}) cached — reusing[/dim] {cache_path}")
            return cache_path
    else:
        url = NRO_STATS_URL_LATEST
        cache_path = cache_dir / NRO_CACHE_LATEST
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < NRO_MAX_AGE_SECONDS:
                console.print(f"  [dim]NRO stats cache {age / 3600:.1f}h old — reusing[/dim] {cache_path}")
                return cache_path

    console.print(f"  Downloading NRO delegated stats → [green]{cache_path}[/green]")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=65536):
                fh.write(chunk)
    return cache_path


def load_asn_countries(stats_path: Path) -> dict[int, str]:
    """Parse NRO delegated stats and return {asn: country_code} for assigned ASNs."""
    result: dict[int, str] = {}
    with stats_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            if len(fields) < 7:
                continue
            if fields[1] == "*" or fields[4] == "summary":
                continue
            if fields[2] != "asn":
                continue
            if fields[6] != "assigned":
                continue
            cc = fields[1]
            try:
                start = int(fields[3])
                count = int(fields[4])
            except ValueError:
                continue
            for asn in range(start, start + count):
                result[asn] = cc
    return result


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

def load_from_txt(path: Path) -> nx.Graph:
    opener = gzip.open if _is_gzip(path) else open
    G = nx.Graph()
    edge_count = skipped = 0
    with opener(path, "rt") as fh:
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
        console.print(f"  [yellow]Skipped {skipped} malformed lines[/yellow]")
    return G


def load_from_gml(path: Path) -> nx.Graph:
    try:
        G = nx.read_gml(path)
    except Exception as e:
        console.print(f"[red]Error:[/red] could not parse GML file: {e}")
        raise typer.Exit(1)
    # Normalise: ensure every node has an integer asn attribute
    for node, attrs in G.nodes(data=True):
        if "asn" not in attrs:
            console.print(f"[red]Error:[/red] node '{node}' has no 'asn' attribute")
            raise typer.Exit(1)
        G.nodes[node]["asn"] = int(attrs["asn"])
    return G


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@app.command(help=__doc__)
def main(
    input: Path = typer.Option(..., "--input", "-i", help="Topology .txt/.txt.gz or .gml file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output base path without extension (default: input stem + -geo); produces .txt and .gml"),
    countries: str = typer.Option(..., "--countries", "-c", help="Comma-separated ISO 3166-1 alpha-2 country codes (e.g. BR,AR,CL)"),
    date: str = typer.Option(None, "--date", help="NRO stats date YYYYMMDD (default: latest)"),
    justify_output: bool = typer.Option(False, "--justify-output", help="Zero-pad ASNs to 8 digits in .txt output"),
) -> None:
    t0 = time.perf_counter()

    # Output paths
    if output is None:
        stem = input.name
        for suffix in (".gml", ".gz", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        base = input.parent / (stem + "-geo")
    else:
        base = output.parent / output.stem if output.suffix else output
    out_txt = base.parent / (base.name + ".txt")
    out_gml = base.parent / (base.name + ".gml")

    country_set = {c.strip().upper() for c in countries.split(",")}
    console.print(f"[bold]Countries:[/bold] {', '.join(sorted(country_set))}")

    # Load NRO stats
    console.print("[bold]NRO stats[/bold]")
    stats_path = fetch_nro_stats(input.parent, date)
    console.print(f"  Parsing {stats_path.name}…")
    asn_country = load_asn_countries(stats_path)
    console.print(f"  {len(asn_country):,} assigned ASNs loaded")

    # Load graph
    is_gml = input.suffix == ".gml" or (input.suffix != ".gz" and not _is_gzip(input) and _looks_like_gml(input))
    console.print(f"[bold]Reading[/bold] {input}")
    G = load_from_gml(input) if is_gml else load_from_txt(input)
    console.print(f"  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    # Filter
    kept_edges = []
    dropped = unknown = 0
    for u, v in G.edges():
        a = int(G.nodes[u]["asn"])
        b = int(G.nodes[v]["asn"])
        cc_a = asn_country.get(a)
        cc_b = asn_country.get(b)
        if cc_a is None or cc_b is None:
            unknown += 1
            dropped += 1
            continue
        if cc_a in country_set and cc_b in country_set:
            kept_edges.append((min(a, b), max(a, b)))
        else:
            dropped += 1
    kept_edges.sort()

    kept_nodes = {asn for edge in kept_edges for asn in edge}
    console.print(
        f"  [green]{len(kept_edges):,} edges kept[/green], "
        f"{dropped:,} dropped ({unknown:,} had unknown country)"
    )

    # Write .txt
    fmt = "{:08d}" if justify_output else "{}"
    console.print(f"[bold]Writing[/bold] {out_txt}")
    with open(out_txt, "w") as fh:
        for a, b in kept_edges:
            fh.write(f"{fmt.format(a)} {fmt.format(b)}\n")

    # Write .gml
    console.print(f"[bold]Writing[/bold] {out_gml}")
    H = nx.Graph()
    for asn in kept_nodes:
        cc = asn_country.get(asn, "")
        label = G.nodes[asn]["label"] if asn in G.nodes else str(asn)
        H.add_node(asn, asn=asn, label=label, country=cc)
    for a, b in kept_edges:
        H.add_edge(a, b)
    nx.write_gml(H, out_gml)

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {elapsed:.2f}s")


def _is_gzip(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def _looks_like_gml(path: Path) -> bool:
    try:
        with open(path, "r") as fh:
            return fh.read(10).strip().startswith("graph")
    except OSError:
        return False


if __name__ == "__main__":
    app()
