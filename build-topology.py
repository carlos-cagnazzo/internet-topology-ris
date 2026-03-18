"""
build-topology.py — Build a deduplicated AS-level topology edge list.

Reads AS path files produced by process-mrt.py, extracts all AS-to-AS links,
and writes a sorted, deduplicated undirected edge list to an output file.

Each line of the output contains two space-separated ASNs representing a link:

    13335 15169
    1299 3356
    ...

Links are undirected: (A, B) and (B, A) are the same edge. Paths are expected
to already be clean (no prepending, no AS sets) as produced by process-mrt.py.

Optionally filters edges to include only ASNs that are formally assigned by one
of the five RIRs, using the NRO delegated extended stats file as the source of
truth. The stats file is cached next to the input files and re-downloaded only
if it is more than 24 hours old.

Always writes two sidecar files:
  {stem}-asns.txt  — unique ASNs present in the final topology
  {stem}-paths.txt — unique AS paths seen across all input files

The paths file is built via an external sort to avoid loading millions of paths
into memory simultaneously.
"""

import heapq
import tempfile
import time
from glob import glob
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer(help=__doc__)
console = Console()

NRO_STATS_URL = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats"
NRO_CACHE_FILENAME = "nro-delegated-stats"
NRO_MAX_AGE_SECONDS = 24 * 3600
ASN_FIELD_WIDTH = 8
SORT_CHUNK_LINES = 500_000


def path_sort_key(line: str) -> tuple[int, ...]:
    """Return a fully numeric sort key for an AS path line.

    Converts every ASN token to int so that sorting is numeric across all
    fields, not lexicographic. E.g. '6 22773' sorts before '37 100'.

    Args:
        line: Space-separated AS path string, optionally with a trailing newline.

    Returns:
        Tuple of ints, one per ASN token.
    """
    return tuple(int(x) for x in line.split())


def fmt(asn: str, justify: bool) -> str:
    """Format an ASN string for file output.

    Args:
        asn:     ASN as a plain string (e.g. '6057').
        justify: When True, zero-pad to ASN_FIELD_WIDTH digits (e.g. '00006057').

    Returns:
        Formatted ASN string.
    """
    return asn.zfill(ASN_FIELD_WIDTH) if justify else asn


def fetch_nro_stats(cache_path: Path) -> Path:
    """Return path to a fresh NRO delegated stats file, downloading if needed.

    The file is cached at *cache_path*. If it exists and is less than 24 hours
    old it is returned as-is. Otherwise it is downloaded from the NRO server.

    Args:
        cache_path: Local path where the stats file should be cached.

    Returns:
        Path to the cached file.
    """
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < NRO_MAX_AGE_SECONDS:
            console.print(
                f"  [dim]NRO stats cache is {age / 3600:.1f}h old — reusing[/dim] {cache_path}"
            )
            return cache_path

    console.print(f"  Downloading NRO delegated stats → [green]{cache_path}[/green]")
    with httpx.stream("GET", NRO_STATS_URL, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=65536):
                fh.write(chunk)

    return cache_path


def load_registered_asns(stats_path: Path) -> set[str]:
    """Parse the NRO delegated stats file and return the set of assigned ASNs.

    Only records where type == 'asn' and status == 'assigned' are included.
    Summary lines (where the count field is 'summary') are skipped, as are
    header lines.

    The count field is respected: an entry with start=64496 and count=10 adds
    ASNs 64496 through 64505 inclusive.

    Args:
        stats_path: Path to the local NRO delegated stats file.

    Returns:
        Set of ASN strings for all assigned autonomous systems.
    """
    registered: set[str] = set()
    with stats_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            # Header line starts with a version number (single integer field)
            if len(fields) < 7:
                continue
            # Skip summary lines: field[4] == 'summary' or field[1] == '*'
            if fields[1] == "*" or fields[4] == "summary":
                continue
            if fields[2] != "asn":
                continue
            if fields[6] != "assigned":
                continue
            try:
                start = int(fields[3])
                count = int(fields[4])
            except ValueError:
                continue
            for asn in range(start, start + count):
                registered.add(str(asn))
    return registered


