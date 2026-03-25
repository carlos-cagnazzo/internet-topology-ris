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

Always writes two sidecar files (unless --no-paths is set):
  {stem}-asns.txt  — unique ASNs present in the final topology
  {stem}-paths.txt — unique AS paths seen across all input files

Performance features:
  - Each input file's result (edges, ASNs, paths) is cached in a sidecar file
    (.topcache / .topcache.paths) and reused on subsequent runs as long as
    neither the input file nor the NRO stats have changed.
  - Input files are processed in parallel using ProcessPoolExecutor.
  - --no-paths skips the paths sort/merge step entirely for faster runs.
"""

import heapq
import os
import pickle
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from glob import glob
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text


class MofNColumn(ProgressColumn):
    """Progress column showing M/N with thousands separators."""

    def render(self, task: Task) -> Text:
        completed = int(task.completed)
        total = int(task.total) if task.total is not None else None
        if total is not None:
            return Text(f"{completed:,}/{total:,}", style="progress.download")
        return Text(f"{completed:,}", style="progress.download")


app = typer.Typer(help=__doc__)
console = Console()

NRO_STATS_URL_LATEST = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats"
NRO_STATS_URL_HISTORICAL = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{date}/nro-delegated-stats"
NRO_CACHE_FILENAME_LATEST = "nro-delegated-stats"
NRO_CACHE_FILENAME_DATED = "nro-delegated-stats-{date}"
NRO_MAX_AGE_SECONDS = 24 * 3600
ASN_FIELD_WIDTH = 8
SORT_CHUNK_LINES = 500_000

# Per-file cache sidecar extensions
CACHE_VERSION = 1
CACHE_META_EXT = ".topcache"         # pickle: edges, asns, dropped_asns, counts
CACHE_PATHS_EXT = ".topcache.paths"  # sorted+deduped paths (plain, unjustified)


# ---------------------------------------------------------------------------
# Cache data structure
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    version: int
    cache_key: tuple  # (input_mtime, nro_mtime, filter_registered)
    edges: set        # set[tuple[str, str]]
    asns: set         # set[str]
    dropped_asns: set # set[str]
    raw_path_count: int


# ---------------------------------------------------------------------------
# Worker-process globals — populated by _worker_init via ProcessPoolExecutor
# ---------------------------------------------------------------------------

_W_REGISTERED: "set[str] | None" = None
_W_FILTER: bool = False
_W_NRO_MTIME: float = 0.0
_W_NO_PATHS: bool = False


def _worker_init(
    registered_asns: "set[str] | None",
    filter_registered: bool,
    nro_mtime: float,
    no_paths: bool,
) -> None:
    global _W_REGISTERED, _W_FILTER, _W_NRO_MTIME, _W_NO_PATHS
    _W_REGISTERED = registered_asns
    _W_FILTER = filter_registered
    _W_NRO_MTIME = nro_mtime
    _W_NO_PATHS = no_paths


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def path_sort_key(line: str) -> tuple:
    """Return a fully numeric sort key for an AS path line.

    Converts every ASN token to int so that sorting is numeric across all
    fields, not lexicographic.

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


# ---------------------------------------------------------------------------
# NRO delegated stats
# ---------------------------------------------------------------------------


def fetch_nro_stats(cache_dir: Path, date: "str | None") -> Path:
    """Return path to a local NRO delegated stats file, downloading if needed.

    When *date* is provided, fetches the historical snapshot for that date and
    caches it permanently (historical files never change). When *date* is None,
    fetches the latest file and re-downloads if the cache is more than 24 hours
    old.

    Args:
        cache_dir: Directory where the stats file should be cached.
        date:      Snapshot date in YYYYMMDD format, or None for the latest file.

    Returns:
        Path to the cached file.
    """
    if date:
        url = NRO_STATS_URL_HISTORICAL.format(date=date)
        cache_path = cache_dir / NRO_CACHE_FILENAME_DATED.format(date=date)
        if cache_path.exists():
            console.print(f"  [dim]NRO stats ({date}) cached — reusing[/dim] {cache_path}")
            return cache_path
    else:
        url = NRO_STATS_URL_LATEST
        cache_path = cache_dir / NRO_CACHE_FILENAME_LATEST
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < NRO_MAX_AGE_SECONDS:
                console.print(
                    f"  [dim]NRO stats cache is {age / 3600:.1f}h old — reusing[/dim] {cache_path}"
                )
                return cache_path

    console.print(f"  Downloading NRO delegated stats → [green]{cache_path}[/green]")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=65536):
                fh.write(chunk)

    return cache_path


