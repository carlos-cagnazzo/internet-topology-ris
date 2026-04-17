"""
topo-to-nx.py — Import an AS-level topology edge list into a NetworkX GML file.

Reads a two-column topology file (AS1 AS2 per line, space-separated) as
produced by build-topology.py and writes an undirected NetworkX graph in GML
format. Zero-padded ASNs are normalised to plain integers. Each node carries
an 'asn' integer attribute and a 'label' string attribute (plain ASN, no
padding).
"""

import gzip
import time
from pathlib import Path

import networkx as nx
import typer
from rich.console import Console

app = typer.Typer(help=__doc__)
console = Console()


@app.command()
def main(
    input: Path = typer.Option(..., "--input", "-i", help="Topology edge list file (.txt or .txt.gz)"),
    output: Path = typer.Option(None, "--output", "-o", help="GML output path (default: input stem + .gml)"),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        for suffix in (".gz", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        output = input.parent / (stem + ".gml")

    opener = gzip.open if input.suffix == ".gz" or _is_gzip(input) else open

    G = nx.Graph()
    skipped = 0
    edge_count = 0

    console.print(f"[bold]Reading[/bold] {input}")
    with opener(input, "rt") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 2:
                skipped += 1
                continue
            a, b = int(parts[0]), int(parts[1])
            for asn in (a, b):
                if asn not in G:
                    G.add_node(asn, asn=asn, label=str(asn))
            G.add_edge(a, b)
            edge_count += 1
            if edge_count % 100_000 == 0:
                console.print(f"  {edge_count:,} edges read…")

    if skipped:
        console.print(f"[yellow]Skipped {skipped} malformed lines[/yellow]")

    console.print(f"[bold]Writing[/bold] {output}")
    nx.write_gml(G, output)

    elapsed = time.perf_counter() - t0
    console.print(
        f"[green]Done[/green] — {G.number_of_nodes():,} nodes, "
        f"{G.number_of_edges():,} edges, {elapsed:.2f}s"
    )


def _is_gzip(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


if __name__ == "__main__":
    app()
