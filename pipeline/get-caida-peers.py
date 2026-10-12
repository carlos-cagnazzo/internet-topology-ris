"""
get-caida-peers.py — Download and extract peer-to-peer AS relationships from CAIDA.

Fetches the CAIDA AS relationships dataset for a given year-month and produces
two output files:

  caida-peers-YYYYMM.txt  — peer-to-peer edges (rel=0), deduplicated and sorted
  caida-tier1-YYYYMM.txt  — potential Tier 1 ASNs: those that provide transit
                             to others (appear as provider in rel=-1) but never
                             buy transit themselves (never appear as customer)

Dataset preference: serial-2 is tried first; serial-1 is used as fallback
for months not covered by serial-2 (roughly pre-2012).

Output format matches the rest of the pipeline: one undirected edge per line,
smaller ASN first, zero-padded to 8 digits by default.
"""

import bz2
import re
import time
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer(help=__doc__)
console = Console()

ASN_FIELD_WIDTH = 8

SERIAL2_INDEX = "https://publicdata.caida.org/datasets/as-relationships/serial-2/"
SERIAL1_INDEX = "https://publicdata.caida.org/datasets/as-relationships/serial-1/"
SERIAL2_PAT = re.compile(r'href="(\d{8}\.as-rel2\.txt\.bz2)"')
SERIAL1_PAT = re.compile(r'href="(\d{8}\.as-rel\.txt\.bz2)"')


def _find_file_for_month(yyyymm: str) -> tuple[str, str]:
    """Return (url, filename) for the given YYYYMM, preferring serial-2.

    Raises typer.Exit if no file is found in either dataset.
    """
    for base_url, pattern, label in [
        (SERIAL2_INDEX, SERIAL2_PAT, "serial-2"),
        (SERIAL1_INDEX, SERIAL1_PAT, "serial-1"),
    ]:
        console.print(f"[dim]Checking {label} index …[/dim]")
        try:
            resp = httpx.get(base_url, follow_redirects=True, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            console.print(f"[yellow]Warning: could not fetch {label} index: {exc}[/yellow]")
            continue

        matches = [m for m in pattern.findall(resp.text) if m.startswith(yyyymm)]
        if matches:
            filename = sorted(matches)[-1]  # latest if multiple in month
            url = base_url + filename
            console.print(f"[green]Found[/green] {label}: [bold]{filename}[/bold]")
            return url, filename

    console.print(f"[red]No CAIDA file found for {yyyymm} in serial-1 or serial-2.[/red]")
    raise typer.Exit(1)


def _download(url: str, dest: Path) -> None:
    """Stream-download *url* to *dest*, showing a progress spinner."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Downloading {dest.name} …", total=None)
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
            resp.raise_for_status()
            tmp = dest.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes(65536):
                    fh.write(chunk)
                    progress.advance(task)
        tmp.rename(dest)


def _parse_relationships(
    path: Path,
) -> tuple[set[tuple[int, int]], set[int]]:
    """Decompress and parse *path* in one pass.

    Returns:
        peer_edges  — set of (min, max) integer tuples for rel=0 lines
        tier1       — ASNs that provide transit (rel=-1, AS1 role) but never
                      buy it (never appear as AS2 in a rel=-1 line)
    """
    peer_edges: set[tuple[int, int]] = set()
    providers: set[int] = set()   # AS1 in a rel=-1 line (sells transit)
    customers: set[int] = set()   # AS2 in a rel=-1 line (buys transit)

    with bz2.open(path, "rt") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            if len(fields) < 3:
                continue
            try:
                a, b, rel = int(fields[0]), int(fields[1]), fields[2]
            except ValueError:
                continue
            if rel == "0":
                peer_edges.add((a, b) if a < b else (b, a))
            elif rel == "-1":
                providers.add(a)
                customers.add(b)

    tier1 = providers - customers
    return peer_edges, tier1


@app.command()
def main(
    date: str = typer.Option(
        ...,
        "--date",
        help="Year-month to fetch, YYYYMM format.",
        metavar="YYYYMM",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        help=(
            "Output file path. "
            "Default: ./output-combined/YYYYMM/caida-peers-YYYYMM.txt"
        ),
    ),
    justify_output: bool = typer.Option(
        True,
        "--justify-output/--no-justify-output",
        help=f"Zero-pad ASNs to {ASN_FIELD_WIDTH} digits (e.g. 6057 → {str(6057).zfill(ASN_FIELD_WIDTH)}).",
    ),
    cache_dir: Path = typer.Option(
        Path("./caida-cache"),
        "--cache-dir",
        help="Directory for cached .bz2 files. Permanent — CAIDA files never change.",
        show_default=True,
    ),
) -> None:
    """Download CAIDA AS relationships for YYYYMM and write peer-to-peer edge list."""
    if not re.fullmatch(r"\d{6}", date):
        console.print("[red]--date must be YYYYMM (6 digits), e.g. 202401[/red]")
        raise typer.Exit(1)

    if output is None:
        output = Path("./output-combined") / date / f"caida-peers-{date}.txt"
    tier1_output = output.parent / f"caida-tier1-{date}.txt"

    start = time.monotonic()

    url, filename = _find_file_for_month(date)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / filename

    if cached.exists():
        console.print(f"[dim]Using cached {filename}[/dim]")
    else:
        _download(url, cached)

    console.print(f"Parsing [bold]{filename}[/bold] …")
    edges, tier1 = _parse_relationships(cached)

    console.print(f"Sorting {len(edges):,} peer pairs …")
    sorted_edges = sorted(edges)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as fh:
        for a, b in sorted_edges:
            if justify_output:
                fh.write(f"{str(a).zfill(ASN_FIELD_WIDTH)} {str(b).zfill(ASN_FIELD_WIDTH)}\n")
            else:
                fh.write(f"{a} {b}\n")

    with tier1_output.open("w") as fh:
        for asn in sorted(tier1):
            fh.write(f"{str(asn).zfill(ASN_FIELD_WIDTH)}\n" if justify_output else f"{asn}\n")

    elapsed = time.monotonic() - start
    console.print(
        f"\n[bold]Done.[/bold] {len(edges):,} peer pairs → [green]{output}[/green]"
        f"\n        {len(tier1):,} potential Tier 1 ASNs  → [green]{tier1_output}[/green]"
        f"\n        {elapsed:.1f}s elapsed"
    )


if __name__ == "__main__":
    app()
