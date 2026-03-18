"""
process-mrt.py — Extract AS paths from RIPE RIS MRT RIB snapshot files.

For each .gz MRT file matched by the input glob, invokes bgpreader to parse
the binary data and writes three sidecar files per input:

  <name>.gz.txt     — all paths (combined)
  <name>.gz.v4.txt  — IPv4-only paths (prefix contains no ':')
  <name>.gz.v6.txt  — IPv6-only paths (prefix contains ':')

A file set is skipped if all three output files already exist.

AS path cleaning applied before writing:
  - Consecutive duplicate ASNs (BGP prepending) are collapsed.
  - Paths containing AS sets (e.g. {64500,64501}) are truncated at the set;
    edges before it are kept, the set and everything after are discarded.
"""

import subprocess
import time
from glob import glob
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer(help=__doc__)
console = Console()

AS_PATH_FIELD = 11
PREFIX_FIELD = 9
ELEM_TYPE_FIELD = 1


def clean_path(raw: str) -> list[str]:
    """Parse and clean a raw AS path string from bgpreader output.

    Applies two transformations:
      1. Collapses consecutive duplicate ASNs (removes BGP prepending).
      2. Truncates at the first AS set token (any token starting with '{').

    Args:
        raw: Space-separated AS path string as output by bgpreader.

    Returns:
        List of ASN strings after cleaning. Empty list if nothing remains.
    """
    tokens = raw.split()
    cleaned: list[str] = []
    for token in tokens:
        if token.startswith("{"):
            break  # AS set — truncate here
        if not cleaned or token != cleaned[-1]:
            cleaned.append(token)
    return cleaned


def process_file(
    mrt_path: Path,
    txt_path: Path,
    v4_path: Path,
    v6_path: Path,
) -> tuple[int, int, int]:
    """Run bgpreader on *mrt_path* and write cleaned AS paths to three output files.

    Each path is written to the combined file and to the address-family-specific
    file determined by the prefix field: prefixes containing ':' are IPv6,
    all others are IPv4.

    Args:
        mrt_path: Path to the input .gz MRT RIB file.
        txt_path: Path to the combined output .txt file.
        v4_path:  Path to the IPv4-only output .v4.txt file.
        v6_path:  Path to the IPv6-only output .v6.txt file.

    Returns:
        Tuple of (total_written, v4_written, v6_written).
    """
    cmd = [
        "bgpreader",
        "-d", "singlefile",
        "-o", f"rib-file={mrt_path}",
    ]

    total = v4 = v6 = 0
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as proc:
        with txt_path.open("w") as out_all, v4_path.open("w") as out_v4, v6_path.open("w") as out_v6:
            for line in proc.stdout:
                fields = line.rstrip("\n").split("|")
                if len(fields) <= AS_PATH_FIELD:
                    continue
                if fields[ELEM_TYPE_FIELD] != "R":
                    continue
                raw_path = fields[AS_PATH_FIELD]
                if not raw_path:
                    continue
                tokens = clean_path(raw_path)
                if len(tokens) < 2:
                    continue
                path_line = " ".join(tokens) + "\n"
                out_all.write(path_line)
                total += 1
                prefix = fields[PREFIX_FIELD] if len(fields) > PREFIX_FIELD else ""
                if ":" in prefix:
                    out_v6.write(path_line)
                    v6 += 1
                else:
                    out_v4.write(path_line)
                    v4 += 1

    return total, v4, v6


@app.command()
def main(
    input_files: str = typer.Option(
        ...,
        "--input-files",
        help='Glob pattern matching MRT .gz files to process (e.g. "./mrt/*.gz").',
        metavar="GLOB",
    ),
    output_dir: Path = typer.Option(
        Path("./paths"),
        "--output-dir",
        help="Directory where extracted AS path .txt files will be written.",
        show_default=True,
    ),
) -> None:
    """Extract AS paths from MRT RIB snapshot files using bgpreader."""
    start = time.monotonic()

    matches = sorted(glob(input_files))
    if not matches:
        console.print(f"[red]Error:[/red] No files matched: {input_files}")
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    files = [
        (
            Path(m),
            output_dir / (Path(m).name + ".txt"),
            output_dir / (Path(m).name + ".v4.txt"),
            output_dir / (Path(m).name + ".v6.txt"),
        )
        for m in matches
    ]
    total = len(files)

    console.print(f"\n[bold]Processing {total} MRT file(s)[/bold]\n")

    processed = 0
    skipped = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        overall = progress.add_task("Files", total=total)
        for idx, (mrt_path, txt_path, v4_path, v6_path) in enumerate(files, 1):
            progress.update(overall, description=f"[cyan]{mrt_path.name}[/cyan]")

            if txt_path.exists() and v4_path.exists() and v6_path.exists():
                console.print(f"  [[dim]{idx}/{total}[/dim]] [dim]skip[/dim]  {mrt_path.name}")
                skipped += 1
                progress.advance(overall)
                continue

            console.print(f"  [[dim]{idx}/{total}[/dim]] [bold]{mrt_path.name}[/bold]")
            total_written, v4_written, v6_written = process_file(mrt_path, txt_path, v4_path, v6_path)
            console.print(
                f"           → {total_written:,} paths "
                f"([cyan]{v4_written:,}[/cyan] v4, [magenta]{v6_written:,}[/magenta] v6) "
                f"written to [green]{txt_path.name}[/green]"
            )
            processed += 1
            progress.advance(overall)

    elapsed = time.monotonic() - start
    console.print(
        f"\n[bold]Done.[/bold] {processed} processed, {skipped} skipped"
        f" — {elapsed:.1f}s elapsed"
    )


if __name__ == "__main__":
    app()
