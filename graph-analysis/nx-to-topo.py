"""
nx-to-topo.py — Export a NetworkX GML file back to a two-column topology edge list.

Reads a GML file produced by topo-to-nx.py and writes an AS-level topology
file (ASN1 ASN2 per line, ASN1 < ASN2, sorted numerically by ASN1). ASNs are
always taken from the node 'asn' attribute, so enriched GML files (where node
keys may be holder name strings) are handled correctly.

Optionally filters edges to those where both endpoints have degree >= --min-degree.
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
    output: Path = typer.Option(None, "--output", "-o", help="Output topology file (default: input stem + .txt)"),
    min_degree: int = typer.Option(None, "--min-degree", "-d", help="Only include edges where both endpoints have degree >= N"),
    justify_output: bool = typer.Option(False, "--justify-output", help="Zero-pad ASNs to 8 digits"),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        if stem.endswith(".gml"):
            stem = stem[:-4]
        output = input.parent / (stem + ".txt")

    console.print(f"[bold]Reading[/bold] {input}")
    try:
        G = nx.read_gml(input)
    except Exception as e:
        console.print(f"[red]Error:[/red] could not parse GML file: {e}")
        raise typer.Exit(1)

    # Build ASN lookup from node key → asn attribute
    asn_map: dict = {}
    for node, attrs in G.nodes(data=True):
        if "asn" not in attrs:
            console.print(f"[red]Error:[/red] node '{node}' has no 'asn' attribute")
            raise typer.Exit(1)
        asn_map[node] = int(attrs["asn"])

    console.print(f"  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    # Compute degree in terms of ASNs (needed for filter and reporting)
    degree: dict[int, int] = {asn_map[n]: G.degree(n) for n in G.nodes}

    # Build and optionally filter edge list
    edges = []
    dropped = 0
    for u, v in G.edges():
        a, b = asn_map[u], asn_map[v]
        if a > b:
            a, b = b, a
        if min_degree is not None and (degree[a] < min_degree or degree[b] < min_degree):
            dropped += 1
            continue
        edges.append((a, b))

    edges.sort()

    if min_degree is not None:
        console.print(f"  {len(edges):,} edges kept (degree >= {min_degree}), {dropped:,} dropped")

    fmt = "{:08d}" if justify_output else "{}"

    console.print(f"[bold]Writing[/bold] {output}")
    with open(output, "w") as fh:
        for a, b in edges:
            fh.write(f"{fmt.format(a)} {fmt.format(b)}\n")

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {len(edges):,} edges written, {elapsed:.2f}s")


if __name__ == "__main__":
    app()
