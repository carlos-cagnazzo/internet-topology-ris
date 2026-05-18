"""
hubs.py — List high-degree ASNs from a NetworkX GML topology graph.

This tool reads a GML file produced by topology-to-gml.py and writes a list of all
ASNs whose degree (number of direct neighbours) is greater than or equal to the
value given by --min-degree. In the context of AS-level Internet topology, high-
degree nodes are transit providers, Internet exchange points, and large content
networks — commonly referred to as tier-1 or tier-2 operators.

Without --wide, the output is a plain list with one ASN per line, sorted
numerically. With --wide, the output has two columns (ASN and degree), sorted
by degree in descending order, making it easy to identify the most connected
ASNs at a glance. The output file can be used as input to other tools or
processed directly with standard Unix utilities.
"""

import time
from pathlib import Path

import networkx as nx
import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command(help=__doc__)
def main(
    input: Path = typer.Option(..., "--input", "-i", help="GML file produced by topology-to-gml.py"),
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
