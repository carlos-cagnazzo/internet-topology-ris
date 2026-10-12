"""
path-transit-freq.py — Count transit AS frequency across a path file.

For each AS path, the first ASN (route collector sensor) and last ASN (origin)
are stripped. The remaining intermediates are deduplicated per path (collapsing
prepends) and each unique intermediate increments its counter by one.

Paths with two or fewer ASNs have no intermediates and are skipped.

Output: one line per transit ASN, sorted by frequency descending.
  <ASN> <freq>
"""

import gzip
import time
from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer(help=__doc__)
console = Console()

ASN_FIELD_WIDTH = 8
_MAGIC_GZIP = b"\x1f\x8b"
_PROGRESS_ADVANCE_EVERY = 50_000


def _open_path_file(path: Path):
    """Open *path* for reading, transparently handling gzip compression."""
    with path.open("rb") as fh:
        magic = fh.read(2)
    if magic == _MAGIC_GZIP:
        return gzip.open(path, "rt")
    return path.open("r")


@app.command()
def main(
    input_file: Path = typer.Option(
        ...,
        "--input",
        help="AS path file to analyse (.txt or .txt.gz).",
        metavar="FILE",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        help=(
            "Output file. Default: <input-stem>-transit-freq.txt "
            "in the same directory as the input."
        ),
    ),
    justify_output: bool = typer.Option(
        True,
        "--justify-output/--no-justify-output",
        help=f"Zero-pad ASNs to {ASN_FIELD_WIDTH} digits (e.g. 6057 → {str(6057).zfill(ASN_FIELD_WIDTH)}).",
    ),
) -> None:
    """Count how often each ASN appears as a transit hop across all paths."""
    if not input_file.exists():
        console.print(f"[red]Input file not found: {input_file}[/red]")
        raise typer.Exit(1)

    # Derive default output path from input stem, handling both *.txt.gz and *.gz.txt
    if output is None:
        name = input_file.name
        for suffix in (".txt.gz", ".gz.txt", ".bz2.txt", ".txt"):
            if name.endswith(suffix):
                stem = name[: -len(suffix)]
                break
        else:
            stem = input_file.stem
        output = input_file.parent / f"{stem}-transit-freq.txt"

    start = time.monotonic()

    freq: dict[str, int] = defaultdict(int)
    total = 0
    skipped = 0

    console.print(f"\n[bold]Analysing[/bold] {input_file.name}\n")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task("Paths processed", total=None)
        with _open_path_file(input_file) as fh:
            for line in fh:
                tokens = line.split()
                total += 1
                if len(tokens) <= 2:
                    skipped += 1
                else:
                    for asn in set(tokens[1:-1]):
                        freq[asn] += 1
                if total % _PROGRESS_ADVANCE_EVERY == 0:
                    progress.advance(task, _PROGRESS_ADVANCE_EVERY)

    console.print(f"Sorting {len(freq):,} transit ASNs …")
    sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)

    with output.open("w") as fh:
        for asn, count in sorted_freq:
            if justify_output:
                fh.write(f"{asn.zfill(ASN_FIELD_WIDTH)} {count}\n")
            else:
                fh.write(f"{asn} {count}\n")

    elapsed = time.monotonic() - start
    console.print(
        f"\n[bold]Done.[/bold]"
        f" {total:,} paths · {skipped:,} skipped (≤2 ASes) · {len(freq):,} transit ASNs"
        f"\n→ [green]{output}[/green]  ({elapsed:.1f}s)"
    )


if __name__ == "__main__":
    app()
