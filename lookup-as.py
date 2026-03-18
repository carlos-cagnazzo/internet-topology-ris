"""
lookup-as.py — Look up AS information from RIPEstat.

For one or more Autonomous System Numbers, queries the RIPEstat Data API
to retrieve:
  - AS holder name
  - Number of currently announced prefixes
  - Date/time the AS was last seen in the global routing table
  - Whether the AS is currently announcing routes

Results are displayed as a rich table. Optionally written to a TSV file.
Batch lookups (--file) run concurrently for speed.
"""

import asyncio
import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help=__doc__)
console = Console()

RIPESTAT_BASE = "https://stat.ripe.net/data"
DEFAULT_CONCURRENCY = 10


@dataclass
class ASInfo:
    """Result of a RIPEstat lookup for a single ASN."""

    asn: str
    name: str | None
    prefix_count: int | None
    last_seen: datetime | None
    is_announced: bool | None
    error: str | None = None


async def fetch_as_info(asn: str, client: httpx.AsyncClient) -> ASInfo:
    """Fetch AS name, prefix count, and last-seen time from RIPEstat.

    Fires three concurrent sub-requests (as-overview, announced-prefixes,
    routing-status) and merges the results. A failed sub-request contributes
    a None value for its fields rather than aborting the whole lookup.

    Args:
        asn:    ASN as a plain string (e.g. '15169').
        client: Shared async HTTP client.

    Returns:
        ASInfo dataclass populated with available data.
    """
    resource = f"AS{asn}"
    urls = {
        "overview":  f"{RIPESTAT_BASE}/as-overview/data.json?resource={resource}",
        "prefixes":  f"{RIPESTAT_BASE}/announced-prefixes/data.json?resource={resource}",
        "routing":   f"{RIPESTAT_BASE}/routing-status/data.json?resource={resource}",
    }

    async def get(key: str) -> dict | None:
        try:
            r = await client.get(urls[key], timeout=30)
            r.raise_for_status()
            body = r.json()
            if body.get("status") != "ok":
                return None
            return body.get("data", {})
        except Exception:
            return None

    overview_data, prefixes_data, routing_data = await asyncio.gather(
        get("overview"), get("prefixes"), get("routing")
    )

    # Name + announced status
    name: str | None = None
    is_announced: bool | None = None
    if overview_data is not None:
        name = overview_data.get("holder") or None
        is_announced = bool(overview_data.get("announced"))

    # Prefix count from currently announced prefixes list
    prefix_count: int | None = None
    if prefixes_data is not None:
        prefixes = prefixes_data.get("prefixes")
        if isinstance(prefixes, list):
            prefix_count = len(prefixes)

    # Last seen timestamp — last_seen is a dict with a "time" key
    last_seen: datetime | None = None
    if routing_data is not None:
        raw_obj = routing_data.get("last_seen")
        if isinstance(raw_obj, dict):
            raw = raw_obj.get("time")
        else:
            raw = raw_obj  # defensive: handle plain string if API changes
        if raw:
            try:
                last_seen = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                pass

    # Surface an error only if all three calls failed
    error: str | None = None
    if overview_data is None and prefixes_data is None and routing_data is None:
        error = "API unavailable"

    return ASInfo(
        asn=asn,
        name=name,
        prefix_count=prefix_count,
        last_seen=last_seen,
        is_announced=is_announced,
        error=error,
    )


async def fetch_all(asns: list[str], concurrency: int) -> list[ASInfo]:
    """Fetch info for all ASNs concurrently, bounded by a semaphore.

    Args:
        asns:        List of ASN strings to look up.
        concurrency: Maximum number of in-flight requests at once.

    Returns:
        List of ASInfo results in the same order as the input.
    """
    sem = asyncio.Semaphore(concurrency)

    async def bounded(asn: str, client: httpx.AsyncClient) -> ASInfo:
        async with sem:
            return await fetch_as_info(asn, client)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        return await asyncio.gather(*(bounded(asn, client) for asn in asns))


