"""
annotate-topology.py — Enrich an AS-level topology edge list with country and RIR data.

Each line of the input topology (two-column ASN edge list) is annotated with
four additional space-separated columns: the ISO 3166-1 alpha-2 country code of
the first ASN, its RIR, the country code of the second ASN, and its RIR. Country
and RIR assignments come from the NRO delegated extended statistics file. ASNs
not present in the NRO file (private, reserved, or unregistered) are annotated
as 'unknown' in both the country and RIR columns.

Example output line:
    6057 3359 uy lacnic us arin

RIR names follow NRO stats terminology: arin, ripencc, apnic, lacnic, afrinic.

The NRO delegated stats file is fetched automatically and cached next to the
input file. Without --date, the latest available file is used and re-fetched if
the cache is older than 24 hours. With --date (YYYYMMDD), the historical snapshot
for that date is used and cached permanently. The sort order of the input file is
preserved in the output.
"""

import gzip
import sys
import time
from pathlib import Path

import typer
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))
from lib import fetch_nro_stats, is_gzip, load_asn_info

app = typer.Typer()
console = Console()

UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@app.command(help=__doc__)
def main(
    input: Path = typer.Option(..., "--input", "-i", help="Topology edge list file (.txt or .txt.gz)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (default: input stem + -annotated.txt)"),
    date: str = typer.Option(None, "--date", help="NRO stats date YYYYMMDD (default: latest)"),
    justify_output: bool = typer.Option(False, "--justify-output", help="Zero-pad ASNs to 8 digits"),
) -> None:
    t0 = time.perf_counter()

    if output is None:
        stem = input.name
        for suffix in (".gz", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        output = input.parent / (stem + "-annotated.txt")

    # Load NRO stats
    console.print("[bold]NRO stats[/bold]")
    stats_path = fetch_nro_stats(input.parent, date)
    console.print(f"  Parsing {stats_path.name}…")
    asn_info = load_asn_info(stats_path)
    console.print(f"  {len(asn_info):,} assigned ASNs loaded")

    # Process topology
    opener = gzip.open if is_gzip(input) else open
    fmt = "{:08d}" if justify_output else "{}"

    total = unknown_edges = skipped = 0

    console.print(f"[bold]Annotating[/bold] {input}")
    console.print(f"[bold]Writing[/bold] {output}")
    with opener(input, "rt") as fh_in, open(output, "w") as fh_out:
        for line in fh_in:
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

            cc_a, rir_a = asn_info.get(a, (UNKNOWN, UNKNOWN))
            cc_b, rir_b = asn_info.get(b, (UNKNOWN, UNKNOWN))

            fh_out.write(f"{fmt.format(a)} {fmt.format(b)} {cc_a} {rir_a} {cc_b} {rir_b}\n")

            total += 1
            if cc_a == UNKNOWN or cc_b == UNKNOWN:
                unknown_edges += 1
            if total % 100_000 == 0:
                console.print(f"  {total:,} edges processed…")

    if skipped:
        console.print(f"  [yellow]Skipped {skipped} malformed lines[/yellow]")

    pct = unknown_edges / total * 100 if total else 0
    console.print(
        f"  [green]{total:,} edges annotated[/green], "
        f"{unknown_edges:,} ({pct:.1f}%) with at least one unknown ASN"
    )

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {elapsed:.2f}s")


if __name__ == "__main__":
    app()
