"""
build-topology.py — Build a deduplicated AS-level topology edge list.

Reads AS path files produced by process-mrt.py, extracts all AS-to-AS links,
and writes a sorted, deduplicated undirected edge list to an output file.

Each line of the output contains two space-separated ASNs representing a link:

    13335 15169
    1299 3356
    ...

Links are undirected: (A, B) and (B, A) are the same edge. Paths are expected
to already be clean (no prepending, no AS sets) as produced by process-mrt.py.

Optionally filters edges to include only ASNs that are formally assigned by one
of the five RIRs, using the NRO delegated extended stats file as the source of
truth. The stats file is cached next to the input files and re-downloaded only
if it is more than 24 hours old.
"""

import time
from glob import glob
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer(help=__doc__)
console = Console()

NRO_STATS_URL = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats"
NRO_CACHE_FILENAME = "nro-delegated-stats"
NRO_MAX_AGE_SECONDS = 24 * 3600


def fetch_nro_stats(cache_path: Path) -> Path:
    """Return path to a fresh NRO delegated stats file, downloading if needed.

    The file is cached at *cache_path*. If it exists and is less than 24 hours
    old it is returned as-is. Otherwise it is downloaded from the NRO server.

    Args:
        cache_path: Local path where the stats file should be cached.

    Returns:
        Path to the cached file.
    """
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < NRO_MAX_AGE_SECONDS:
            console.print(
                f"  [dim]NRO stats cache is {age / 3600:.1f}h old — reusing[/dim] {cache_path}"
            )
            return cache_path

    console.print(f"  Downloading NRO delegated stats → [green]{cache_path}[/green]")
    with httpx.stream("GET", NRO_STATS_URL, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=65536):
                fh.write(chunk)

    return cache_path


def load_registered_asns(stats_path: Path) -> set[str]:
    """Parse the NRO delegated stats file and return the set of assigned ASNs.

    Only records where type == 'asn' and status == 'assigned' are included.
    Summary lines (where the count field is 'summary') are skipped, as are
    header lines.

    The count field is respected: an entry with start=64496 and count=10 adds
    ASNs 64496 through 64505 inclusive.

    Args:
        stats_path: Path to the local NRO delegated stats file.

    Returns:
        Set of ASN strings for all assigned autonomous systems.
    """
    registered: set[str] = set()
    with stats_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            # Header line starts with a version number (single integer field)
            if len(fields) < 7:
                continue
            # Skip summary lines: field[4] == 'summary' or field[1] == '*'
            if fields[1] == "*" or fields[4] == "summary":
                continue
            if fields[2] != "asn":
                continue
            if fields[6] != "assigned":
                continue
            try:
                start = int(fields[3])
                count = int(fields[4])
            except ValueError:
                continue
            for asn in range(start, start + count):
                registered.add(str(asn))
    return registered


@app.command()
def main(
    input_files: str = typer.Option(
        ...,
        "--input",
        help='Glob pattern matching AS path .txt files to process (e.g. "./paths/*.txt").',
        metavar="GLOB",
    ),
    output: Path = typer.Option(
        Path("./topology.txt"),
        "--output",
        help="Output file for the deduplicated edge list.",
        show_default=True,
    ),
    filter_registered: bool = typer.Option(
        False,
        "--filter-registered/--no-filter-registered",
        help=(
            "When enabled, drops any edge where either ASN is not formally assigned "
            "according to the NRO delegated extended stats. Unregistered ASNs are "
            "written to a sidecar file next to --output."
        ),
    ),
) -> None:
    """Build a deduplicated undirected AS-level topology edge list from AS path files."""
    start = time.monotonic()

    matches = sorted(glob(input_files))
    if not matches:
        console.print(f"[red]Error:[/red] No files matched: {input_files}")
        raise typer.Exit(1)

    total_files = len(matches)
    console.print(f"\n[bold]Building topology from {total_files} file(s)[/bold]")

    # Load registered ASN filter if requested
    registered_asns: set[str] | None = None
    if filter_registered:
        input_dir = Path(matches[0]).parent
        cache_path = input_dir / NRO_CACHE_FILENAME
        console.print()
        registered_asns = load_registered_asns(fetch_nro_stats(cache_path))
        console.print(f"  [bold]{len(registered_asns):,}[/bold] assigned ASNs loaded from NRO stats\n")
    else:
        console.print()

    edges: set[tuple[str, str]] = set()
    asns: set[str] = set()
    dropped_edges: set[tuple[str, str]] = set()
    dropped_asns: set[str] = set()
    total_paths = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        overall = progress.add_task("Files", total=total_files)
        for txt_path in matches:
            progress.update(overall, description=f"[cyan]{Path(txt_path).name}[/cyan]")
            with open(txt_path) as fh:
                for line in fh:
                    tokens = line.split()
                    if len(tokens) < 2:
                        continue
                    total_paths += 1
                    for a, b in zip(tokens, tokens[1:]):
                        edge = (a, b) if int(a) < int(b) else (b, a)
                        if registered_asns is not None:
                            a_ok = a in registered_asns
                            b_ok = b in registered_asns
                            if not a_ok or not b_ok:
                                dropped_edges.add(edge)
                                if not a_ok:
                                    dropped_asns.add(a)
                                if not b_ok:
                                    dropped_asns.add(b)
                                continue
                        edges.add(edge)
                        asns.add(a)
                        asns.add(b)
            progress.advance(overall)

    # Write topology
    console.print(f"  Writing [bold]{len(edges):,}[/bold] edges to [green]{output}[/green] ...")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as fh:
        for a, b in sorted(edges, key=lambda e: (int(e[0]), int(e[1]))):
            fh.write(f"{a} {b}\n")

    # Write dropped ASNs sidecar file
    if filter_registered and dropped_asns:
        dropped_path = output.parent / f"{output.stem}-dropped-asns{output.suffix}"
        console.print(
            f"  Writing [bold]{len(dropped_asns):,}[/bold] dropped ASNs to [yellow]{dropped_path}[/yellow] ..."
        )
        with dropped_path.open("w") as fh:
            for asn in sorted(dropped_asns, key=int):
                fh.write(f"{asn}\n")

    elapsed = time.monotonic() - start
    summary = (
        f"\n[bold]Done.[/bold]\n"
        f"  Files processed : {total_files:,}\n"
        f"  AS paths read   : {total_paths:,}\n"
        f"  Unique edges    : {len(edges):,}\n"
        f"  Unique ASNs     : {len(asns):,}\n"
    )
    if filter_registered:
        summary += (
            f"  Dropped edges   : {len(dropped_edges):,}\n"
            f"  Dropped ASNs    : {len(dropped_asns):,}\n"
        )
    summary += f"  Elapsed         : {elapsed:.1f}s"
    console.print(summary)


if __name__ == "__main__":
    app()
