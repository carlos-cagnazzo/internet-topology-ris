"""
process-mrt.py — Extract AS paths from RIPE RIS MRT RIB snapshot files.

For each .gz MRT file matched by the input glob, invokes bgpreader to parse
the binary data and writes a sidecar .txt file containing one AS path per line
(space-separated ASNs). Already-processed files (whose .txt exists) are skipped.

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


def process_file(mrt_path: Path, txt_path: Path) -> int:
    """Run bgpreader on *mrt_path* and write cleaned AS paths to *txt_path*.

    Args:
        mrt_path: Path to the input .gz MRT RIB file.
        txt_path: Path to the output .txt file to create.

    Returns:
        Number of AS path lines written.
    """
    cmd = [
        "bgpreader",
        "-d", "singlefile",
        "-o", f"rib-file={mrt_path}",
    ]

    written = 0
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as proc:
        with txt_path.open("w") as out:
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
                out.write(" ".join(tokens) + "\n")
                written += 1

    return written


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

    files = [(Path(m), output_dir / (Path(m).name + ".txt")) for m in matches]
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
        for idx, (mrt_path, txt_path) in enumerate(files, 1):
            progress.update(overall, description=f"[cyan]{mrt_path.name}[/cyan]")

            if txt_path.exists():
                console.print(f"  [[dim]{idx}/{total}[/dim]] [dim]skip[/dim]  {mrt_path.name}")
                skipped += 1
                progress.advance(overall)
                continue

            console.print(f"  [[dim]{idx}/{total}[/dim]] [bold]{mrt_path.name}[/bold]")
            written = process_file(mrt_path, txt_path)
            console.print(f"           → {written:,} paths written to [green]{txt_path.name}[/green]")
            processed += 1
            progress.advance(overall)

    elapsed = time.monotonic() - start
    console.print(
        f"\n[bold]Done.[/bold] {processed} processed, {skipped} skipped"
        f" — {elapsed:.1f}s elapsed"
    )


if __name__ == "__main__":
    app()