def sort_and_dedup_paths(tmp_path: Path, out_path: Path, justify: bool) -> int:
    """Sort and deduplicate a raw paths temp file, writing formatted output.

    Uses a chunked in-memory sort followed by a heapq.merge k-way merge to
    handle arbitrarily large files without loading all paths into memory at
    once. Deduplication is performed during the merge pass by comparing each
    line to the previously written line (possible because the stream is sorted).
    Sorting is fully numeric across all ASN fields.

    Args:
        tmp_path:  Path to the unsorted, non-deduplicated raw paths temp file.
        out_path:  Path to write the final sorted, unique, formatted paths.
        justify:   Whether to apply zero-padding via fmt().

    Returns:
        Number of unique paths written.
    """
    # Phase 1: read the temp file in chunks, sort each chunk, write to disk
    chunk_paths: list[Path] = []
    try:
        with tmp_path.open() as fh:
            while True:
                chunk = [line.rstrip("\n") for line, _ in
                         zip(fh, range(SORT_CHUNK_LINES)) if line.strip()]
                if not chunk:
                    break
                chunk.sort(key=path_sort_key)
                cf = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".chunk", prefix="paths-chunk-", delete=False
                )
                cf.write("\n".join(chunk) + "\n")
                cf.close()
                chunk_paths.append(Path(cf.name))

        # Phase 2: k-way merge of sorted chunks + deduplicate + write output
        count = 0
        if not chunk_paths:
            out_path.touch()
            return 0

        chunk_handles = [p.open() for p in chunk_paths]
        try:
            with out_path.open("w") as out_fh:
                prev = None
                for line in heapq.merge(*chunk_handles, key=path_sort_key):
                    line = line.rstrip("\n")
                    if not line or line == prev:
                        continue
                    out_fh.write(" ".join(fmt(t, justify) for t in line.split()) + "\n")
                    prev = line
                    count += 1
        finally:
            for fh in chunk_handles:
                fh.close()

    finally:
        for cp in chunk_paths:
            cp.unlink(missing_ok=True)

    return count


