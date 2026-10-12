"""
topology-ops.py — Set operations on AS-level topology edge lists.

Combines two or more topology files (as produced by build-topology.py) using
either a union (add) or difference (sub) operation:

  add  — output contains all edges present in any input (deduplicated union)
  sub  — output contains edges from the first file that are absent from all
         remaining files (first minus the union of the rest)

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
    with path.open() as fh:
        for line in fh:
            tokens = line.split()
            if len(tokens) < 2:
                continue
            try:
                a, b = int(tokens[0]), int(tokens[1])
            except ValueError:
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
    inputs: list[Path] = typer.Argument(
        ...,
        help=(
            "Two or more topology edge list files. "
            "For 'add': union of all files. "
            "For 'sub': first file minus the union of the remaining files."
        ),
        metavar="FILE...",
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
    """Perform set operations (add/sub) on two or more topology edge list files."""
    start = time.monotonic()

    if len(inputs) < 2:
        console.print("[red]Error:[/red] at least two input files are required.")
        raise typer.Exit(1)

    for path in inputs:
        if not path.exists():
            console.print(f"[red]Error:[/red] file not found: {path}")
            raise typer.Exit(1)

    console.print(f"\n[bold]Operation:[/bold] {op.value} ({len(inputs)} files)\n")

    edge_sets: list[set[tuple[int, int]]] = []
    for path in inputs:
        console.print(f"  Reading [cyan]{path}[/cyan] ...")
        edges = read_edges(path)
        console.print(f"    {len(edges):,} edges")
        edge_sets.append(edges)
    console.print()

    if op == Op.add:
        result = edge_sets[0]
        for es in edge_sets[1:]:
            result = result | es
    else:
        subtrahend: set[tuple[int, int]] = set()
        for es in edge_sets[1:]:
            subtrahend = subtrahend | es
        result = edge_sets[0] - subtrahend

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"  Writing [bold]{len(result):,}[/bold] edges to [green]{output}[/green] ...")
    with output.open("w") as fh:
        for a, b in sorted(result):
            fh.write(f"{fmt(a, justify_output)} {fmt(b, justify_output)}\n")

    elapsed = time.monotonic() - start
    console.print(f"\n[bold]Done.[/bold]")
    for i, (path, es) in enumerate(zip(inputs, edge_sets)):
        label = "base  " if (op == Op.sub and i == 0) else f"input{i + 1}"
        console.print(f"  {label} ({path.name}): {len(es):,} edges")
    if op == Op.sub:
        console.print(f"  removed : {len(edge_sets[0]) - len(result):,}")
    console.print(f"  output  : {len(result):,} edges")
    console.print(f"  elapsed : {elapsed:.1f}s")


if __name__ == "__main__":
    app()
