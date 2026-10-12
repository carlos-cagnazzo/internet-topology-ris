"""
get-routeviews.py — Download RouteViews RIB snapshot (bview) files.

For each requested collector and date, downloads the 00:00 UTC RIB snapshot
from https://archive.routeviews.org/ and saves it under the output directory.
Already-present files are skipped without re-downloading.
"""

import time
from datetime import datetime
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

app = typer.Typer(help=__doc__)
console = Console()

ROUTEVIEWS_BASE = "https://archive.routeviews.org"


def build_url(collector: str, date: str) -> str:
    """Return the canonical URL for a collector's 00:00 UTC RIB snapshot.

    Args:
        collector: RouteViews collector identifier, e.g. 'route-views.amsix'.
        date:      Date string in YYYYMMDD format.

    Returns:
        Full HTTPS URL to the .bz2 RIB file.
    """
    dt = datetime.strptime(date, "%Y%m%d")
    year_month = dt.strftime("%Y.%m")
    filename = f"rib.{date}.0000.bz2"
    return f"{ROUTEVIEWS_BASE}/{collector}/bgpdata/{year_month}/RIBS/{filename}"


def download_file(url: str, dest: Path, progress: Progress) -> bool:
    """Stream a file from *url* to *dest*, showing a rich progress bar.

    Args:
        url:      Remote URL to download.
        dest:     Local path to write to (parent must exist).
        progress: Rich Progress instance to attach the download task to.

    Returns:
        True if the file was downloaded, False if it was skipped.
    """
    if dest.exists():
        console.print(f"  [dim]skip[/dim]  {dest.name} (already exists)")
        return False

    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0)) or None
        task = progress.add_task(f"[cyan]{dest.name}", total=total)

        with dest.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=65536):
                fh.write(chunk)
                progress.update(task, advance=len(chunk))

    progress.remove_task(task)
    return True


@app.command()
def main(
    collectors: str = typer.Option(
        ...,
        "--collectors",
        help=(
            "Comma-separated list of RouteViews collector IDs. "
            "Examples: 'route-views.amsix', 'ix-br2.gru', "
            "'route-views.amsix,ix-br2.gru'."
        ),
        metavar="SPEC",
    ),
    date: str = typer.Option(
        ...,
        "--date",
        help="Date of the 00:00 UTC RIB snapshot to download, in YYYYMMDD format.",
        metavar="YYYYMMDD",
    ),
    output_dir: Path = typer.Option(
        Path("./mrt"),
        "--output-dir",
        help="Directory where downloaded .bz2 files will be stored.",
        show_default=True,
    ),
) -> None:
    """Download RouteViews RIB snapshot files for one or more collectors."""
    start = time.monotonic()

    # Validate date format
    try:
        datetime.strptime(date, "%Y%m%d")
    except ValueError:
        console.print(f"[red]Error:[/red] --date must be in YYYYMMDD format, got '{date}'")
        raise typer.Exit(1)

    collector_list = [c.strip() for c in collectors.split(",") if c.strip()]
    if not collector_list:
        console.print("[red]Error:[/red] --collectors must not be empty")
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    urls = [
        (c, build_url(c, date), output_dir / f"rib.{c}.{date}.0000.bz2")
        for c in collector_list
    ]
    total = len(urls)

    console.print(f"\n[bold]Downloading {total} RIB file(s) for {date}[/bold]\n")

    downloaded = 0
    skipped = 0
    failed = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    with progress:
        for idx, (collector, url, dest) in enumerate(urls, 1):
            console.print(f"[{idx}/{total}] [bold]{collector}[/bold]  {url}")
            try:
                did_download = download_file(url, dest, progress)
                if did_download:
                    downloaded += 1
                    console.print(f"  [green]done[/green]   {dest}")
                else:
                    skipped += 1
            except httpx.HTTPStatusError as exc:
                console.print(f"  [red]error[/red]  HTTP {exc.response.status_code}")
                failed += 1
            except httpx.RequestError as exc:
                console.print(f"  [red]error[/red]  {exc}")
                failed += 1

    elapsed = time.monotonic() - start
    failed_str = f", [red]{failed} failed[/red]" if failed else ""
    console.print(
        f"\n[bold]Done.[/bold] {downloaded} downloaded, {skipped} skipped{failed_str}"
        f" — {elapsed:.1f}s elapsed"
    )


if __name__ == "__main__":
    app()
