"""
get-ris-day.py — Download and process a full day of RIS data per collector.

For each requested collector, downloads the 00:00 UTC bview (full table) and
all 288 five-minute update files for the given date. AS paths are extracted
from the bview (all RIB entries) and from every update announcement (withdrawals
are ignored). The combined result is written to a single path file per
collector.

Output files are named bview.<collector>.<date>.full.gz.txt to distinguish
them from the per-snapshot files produced by get-mrt.py + process-mrt.py.
Both can coexist in the same paths directory; build-topology.py will include
both if present.
"""

import asyncio
import gzip
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

app = typer.Typer(help=__doc__)
console = Console()

RIS_BASE = "https://data.ris.ripe.net"
RANGE_RE = re.compile(r"^rrc(\d+)-rrc(\d+)$")
AS_PATH_FIELD = 11
PREFIX_FIELD = 9
ELEM_TYPE_FIELD = 1
DEFAULT_CONCURRENCY = 20


# ---------------------------------------------------------------------------
# Collector expansion
# ---------------------------------------------------------------------------


def expand_collectors(spec: str) -> list[str]:
    """Expand a collector spec into individual collector IDs.

    Accepts a comma-separated mix of individual IDs and ranges:
      rrc00, rrc00-rrc05, rrc00-rrc05,rrc11,rrc23

    Args:
        spec: Collector specification string.

    Returns:
        Ordered list of collector ID strings.
    """
    collectors: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        m = RANGE_RE.match(part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            for i in range(lo, hi + 1):
                collectors.append(f"rrc{i:02d}")
        elif part:
            collectors.append(part)
    return collectors


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------


def _ym(date: str) -> str:
    return datetime.strptime(date, "%Y%m%d").strftime("%Y.%m")


def bview_url(collector: str, date: str) -> str:
    return f"{RIS_BASE}/{collector}/{_ym(date)}/bview.{date}.0000.gz"


def update_url(collector: str, date: str, hhmm: str) -> str:
    return f"{RIS_BASE}/{collector}/{_ym(date)}/updates.{date}.{hhmm}.gz"


def all_hhmms() -> list[str]:
    """Return all 288 five-minute interval strings for a 24-hour day."""
    return [f"{h:02d}{m:02d}" for h in range(24) for m in range(0, 60, 5)]


# ---------------------------------------------------------------------------
# AS path cleaning (same rules as process-mrt.py)
# ---------------------------------------------------------------------------


def clean_path(raw: str) -> list[str]:
    """Collapse prepended ASNs and truncate at AS sets.

    Args:
        raw: Space-separated AS path string from bgpreader.

    Returns:
        Cleaned list of ASN strings, or empty list if nothing usable remains.
    """
    tokens = raw.split()
    cleaned: list[str] = []
    for token in tokens:
        if token.startswith("{"):
            break
        if not cleaned or token != cleaned[-1]:
            cleaned.append(token)
    return cleaned


# ---------------------------------------------------------------------------
# Bview download (synchronous, streaming with progress bar)
# ---------------------------------------------------------------------------


def download_bview(url: str, dest: Path) -> bool:
    """Stream a bview file to *dest*, showing a progress bar.

    Args:
        url:  Remote URL.
        dest: Local destination path.

    Returns:
        True if the file was downloaded, False if it was already present.
    """
    if dest.exists():
        console.print(f"  [dim]skip[/dim]  {dest.name} (already exists)")
        return False

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
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0)) or None
            task = progress.add_task(f"[cyan]{dest.name}", total=total)
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    fh.write(chunk)
                    progress.update(task, advance=len(chunk))
    return True


# ---------------------------------------------------------------------------
# Update file download (asynchronous, parallel)
# ---------------------------------------------------------------------------


async def _fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
    dest: Path,
    progress: Progress,
    task_id: int,
    counters: dict,
) -> str:
    if dest.exists():
        counters["skipped"] += 1
        progress.advance(task_id)
        return "skip"
    async with sem:
        try:
            async with client.stream("GET", url, follow_redirects=True, timeout=60) as resp:
                if resp.status_code == 404:
                    counters["missing"] += 1
                    progress.advance(task_id)
                    return "missing"
                resp.raise_for_status()
                with dest.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        fh.write(chunk)
            counters["downloaded"] += 1
            progress.advance(task_id)
            return "ok"
        except Exception:
            dest.unlink(missing_ok=True)
            counters["failed"] += 1
            progress.advance(task_id)
            return "error"


