"""
topology-ops.py — Set operations on AS-level topology edge lists.

Combines two topology files (as produced by build-topology.py) using either
a union (add) or difference (sub) operation:

  add  — output contains all edges present in either input (deduplicated)
  sub  — output contains edges from input1 that are not present in input2

Both plain and zero-padded ASN formats are handled transparently; comparison
is always done numerically. Output format is controlled by --justify-output.
"""

import time
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help=__doc__)
console = Console()

ASN_FIELD_WIDTH = 8


class Op(str, Enum):
    add = "add"
    sub = "sub"


def fmt(asn: int, justify: bool) -> str:
    """Format an ASN integer for file output.

    Args:
        asn:     ASN as an integer.
        justify: When True, zero-pad to ASN_FIELD_WIDTH digits.

    Returns:
        Formatted ASN string.
    """
    return str(asn).zfill(ASN_FIELD_WIDTH) if justify else str(asn)


def read_edges(path: Path) -> set[tuple[int, int]]:
    """Read a topology edge list into a set of integer edge tuples.

    Handles both plain (6 22773) and zero-padded (00000006 00022773) formats.
    Edges are stored as (min, max) tuples so that (A, B) and (B, A) are
    treated as the same edge regardless of column order in the file.

    Args:
        path: Path to the topology edge list file.

    Returns:
        Set of (a, b) tuples where a < b, both integers.
    """
    edges: set[tuple[int, int]] = set()
    skipped = 0
    with path.open() as fh:
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
            edges.add((a, b) if a < b else (b, a))
    return edges


@app.command()
def main(
    op: Op = typer.Option(
        ...,
        "--op",
        help="Operation to perform: 'add' (union) or 'sub' (difference).",
        case_sensitive=False,
    ),
    input1: Path = typer.Option(
        ...,
        "--input1",
        help="First topology edge list file.",
        metavar="FILE",
    ),
    input2: Path = typer.Option(
        ...,
        "--input2",
        help="Second topology edge list file.",
        metavar="FILE",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        help="Output edge list file.",
        metavar="FILE",
    ),
    justify_output: bool = typer.Option(
        False,
        "--justify-output/--no-justify-output",
        help=(
            f"Zero-pad all ASNs to {ASN_FIELD_WIDTH} digits in the output file "
            f"(e.g. AS 6057 → {str(6057).zfill(ASN_FIELD_WIDTH)})."
        ),
    ),
) -> None:
    """Perform set operations (add/sub) on two topology edge list files."""
    start = time.monotonic()

    for path, flag in ((input1, "--input1"), (input2, "--input2")):
        if not path.exists():
            console.print(f"[red]Error:[/red] {flag} file not found: {path}")
            raise typer.Exit(1)

    console.print(f"\n[bold]Operation:[/bold] {op.value}\n")

    console.print(f"  Reading [cyan]{input1}[/cyan] ...")
    edges1 = read_edges(input1)
    console.print(f"    {len(edges1):,} edges\n")

    console.print(f"  Reading [cyan]{input2}[/cyan] ...")
    edges2 = read_edges(input2)
    console.print(f"    {len(edges2):,} edges\n")

    # Apply operation
    if op == Op.add:
        result = edges1 | edges2
    else:
        result = edges1 - edges2

    removed = len(edges1) - len(result) if op == Op.sub else None

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"  Writing [bold]{len(result):,}[/bold] edges to [green]{output}[/green] ...")
    with output.open("w") as fh:
        for a, b in sorted(result):
            fh.write(f"{fmt(a, justify_output)} {fmt(b, justify_output)}\n")

    elapsed = time.monotonic() - start
    console.print(f"\n[bold]Done.[/bold]")
    console.print(f"  input1 edges : {len(edges1):,}")
    console.print(f"  input2 edges : {len(edges2):,}")
    if op == Op.sub:
        console.print(f"  removed      : {removed:,}")
    console.print(f"  output edges : {len(result):,}")
    console.print(f"  elapsed      : {elapsed:.1f}s")


if __name__ == "__main__":
    app()