def load_registered_asns(stats_path: Path) -> "set[str]":
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
            if len(fields) < 7:
                continue
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


# ---------------------------------------------------------------------------
# Per-file cache helpers
# ---------------------------------------------------------------------------


def _mk_cache_key(txt_path: Path, nro_mtime: float, filter_registered: bool) -> tuple:
    return (txt_path.stat().st_mtime, nro_mtime, filter_registered)


def _load_cache(
    txt_path: Path,
    nro_mtime: float,
    filter_registered: bool,
    no_paths: bool,
) -> "_CacheEntry | None":
    """Load a valid cache entry for *txt_path*, or return None on any miss."""
    meta_path = txt_path.parent / (txt_path.name + CACHE_META_EXT)
    if not meta_path.exists():
        return None
    try:
        with meta_path.open("rb") as fh:
            entry = pickle.load(fh)
        if not isinstance(entry, _CacheEntry) or entry.version != CACHE_VERSION:
            return None
        if entry.cache_key != _mk_cache_key(txt_path, nro_mtime, filter_registered):
            return None
        if not no_paths:
            paths_path = txt_path.parent / (txt_path.name + CACHE_PATHS_EXT)
            if not paths_path.exists():
                return None
        return entry
    except Exception:
        return None


def _save_cache(txt_path: Path, entry: _CacheEntry) -> None:
    """Write *entry* to the per-file cache sidecar (failures are non-fatal)."""
    meta_path = txt_path.parent / (txt_path.name + CACHE_META_EXT)
    try:
        with meta_path.open("wb") as fh:
            pickle.dump(entry, fh)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sort raw paths to a sorted+deduped per-file cache file
# ---------------------------------------------------------------------------


def _sort_to_cache(tmp_path: Path, cache_paths: Path) -> None:
    """Sort and deduplicate a raw paths temp file, writing to *cache_paths*.

    Uses chunked in-memory sort + heapq.merge so arbitrarily large files are
    handled without loading everything into memory at once. Deduplication is
    done during the merge pass by comparing adjacent lines.

    The output is plain (un-justified) so the same cache can serve runs with
    and without --justify-output. Justification is applied at final merge time.

    Args:
        tmp_path:    Unsorted, non-deduplicated raw paths temp file.
        cache_paths: Destination for the sorted, deduplicated paths.
    """
    chunk_paths: list[Path] = []
    try:
        with tmp_path.open() as fh:
            while True:
                chunk = [
                    line.rstrip("\n")
                    for line, _ in zip(fh, range(SORT_CHUNK_LINES))
                    if line.strip()
                ]
                if not chunk:
                    break
                chunk.sort(key=path_sort_key)
                cf = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".chunk", prefix="bt-chunk-", delete=False
                )
                cf.write("\n".join(chunk) + "\n")
                cf.close()
                chunk_paths.append(Path(cf.name))

        if not chunk_paths:
            cache_paths.touch()
            return

        chunk_handles = [p.open() for p in chunk_paths]
        try:
            with cache_paths.open("w") as out_fh:
                prev = None
                for line in heapq.merge(*chunk_handles, key=path_sort_key):
                    line = line.rstrip("\n")
                    if not line or line == prev:
                        continue
                    out_fh.write(line + "\n")
                    prev = line
        finally:
            for fh in chunk_handles:
                fh.close()
    finally:
        for cp in chunk_paths:
            cp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Worker function — runs inside a ProcessPoolExecutor worker process
# ---------------------------------------------------------------------------


