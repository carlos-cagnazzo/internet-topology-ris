"""
hubs.py — List ASNs with degree >= a given threshold from a NetworkX GML file.

Without --wide: one ASN per line, sorted numerically.
With --wide:    two columns (ASN degree), sorted by degree descending.
"""

import time
from pathlib import Path

import networkx as nx
import typer
from rich.console import Console

app = typer.Typer(help=__doc__)
console = Console()


@app.command()
def main(
    input: Path = typer.Option(..., "--input", "-i", help="GML file produced by topo-to-nx.py"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (default: input stem + -hubs.txt)"),
    min_degree: int = typer.Option(..., "--min-degree", "-d", help="Minimum degree (inclusive)"),
    wide: bool = typer.Option(False, "--wide", help="Add degree column; sort by degree descending"),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        if stem.endswith(".gml"):
            stem = stem[:-4]
        output = input.parent / (stem + "-hubs.txt")

    console.print(f"[bold]Reading[/bold] {input}")
    G = nx.read_gml(input)

    results = [(int(node), deg) for node, deg in G.degree() if deg >= min_degree]

    if wide:
        results.sort(key=lambda x: x[1], reverse=True)
    else:
        results.sort(key=lambda x: x[0])

    console.print(f"[bold]Writing[/bold] {output}  ({len(results):,} ASNs with degree >= {min_degree})")
    with open(output, "w") as fh:
        for asn, deg in results:
            fh.write(f"{asn} {deg}\n" if wide else f"{asn}\n")

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {elapsed:.2f}s")


if __name__ == "__main__":
    app()