def format_last_seen(dt: datetime | None) -> str:
    """Format a last-seen datetime for display.

    Args:
        dt: UTC-aware datetime, or None.

    Returns:
        Human-readable string: ISO date + time, or '—' if unknown.
    """
    if dt is None:
        return "—"
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def build_table(results: list[ASInfo]) -> Table:
    """Build a rich Table from a list of ASInfo results.

    Args:
        results: Lookup results, sorted by ASN before calling.

    Returns:
        Populated Rich Table ready for printing.
    """
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("ASN", style="cyan", no_wrap=True, min_width=8)
    table.add_column("Name", no_wrap=False, min_width=30)
    table.add_column("Prefixes", justify="right", min_width=8)
    table.add_column("Last Seen", no_wrap=True, min_width=16)
    table.add_column("Status", no_wrap=True)

    for info in results:
        if info.error:
            table.add_row(info.asn, f"[red]{info.error}[/red]", "—", "—", "[red]error[/red]")
            continue

        name_str = info.name or "[dim]unknown[/dim]"
        prefix_str = str(info.prefix_count) if info.prefix_count is not None else "—"
        last_seen_str = format_last_seen(info.last_seen)

        if info.is_announced:
            status = "[green]announced[/green]"
        elif info.is_announced is False:
            status = "[yellow]not announced[/yellow]"
        else:
            status = "[dim]unknown[/dim]"

        table.add_row(info.asn, name_str, prefix_str, last_seen_str, status)

    return table


def write_tsv(results: list[ASInfo], path: Path) -> None:
    """Write lookup results to a TSV file.

    Args:
        results: Lookup results.
        path:    Output file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["asn", "name", "prefix_count", "last_seen_utc", "is_announced", "error"])
        for info in results:
            writer.writerow([
                info.asn,
                info.name or "",
                info.prefix_count if info.prefix_count is not None else "",
                info.last_seen.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if info.last_seen else "",
                "" if info.is_announced is None else ("true" if info.is_announced else "false"),
                info.error or "",
            ])


@app.command()
def main(
    asn: str | None = typer.Option(
        None,
        "--asn",
        help="Single ASN to look up (e.g. 15169). Mutually exclusive with --file.",
        metavar="ASN",
    ),
    file: Path | None = typer.Option(
        None,
        "--file",
        help="File containing one ASN per line. Mutually exclusive with --asn.",
        metavar="FILE",
        exists=False,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Write results as TSV to this file in addition to terminal output.",
        metavar="FILE",
    ),
    concurrency: int = typer.Option(
        DEFAULT_CONCURRENCY,
        "--concurrency",
        help="Maximum parallel API requests (batch mode only).",
        show_default=True,
        min=1,
        max=50,
    ),
) -> None:
    """Look up AS name, prefix count, and last-seen time from RIPEstat."""
    start = time.monotonic()

    # Validate mutual exclusion
    if asn is None and file is None:
        console.print("[red]Error:[/red] Provide either --asn or --file.")
        raise typer.Exit(1)
    if asn is not None and file is not None:
        console.print("[red]Error:[/red] --asn and --file are mutually exclusive.")
        raise typer.Exit(1)

    # Build ASN list
    if asn is not None:
        asns = [asn.strip().lstrip("ASas")]
    else:
        if not file.exists():
            console.print(f"[red]Error:[/red] File not found: {file}")
            raise typer.Exit(1)
        raw_lines = file.read_text().splitlines()
        asns = [line.strip().lstrip("ASas") for line in raw_lines if line.strip()]
        if not asns:
            console.print(f"[red]Error:[/red] No ASNs found in {file}")
            raise typer.Exit(1)

    # Validate all tokens are numeric
    invalid = [a for a in asns if not a.isdigit()]
    if invalid:
        console.print(f"[red]Error:[/red] Non-numeric ASN(s): {', '.join(invalid)}")
        raise typer.Exit(1)

    # Deduplicate, preserve order
    seen: set[str] = set()
    unique_asns: list[str] = []
    for a in asns:
        if a not in seen:
            seen.add(a)
            unique_asns.append(a)

    total = len(unique_asns)
    console.print(f"\n[bold]Looking up {total} ASN(s) via RIPEstat[/bold]\n")

    results = asyncio.run(fetch_all(unique_asns, concurrency))
    results.sort(key=lambda r: int(r.asn))

    console.print(build_table(results))

    if output:
        write_tsv(results, output)
        console.print(f"\n  Results written to [green]{output}[/green]")

    # Summary
    announced = sum(1 for r in results if r.is_announced)
    errors = sum(1 for r in results if r.error)
    elapsed = time.monotonic() - start
    parts = [f"{total} ASN(s) looked up", f"{announced} announced"]
    if errors:
        parts.append(f"[red]{errors} error(s)[/red]")
    console.print(f"\n[bold]Done.[/bold] {', '.join(parts)} — {elapsed:.1f}s elapsed")


if __name__ == "__main__":
    app()