def _process_file(txt_path_str: str) -> dict:
    """Process one AS path file and return accumulated results.

    Checks the per-file cache first; if valid, returns immediately without
    re-reading the input. Otherwise processes the file, builds edges/ASN sets,
    writes the sorted+deduped per-file paths cache, and saves the metadata
    cache.

    Args:
        txt_path_str: String path to the AS path .txt file to process.

    Returns:
        Dict with keys: name, edges, asns, dropped_asns, raw_path_count,
        paths_file (str path or None), from_cache (bool).
    """
    txt_path = Path(txt_path_str)
    no_paths = _W_NO_PATHS

    cached = _load_cache(txt_path, _W_NRO_MTIME, _W_FILTER, no_paths)
    if cached is not None:
        paths_file = (
            None
            if no_paths
            else str(txt_path.parent / (txt_path.name + CACHE_PATHS_EXT))
        )
        return {
            "name": txt_path.name,
            "edges": cached.edges,
            "asns": cached.asns,
            "dropped_asns": cached.dropped_asns,
            "raw_path_count": cached.raw_path_count,
            "paths_file": paths_file,
            "from_cache": True,
        }

    edges: set[tuple[str, str]] = set()
    asns: set[str] = set()
    dropped_asns: set[str] = set()
    raw_path_count = 0

    tmp_fh = None
    tmp_path: "Path | None" = None
    if not no_paths:
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".rawpaths", prefix="bt-", delete=False
        )
        tmp_path = Path(tf.name)
        tmp_fh = tf

    try:
        with txt_path.open() as fh:
            for line in fh:
                tokens = line.split()
                if len(tokens) < 2:
                    continue
                raw_path_count += 1
                if _W_REGISTERED is not None:
                    if not all(t in _W_REGISTERED for t in tokens):
                        for t in tokens:
                            if t not in _W_REGISTERED:
                                dropped_asns.add(t)
                        continue
                if tmp_fh:
                    tmp_fh.write(" ".join(tokens) + "\n")
                for a, b in zip(tokens, tokens[1:]):
                    edge = (a, b) if int(a) < int(b) else (b, a)
                    edges.add(edge)
                    asns.add(a)
                    asns.add(b)

        if tmp_fh:
            tmp_fh.close()
            tmp_fh = None

        paths_file = None
        if not no_paths and tmp_path is not None:
            cache_paths = txt_path.parent / (txt_path.name + CACHE_PATHS_EXT)
            _sort_to_cache(tmp_path, cache_paths)
            paths_file = str(cache_paths)

        _save_cache(
            txt_path,
            _CacheEntry(
                version=CACHE_VERSION,
                cache_key=_mk_cache_key(txt_path, _W_NRO_MTIME, _W_FILTER),
                edges=edges,
                asns=asns,
                dropped_asns=dropped_asns,
                raw_path_count=raw_path_count,
            ),
        )

    finally:
        if tmp_fh:
            tmp_fh.close()
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    return {
        "name": txt_path.name,
        "edges": edges,
        "asns": asns,
        "dropped_asns": dropped_asns,
        "raw_path_count": raw_path_count,
        "paths_file": paths_file,
        "from_cache": False,
    }


# ---------------------------------------------------------------------------
# Final k-way merge of pre-sorted per-file paths
# ---------------------------------------------------------------------------


