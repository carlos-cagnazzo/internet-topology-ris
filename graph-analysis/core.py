"""
core.py — Filter a topology edge list to edges where both endpoints meet a minimum degree.

Reads a two-column AS-level topology file and outputs only edges where both
ASNs have degree >= --min-degree. Output is sorted numerically by ASN1 (with
ASN1 < ASN2 always). Accepts plain or gzip-compressed input.
"""

import gzip
import time
from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help=__doc__)
console = Console()


@app.command()
def main(
    input: Path = typer.Option(..., "--input", "-i", help="Topology edge list file (.txt or .txt.gz)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (default: input stem + -core.txt)"),
    min_degree: int = typer.Option(..., "--min-degree", "-d", help="Minimum degree for both endpoints (inclusive)"),
    wide: bool = typer.Option(False, "--wide", help="Add DEG1 DEG2 columns"),
    justify_output: bool = typer.Option(False, "--justify-output", help="Zero-pad ASNs to 8 digits"),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        for suffix in (".gz", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        output = input.parent / (stem + "-core.txt")

    opener = gzip.open if _is_gzip(input) else open

    edges = []
    degree: dict[int, int] = defaultdict(int)
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
            a, b = int(parts[0]), int(parts[1])
            if a > b:
                a, b = b, a
            edges.append((a, b))
            degree[a] += 1
            degree[b] += 1
            edge_count += 1
            if edge_count % 100_000 == 0:
                console.print(f"  {edge_count:,} edges read…")

    if skipped:
        console.print(f"[yellow]Skipped {skipped} malformed lines[/yellow]")

    console.print(f"[bold]Filtering[/bold] degree >= {min_degree}")
    filtered = [(a, b) for a, b in edges if degree[a] >= min_degree and degree[b] >= min_degree]
    filtered.sort()

    fmt = f"{{:08d}}" if justify_output else "{}"

    console.print(f"[bold]Writing[/bold] {output}  ({len(filtered):,} / {len(edges):,} edges kept)")
    with open(output, "w") as fh:
        for a, b in filtered:
            if wide:
                fh.write(f"{fmt.format(a)} {fmt.format(b)} {degree[a]} {degree[b]}\n")
            else:
                fh.write(f"{fmt.format(a)} {fmt.format(b)}\n")

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {elapsed:.2f}s")


def _is_gzip(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


if __name__ == "__main__":
    app()
