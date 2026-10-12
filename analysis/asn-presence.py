"""
asn-presence.py — Build a day-by-day ASN presence matrix.

Reads all unique-asns-YYYYMMDD.txt files matching --input glob(s) and writes a
presence matrix: one row per ASN, one column per date, space-separated, values
0 or 1. Missing days in the input produce no column — gaps appear as absent
columns rather than columns of zeros.

The first line is a header: ASN followed by dates in ascending order. ASNs are
zero-padded to 8 digits, consistent with the source files.

Load in pandas:
    df = pd.read_csv("asn-presence.txt", sep=r"\\s+", index_col=0, dtype=int)

Inspect with shell tools:
    grep 00006057 asn-presence.txt
    awk 'NR==1 || $5==1' asn-presence.txt   # ASNs present on the 4th date
    awk '{sum=0; for(i=2;i<=NF;i++) sum+=$i; print sum, $1}' asn-presence.txt | sort -rn | head
"""

import re
import time
from glob import glob
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer()
console = Console()

DATE_RE = re.compile(r"unique-asns-(\d{8})\.txt$")


@app.command(help=__doc__)
def main(
    input_patterns: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        help="Glob pattern matching unique-asns-YYYYMMDD.txt files. Repeat to include multiple patterns.",
        metavar="GLOB",
    ),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (default: directory of first matched file / asn-presence.txt)"),
) -> None:
    t0 = time.perf_counter()

    matched = sorted({p for pattern in input_patterns for p in glob(pattern)})
    if not matched:
        console.print(f"[red]No files matched: {', '.join(input_patterns)}[/red]")
        raise typer.Exit(1)

    if output is None:
        output = Path(matched[0]).parent / "asn-presence.txt"

    files: list[tuple[str, Path]] = []
    for p in matched:
        m = DATE_RE.search(Path(p).name)
        if m:
            files.append((m.group(1), Path(p)))
        else:
            console.print(f"[yellow]Skipping {p} — filename does not match unique-asns-YYYYMMDD.txt[/yellow]")
    files.sort(key=lambda x: x[0])

    if not files:
        console.print("[red]No files with a recognisable unique-asns-YYYYMMDD.txt name found.[/red]")
        raise typer.Exit(1)

    dates = [d for d, _ in files]
    console.print(f"Found [bold]{len(files)}[/bold] files: {dates[0]} → {dates[-1]}")

    day_sets: list[set[int]] = []
    for date, path in files:
        asns: set[int] = set()
        with open(path) as fh:
            for line in fh:
                s = line.strip()
                if s:
                    try:
                        asns.add(int(s))
                    except ValueError:
                        pass
        day_sets.append(asns)
        console.print(f"  {date}: {len(asns):,} ASNs")

    all_asns = sorted(set().union(*day_sets))
    console.print(f"[bold]{len(all_asns):,}[/bold] unique ASNs across all days")

    console.print(f"[bold]Writing[/bold] {output}")
    with open(output, "w") as fh:
        fh.write("ASN " + " ".join(dates) + "\n")
        for asn in all_asns:
            presence = " ".join("1" if asn in day_set else "0" for day_set in day_sets)
            fh.write(f"{asn:08d} {presence}\n")

    elapsed = time.perf_counter() - t0
    console.print(f"[green]Done[/green] — {elapsed:.2f}s")


if __name__ == "__main__":
    app()
