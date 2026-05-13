"""
annotate-topo.py — Enrich an AS-level topology edge list with country and RIR data.

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
import time
from pathlib import Path

import httpx
import typer
from rich.console import Console

app = typer.Typer()
console = Console()

NRO_STATS_URL_LATEST = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats"
NRO_STATS_URL_HISTORICAL = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{date}/nro-delegated-stats"
NRO_CACHE_LATEST = "nro-delegated-stats"
NRO_CACHE_DATED = "nro-delegated-stats-{date}"
NRO_MAX_AGE_SECONDS = 86400

UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# NRO stats
# ---------------------------------------------------------------------------

def fetch_nro_stats(cache_dir: Path, date: str | None) -> Path:
    if date:
        url = NRO_STATS_URL_HISTORICAL.format(date=date)
        cache_path = cache_dir / NRO_CACHE_DATED.format(date=date)
        if cache_path.exists():
            console.print(f"  [dim]NRO stats ({date}) cached — reusing[/dim] {cache_path}")
            return cache_path
    else:
        url = NRO_STATS_URL_LATEST
        cache_path = cache_dir / NRO_CACHE_LATEST
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < NRO_MAX_AGE_SECONDS:
                console.print(f"  [dim]NRO stats cache {age / 3600:.1f}h old — reusing[/dim] {cache_path}")
                return cache_path

    console.print(f"  Downloading NRO delegated stats → [green]{cache_path}[/green]")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=65536):
                fh.write(chunk)
    return cache_path


def load_asn_info(stats_path: Path) -> dict[int, tuple[str, str]]:
    """Parse NRO delegated stats and return {asn: (country_code, rir)} for assigned ASNs."""
    result: dict[int, tuple[str, str]] = {}
    with stats_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            if len(fields) < 7:
                continue
            if fields[1] == "*" or fields[4] == "summary":
                continue
            if fields[2] != "asn":
                continue
            if fields[6] != "assigned":
                continue
            rir = fields[0]
            cc = fields[1]
            try:
                start = int(fields[3])
                count = int(fields[4])
            except ValueError:
                continue
            for asn in range(start, start + count):
                result[asn] = (cc.lower(), rir)
    return result


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
    opener = gzip.open if _is_gzip(input) else open
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


def _is_gzip(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


if __name__ == "__main__":
    app()