async def _download_updates_async(
    collector: str,
    date: str,
    mrt_dir: Path,
    concurrency: int,
) -> tuple[list[Path], dict]:
    hhmms = all_hhmms()
    items = [
        (update_url(collector, date, t), mrt_dir / f"updates.{collector}.{date}.{t}.gz")
        for t in hhmms
    ]
    counters = {"downloaded": 0, "skipped": 0, "failed": 0, "missing": 0}
    sem = asyncio.Semaphore(concurrency)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    with progress:
        task_id = progress.add_task("  Downloading updates", total=len(items))
        async with httpx.AsyncClient() as client:
            coros = [
                _fetch_one(client, sem, url, dest, progress, task_id, counters)
                for url, dest in items
            ]
            results = await asyncio.gather(*coros)

    present = [dest for (_, dest), r in zip(items, results) if r in ("ok", "skip")]
    return present, counters


def download_updates(
    collector: str, date: str, mrt_dir: Path, concurrency: int
) -> tuple[list[Path], dict]:
    return asyncio.run(_download_updates_async(collector, date, mrt_dir, concurrency))


# ---------------------------------------------------------------------------
# bgpreader processing
# ---------------------------------------------------------------------------


def process_bgpreader(
    path: Path, out_fh, v4_fh, v6_fh, elem_type: str
) -> tuple[int, int, int]:
    """Run bgpreader on *path* and write cleaned AS paths to three output file handles.

    Args:
        path:      MRT file to process (bview or update).
        out_fh:    Open file handle for combined output.
        v4_fh:     Open file handle for IPv4-only output.
        v6_fh:     Open file handle for IPv6-only output.
        elem_type: bgpreader element type to keep: 'R' for bview, 'A' for updates.

    Returns:
        Tuple of (total_written, v4_written, v6_written).
    """
    opt_key = "rib-file" if elem_type == "R" else "upd-file"
    cmd = ["bgpreader", "-d", "singlefile", "-o", f"{opt_key}={path}"]
    total = v4 = v6 = 0
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    ) as proc:
        for line in proc.stdout:
            fields = line.rstrip("\n").split("|")
            if len(fields) <= AS_PATH_FIELD:
                continue
            if fields[ELEM_TYPE_FIELD] != elem_type:
                continue
            raw = fields[AS_PATH_FIELD]
            if not raw:
                continue
            tokens = clean_path(raw)
            if len(tokens) < 2:
                continue
            path_line = " ".join(tokens) + "\n"
            out_fh.write(path_line)
            total += 1
            prefix = fields[PREFIX_FIELD] if len(fields) > PREFIX_FIELD else ""
            if ":" in prefix:
                v6_fh.write(path_line)
                v6 += 1
            else:
                v4_fh.write(path_line)
                v4 += 1
    return total, v4, v6


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@app.command()
def main(
    collectors: str = typer.Option(
        ...,
        "--collectors",
        help=(
            "Collector specification. Accepts individual IDs, ranges, and "
            "comma-separated mixes: rrc00, rrc00-rrc05, rrc00-rrc05,rrc11."
        ),
        metavar="SPEC",
    ),
    date: str = typer.Option(
        ...,
        "--date",
        help="Date of the snapshot in YYYYMMDD format.",
        metavar="YYYYMMDD",
    ),
    mrt_dir: Path = typer.Option(
        Path("./mrt"),
        "--mrt-dir",
        help="Root directory for downloaded MRT files (date subdir created automatically).",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("./paths"),
        "--output-dir",
        help="Root directory for output path files (date subdir created automatically).",
        show_default=True,
    ),
    keep: bool = typer.Option(
        False,
        "--keep/--no-keep",
        help="Keep downloaded update files after processing. Bview files are always kept.",
    ),
    concurrency: int = typer.Option(
        DEFAULT_CONCURRENCY,
        "--concurrency",
        help="Maximum number of parallel update file downloads.",
        show_default=True,
    ),
) -> None:
    """Download and process a full day of RIS data (bview + all updates) per collector."""
    start = time.monotonic()

    try:
        datetime.strptime(date, "%Y%m%d")
    except ValueError:
        console.print(f"[red]Error:[/red] --date must be YYYYMMDD, got '{date}'")
        raise typer.Exit(1)

    collector_list = expand_collectors(collectors)
    if not collector_list:
        console.print("[red]Error:[/red] --collectors must not be empty")
        raise typer.Exit(1)

    day_mrt = mrt_dir / date
    day_out = output_dir / date
    day_mrt.mkdir(parents=True, exist_ok=True)
    day_out.mkdir(parents=True, exist_ok=True)

    n = len(collector_list)
    console.print(
        f"\n[bold]Full-day processing for {date}[/bold] — {n} collector(s), "
        f"concurrency={concurrency}\n"
    )

    grand_total_paths = 0
    grand_downloaded = 0
    grand_skipped = 0
    grand_failed = 0
    collectors_done = 0

    for idx, collector in enumerate(collector_list, 1):
        console.print(f"[{idx}/{n}] [bold]{collector}[/bold]")

        out_path = day_out / f"bview.{collector}.{date}.full.gz.txt"
        v4_path = day_out / f"bview.{collector}.{date}.full.gz.v4.txt"
        v6_path = day_out / f"bview.{collector}.{date}.full.gz.v6.txt"
        if out_path.exists() and v4_path.exists() and v6_path.exists():
            console.print(f"  [dim]skip[/dim]  {out_path.name} (already exists)\n")
            collectors_done += 1
            continue

        # --- bview ---
        bv_dest = day_mrt / f"bview.{collector}.{date}.0000.gz"
        console.print(f"  [bold]bview[/bold]  {bview_url(collector, date)}")
        try:
            did = download_bview(bview_url(collector, date), bv_dest)
            if did:
                console.print(f"  [green]done[/green]   {bv_dest.name}")
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            console.print(f"  [red]error[/red]  bview download failed: {exc}")
            grand_failed += 1
            console.print()
            continue

        # --- updates ---
        console.print(f"  [bold]updates[/bold] 288 files ...")
        upd_paths, counters = download_updates(collector, date, day_mrt, concurrency)
        console.print(
            f"  {counters['downloaded']} downloaded, {counters['skipped']} skipped, "
            f"{counters['missing']} missing, {counters['failed']} failed"
        )
        grand_downloaded += counters["downloaded"]
        grand_skipped += counters["skipped"]
        grand_failed += counters["failed"]

        # --- process ---
        console.print(f"  [bold]processing[/bold] → [green]{out_path.name}[/green]")
        collector_paths = 0

        with (
            gzip.open(out_path, "wt", compresslevel=1) as out_fh,
            gzip.open(v4_path, "wt", compresslevel=1) as v4_fh,
            gzip.open(v6_path, "wt", compresslevel=1) as v6_fh,
        ):
            n_bview, n_bview_v4, n_bview_v6 = process_bgpreader(bv_dest, out_fh, v4_fh, v6_fh, "R")
            collector_paths += n_bview
            console.print(
                f"    bview   : {n_bview:,} paths "
                f"([cyan]{n_bview_v4:,}[/cyan] v4, [magenta]{n_bview_v6:,}[/magenta] v6)"
            )

            n_upd = n_upd_v4 = n_upd_v6 = 0
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            )
            with progress:
                task = progress.add_task("    updates ", total=len(upd_paths))
                for upd_path in upd_paths:
                    t, t_v4, t_v6 = process_bgpreader(upd_path, out_fh, v4_fh, v6_fh, "A")
                    n_upd += t
                    n_upd_v4 += t_v4
                    n_upd_v6 += t_v6
                    progress.advance(task)

        collector_paths += n_upd
        console.print(
            f"    updates : {n_upd:,} paths "
            f"([cyan]{n_upd_v4:,}[/cyan] v4, [magenta]{n_upd_v6:,}[/magenta] v6)"
        )
        console.print(f"    total   : {collector_paths:,} paths written")
        grand_total_paths += collector_paths
        collectors_done += 1

        # --- cleanup ---
        if not keep:
            for p in upd_paths:
                p.unlink(missing_ok=True)

        console.print()

    elapsed = time.monotonic() - start
    console.print(
        f"[bold]Done.[/bold]\n"
        f"  Collectors processed : {collectors_done}/{n}\n"
        f"  Update files         : {grand_downloaded} downloaded, "
        f"{grand_skipped} skipped, {grand_failed} failed\n"
        f"  Total paths written  : {grand_total_paths:,}\n"
        f"  Elapsed              : {elapsed:.1f}s"
    )


if __name__ == "__main__":
    app()