def _merge_paths(
    paths_files: list[str],
    out_path: Path,
    justify: bool,
    total_hint: int,
) -> int:
    """k-way merge of pre-sorted per-file path files, deduplicating globally.

    Each per-file paths cache is already sorted and intra-file deduplicated.
    This step merges them into one globally sorted, fully deduplicated output,
    applying justification at write time.

    Args:
        paths_files: List of paths to sorted per-file paths cache files.
        out_path:    Destination file for the final merged paths.
        justify:     Whether to zero-pad ASNs in the output.
        total_hint:  Approximate line count for progress bar sizing.

    Returns:
        Number of unique paths written.
    """
    if not paths_files:
        out_path.touch()
        return 0

    handles = [open(p) for p in paths_files]
    count = 0
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    try:
        with progress:
            task = progress.add_task(
                "  Merging & deduplicating paths", total=total_hint
            )
            with out_path.open("w") as out_fh:
                prev = None
                for line in heapq.merge(*handles, key=path_sort_key):
                    line = line.rstrip("\n")
                    progress.advance(task)
                    if not line or line == prev:
                        continue
                    out_fh.write(
                        " ".join(fmt(t, justify) for t in line.split()) + "\n"
                    )
                    prev = line
                    count += 1
    finally:
        for fh in handles:
            fh.close()
    return count


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@app.command()
def main(
    input_files: list[str] = typer.Option(
        ...,
        "--input",
        help='Glob pattern matching AS path .txt files. Repeat to include multiple patterns.',
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
    no_paths: bool = typer.Option(
        False,
        "--no-paths",
        help=(
            "Skip building the paths output file. Speeds up runs where only the "
            "edge list and ASN list are needed."
        ),
    ),
    workers: int = typer.Option(
        0,
        "--workers",
        help="Number of parallel file-processing workers. 0 = use cpu_count.",
        show_default=True,
    ),
    date: "str | None" = typer.Option(
        None,
        "--date",
        help=(
            "Date of the RIB snapshot in YYYYMMDD format. When provided, the "
            "matching historical NRO delegated stats file is used for filtering "
            "instead of the latest. Defaults to latest when omitted."
        ),
        metavar="YYYYMMDD",
    ),
) -> None:
    """Build a deduplicated undirected AS-level topology edge list from AS path files."""
    start = time.monotonic()

    matches = sorted({f for pattern in input_files for f in glob(pattern)})
    if not matches:
        console.print(f"[red]Error:[/red] No files matched: {', '.join(input_files)}")
        raise typer.Exit(1)

    total_files = len(matches)
    n_workers = (workers if workers > 0 else (os.cpu_count() or 4))
    n_workers = min(n_workers, total_files)
    console.print(
        f"\n[bold]Building topology from {total_files} file(s)[/bold]"
        f" — {n_workers} worker(s)"
        + (" [dim](--no-paths)[/dim]" if no_paths else "")
    )

    # Load NRO filter if requested
    registered_asns: "set[str] | None" = None
    nro_mtime = 0.0
    if filter_registered:
        input_dir = Path(matches[0]).parent
        console.print()
        nro_path = fetch_nro_stats(input_dir, date)
        registered_asns = load_registered_asns(nro_path)
        nro_mtime = nro_path.stat().st_mtime
        console.print(
            f"  [bold]{len(registered_asns):,}[/bold] assigned ASNs loaded from NRO stats\n"
        )
    else:
        console.print()

    # Process files in parallel
    all_edges: set[tuple[str, str]] = set()
    all_asns: set[str] = set()
    all_dropped_asns: set[str] = set()
    total_raw = 0
    paths_files: list[str] = []
    cached_count = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        overall = progress.add_task("Files", total=total_files)

        with ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_worker_init,
            initargs=(registered_asns, filter_registered, nro_mtime, no_paths),
        ) as pool:
            futures = {pool.submit(_process_file, p): p for p in matches}
            for future in as_completed(futures):
                result = future.result()
                progress.update(
                    overall,
                    description=f"[cyan]{result['name']}[/cyan]",
                    advance=1,
                )
                all_edges |= result["edges"]
                all_asns |= result["asns"]
                all_dropped_asns |= result["dropped_asns"]
                total_raw += result["raw_path_count"]
                if result["paths_file"]:
                    paths_files.append(result["paths_file"])
                if result["from_cache"]:
                    cached_count += 1

    output.parent.mkdir(parents=True, exist_ok=True)

    # Write edge list
    console.print(
        f"  Writing [bold]{len(all_edges):,}[/bold] edges → [green]{output}[/green] ..."
    )
    with output.open("w") as fh:
        for a, b in sorted(all_edges, key=lambda e: (int(e[0]), int(e[1]))):
            fh.write(f"{fmt(a, justify_output)} {fmt(b, justify_output)}\n")

    # Write ASN list
    asns_path = output.parent / f"{output.stem}-asns{output.suffix}"
    console.print(
        f"  Writing [bold]{len(all_asns):,}[/bold] ASNs → [green]{asns_path}[/green] ..."
    )
    with asns_path.open("w") as fh:
        for asn in sorted(all_asns, key=int):
            fh.write(f"{fmt(asn, justify_output)}\n")

    # Build final paths file (unless --no-paths)
    unique_path_count: "int | None" = None
    if not no_paths:
        paths_path = output.parent / f"{output.stem}-paths{output.suffix}"
        console.print(f"  Merging paths → [green]{paths_path}[/green] ...")
        unique_path_count = _merge_paths(
            paths_files, paths_path, justify_output, total_raw
        )
        console.print(f"  [bold]{unique_path_count:,}[/bold] unique paths written.")

    # Write dropped ASNs sidecar
    if filter_registered and all_dropped_asns:
        dropped_path = output.parent / f"{output.stem}-dropped-asns{output.suffix}"
        console.print(
            f"  Writing [bold]{len(all_dropped_asns):,}[/bold] dropped ASNs"
            f" → [yellow]{dropped_path}[/yellow] ..."
        )
        with dropped_path.open("w") as fh:
            for asn in sorted(all_dropped_asns, key=int):
                fh.write(f"{fmt(asn, justify_output)}\n")

    elapsed = time.monotonic() - start
    summary = (
        f"\n[bold]Done.[/bold]\n"
        f"  Files processed : {total_files:,} ({cached_count:,} from cache)\n"
        f"  AS paths read   : {total_raw:,}\n"
        f"  Unique edges    : {len(all_edges):,}\n"
        f"  Unique ASNs     : {len(all_asns):,}\n"
    )
    if unique_path_count is not None:
        summary += f"  Unique paths    : {unique_path_count:,}\n"
    if filter_registered:
        summary += f"  Dropped ASNs    : {len(all_dropped_asns):,}\n"
    summary += f"  Elapsed         : {elapsed:.1f}s"
    console.print(summary)


if __name__ == "__main__":
    app()
