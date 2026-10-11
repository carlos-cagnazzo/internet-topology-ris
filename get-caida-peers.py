"""
get-caida-peers.py — Download and extract peer-to-peer AS relationships from CAIDA.

Fetches the CAIDA AS relationships dataset for a given year-month, extracts
peer-to-peer edges (relationship code 0), deduplicates, sorts, and writes a
two-column edge list.

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


def _parse_peers(path: Path) -> set[tuple[int, int]]:
    """Decompress and parse *path*, returning peer-to-peer edges as integer tuples."""
    edges: set[tuple[int, int]] = set()
    with bz2.open(path, "rt") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            if len(fields) < 3:
                continue
            if fields[2] != "0":
                continue
            try:
                a, b = int(fields[0]), int(fields[1])
            except ValueError:
                continue
            edges.add((a, b) if a < b else (b, a))
    return edges


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

    start = time.monotonic()

    url, filename = _find_file_for_month(date)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / filename

    if cached.exists():
        console.print(f"[dim]Using cached {filename}[/dim]")
    else:
        _download(url, cached)

    console.print(f"Parsing [bold]{filename}[/bold] …")
    edges = _parse_peers(cached)

    console.print(f"Sorting {len(edges):,} peer pairs …")
    sorted_edges = sorted(edges)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as fh:
        for a, b in sorted_edges:
            if justify_output:
                fh.write(f"{str(a).zfill(ASN_FIELD_WIDTH)} {str(b).zfill(ASN_FIELD_WIDTH)}\n")
            else:
                fh.write(f"{a} {b}\n")

    elapsed = time.monotonic() - start
    console.print(
        f"\n[bold]Done.[/bold] {len(edges):,} peer pairs → [green]{output}[/green]"
        f" — {elapsed:.1f}s elapsed"
    )


if __name__ == "__main__":
    app()
