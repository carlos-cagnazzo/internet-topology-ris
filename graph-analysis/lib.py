"""
lib.py — Shared helpers for graph-analysis tools.

Provides three utilities used by multiple tools in this directory:
  is_gzip()         — detect gzip-compressed files by magic bytes
  fetch_nro_stats() — download/cache the NRO delegated stats file
  load_asn_info()   — parse NRO stats into {asn: (country_code, rir)}

Import from any graph-analysis script with:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from lib import is_gzip, fetch_nro_stats, load_asn_info
"""

import time
from pathlib import Path

import httpx
from rich.console import Console

console = Console()

NRO_STATS_URL_LATEST = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats"
NRO_STATS_URL_HISTORICAL = "https://ftp.ripe.net/pub/stats/ripencc/nro-stats/{date}/nro-delegated-stats"
NRO_CACHE_LATEST = "nro-delegated-stats"
NRO_CACHE_DATED = "nro-delegated-stats-{date}"
NRO_MAX_AGE_SECONDS = 86400


def is_gzip(path: Path) -> bool:
    """Return True if path starts with the gzip magic bytes."""
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def fetch_nro_stats(cache_dir: Path, date: str | None) -> Path:
    """Download and cache the NRO delegated stats file, return the local path.

    With date=None, fetches the latest file and re-downloads if older than
    24 hours. With a YYYYMMDD date string, fetches the historical snapshot and
    caches permanently (historical files never change).
    """
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
    """Parse NRO delegated stats and return {asn: (cc, rir)} for assigned ASNs.

    cc is a lowercase ISO 3166-1 alpha-2 country code (e.g. 'uy', 'us').
    rir is the RIR name as used in the NRO file (e.g. 'lacnic', 'arin',
    'ripencc', 'apnic', 'afrinic').
    Only records with status 'assigned' are included.
    """
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
            cc = fields[1].lower()
            try:
                start = int(fields[3])
                count = int(fields[4])
            except ValueError:
                continue
            for asn in range(start, start + count):
                result[asn] = (cc, rir)
    return result
