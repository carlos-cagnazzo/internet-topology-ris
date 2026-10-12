"""
hubs.py — List high-degree ASNs from an AS-level topology.

This tool reads a topology edge list (.txt or .txt.gz) or a NetworkX GML file
and writes a list of all ASNs whose degree (number of direct neighbours) is
greater than or equal to the value given by --min-degree. In the context of
AS-level Internet topology, high-degree nodes are transit providers, Internet
exchange points, and large content networks — commonly referred to as tier-1 or
tier-2 operators.

For .txt/.txt.gz input, degrees are computed in a single pass over the edge
list — no GML conversion required. GML input is also accepted for cases where
a graph file already exists.

Without --wide, the output is a plain list with one ASN per line, sorted
numerically. With --wide, the output has two columns (ASN and degree), sorted
by degree in descending order, making it easy to identify the most connected
ASNs at a glance. The output file can be used as input to other tools or
processed directly with standard Unix utilities.
"""

import gzip
import sys
import time
from collections import defaultdict
from pathlib import Path

import networkx as nx
import typer
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))
from lib import is_gzip

app = typer.Typer()
console = Console()


@app.command(help=__doc__)
def main(
    input: Path = typer.Option(..., "--input", "-i", help="Topology edge list (.txt or .txt.gz) or GML file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (default: input stem + -hubs.txt)"),
    min_degree: int = typer.Option(..., "--min-degree", "-d", help="Minimum degree (inclusive)"),
    wide: bool = typer.Option(False, "--wide", help="Add degree column; sort by degree descending"),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        for suffix in (".gml", ".gz", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        output = input.parent / (stem + "-hubs.txt")

    console.print(f"[bold]Reading[/bold] {input}")

    if input.suffix == ".gml":
        G = nx.read_gml(input)
        results = [(int(node), deg) for node, deg in G.degree() if deg >= min_degree]
    else:
        opener = gzip.open if is_gzip(input) else open
        degree: dict[int, int] = defaultdict(int)
        skipped = edge_count = 0
        with opener(input, "rt") as fh:
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
                degree[a] += 1
                degree[b] += 1
                edge_count += 1
                if edge_count % 100_000 == 0:
                    console.print(f"  {edge_count:,} edges read…")
        if skipped:
            console.print(f"  [yellow]Skipped {skipped} malformed lines[/yellow]")
        console.print(f"  {edge_count:,} edges, {len(degree):,} unique ASNs")
        results = [(asn, deg) for asn, deg in degree.items() if deg >= min_degree]

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