@app.command()
def main(
    input_files: str = typer.Option(
        ...,
        "--input",
        help='Glob pattern matching AS path .txt files to process (e.g. "./paths/*.txt").',
        metavar="GLOB",
    ),
    output: Path = typer.Option(
        Path("./topology.txt"),
        "--output",
        help="Output file for the deduplicated edge list.",
        show_default=True,
    ),
    filter_registered: bool = typer.Option(
        False,
        "--filter-registered/--no-filter-registered",
        help=(
            "When enabled, drops any path where any ASN is not formally assigned "
            "according to the NRO delegated extended stats. Unregistered ASNs are "
            "written to a sidecar file next to --output."
        ),
    ),
    justify_output: bool = typer.Option(
        False,
        "--justify-output/--no-justify-output",
        help=(
            f"When enabled, all ASN numbers in every output file are zero-padded to "
            f"{ASN_FIELD_WIDTH} digits (e.g. AS 6057 → {str(6057).zfill(ASN_FIELD_WIDTH)}). "
            "Does not affect terminal output."
        ),
    ),
) -> None:
    """Build a deduplicated undirected AS-level topology edge list from AS path files."""
    start = time.monotonic()

    matches = sorted(glob(input_files))
    if not matches:
        console.print(f"[red]Error:[/red] No files matched: {input_files}")
        raise typer.Exit(1)

    total_files = len(matches)
    console.print(f"\n[bold]Building topology from {total_files} file(s)[/bold]")

    # Load registered ASN filter if requested
    registered_asns: set[str] | None = None
    if filter_registered:
        input_dir = Path(matches[0]).parent
        cache_path = input_dir / NRO_CACHE_FILENAME
        console.print()
        registered_asns = load_registered_asns(fetch_nro_stats(cache_path))
        console.print(f"  [bold]{len(registered_asns):,}[/bold] assigned ASNs loaded from NRO stats\n")
    else:
        console.print()

    edges: set[tuple[str, str]] = set()
    asns: set[str] = set()
    dropped_edges: set[tuple[str, str]] = set()
    dropped_asns: set[str] = set()
    total_paths = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    # Stream accepted paths to a temp file; sort+dedup on disk after the loop
    tmp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="paths-tmp-", delete=False
    )
    tmp_path = Path(tmp_file.name)

    try:
        with progress:
            overall = progress.add_task("Files", total=total_files)
            for txt_path in matches:
                progress.update(overall, description=f"[cyan]{Path(txt_path).name}[/cyan]")
                with open(txt_path) as fh:
                    for line in fh:
                        tokens = line.split()
                        if len(tokens) < 2:
                            continue
                        total_paths += 1
                        # Post-filter: skip path entirely if any ASN is unregistered
                        if registered_asns is not None:
                            if not all(t in registered_asns for t in tokens):
                                for t in tokens:
                                    if t not in registered_asns:
                                        dropped_asns.add(t)
                                for a, b in zip(tokens, tokens[1:]):
                                    dropped_edges.add((a, b) if int(a) < int(b) else (b, a))
                                continue
                        tmp_file.write(" ".join(tokens) + "\n")
                        for a, b in zip(tokens, tokens[1:]):
                            edge = (a, b) if int(a) < int(b) else (b, a)
                            edges.add(edge)
                            asns.add(a)
                            asns.add(b)
                progress.advance(overall)

        tmp_file.close()

        output.parent.mkdir(parents=True, exist_ok=True)

        # Write topology edge list
        console.print(f"  Writing [bold]{len(edges):,}[/bold] edges to [green]{output}[/green] ...")
        with output.open("w") as fh:
            for a, b in sorted(edges, key=lambda e: (int(e[0]), int(e[1]))):
                fh.write(f"{fmt(a, justify_output)} {fmt(b, justify_output)}\n")

        # Write ASN list (always generated)
        asns_path = output.parent / f"{output.stem}-asns{output.suffix}"
        console.print(f"  Writing [bold]{len(asns):,}[/bold] ASNs to [green]{asns_path}[/green] ...")
        with asns_path.open("w") as fh:
            for asn in sorted(asns, key=int):
                fh.write(f"{fmt(asn, justify_output)}\n")

        # Sort and deduplicate paths on disk, then write formatted output
        paths_path = output.parent / f"{output.stem}-paths{output.suffix}"
        console.print(f"  Sorting and deduplicating paths → [green]{paths_path}[/green] ...")
        unique_path_count = sort_and_dedup_paths(tmp_path, paths_path, justify_output)
        console.print(f"  [bold]{unique_path_count:,}[/bold] unique paths written.")

        # Write dropped ASNs sidecar file
        if filter_registered and dropped_asns:
            dropped_path = output.parent / f"{output.stem}-dropped-asns{output.suffix}"
            console.print(
                f"  Writing [bold]{len(dropped_asns):,}[/bold] dropped ASNs to [yellow]{dropped_path}[/yellow] ..."
            )
            with dropped_path.open("w") as fh:
                for asn in sorted(dropped_asns, key=int):
                    fh.write(f"{fmt(asn, justify_output)}\n")

    finally:
        tmp_path.unlink(missing_ok=True)

    elapsed = time.monotonic() - start
    summary = (
        f"\n[bold]Done.[/bold]\n"
        f"  Files processed : {total_files:,}\n"
        f"  AS paths read   : {total_paths:,}\n"
        f"  Unique edges    : {len(edges):,}\n"
        f"  Unique ASNs     : {len(asns):,}\n"
        f"  Unique paths    : {unique_path_count:,}\n"
    )
    if filter_registered:
        summary += (
            f"  Dropped edges   : {len(dropped_edges):,}\n"
            f"  Dropped ASNs    : {len(dropped_asns):,}\n"
        )
    summary += f"  Elapsed         : {elapsed:.1f}s"
    console.print(summary)


if __name__ == "__main__":
    app()
