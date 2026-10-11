# Extract Paths

`extract-paths.py` calls `bgpreader` on each MRT file and writes three sidecar files per input — one combined, one IPv4-only, one IPv6-only. A file set is skipped only if all three outputs already exist.

```
uv run extract-paths.py --input-files <glob> [--output-dir <dir>]
```

| Flag | Required | Description |
|---|---|---|
| `--input-files` | yes | Glob pattern matching MRT files (`.gz` or `.bz2`) |
| `--output-dir` | no | Output directory. Default: `./paths` |

---

## Output files

The output filename strips the source extension (`.gz` or `.bz2`) and appends a new suffix:

| Suffix | Contents |
|---|---|
| `.txt.gz` | All paths (combined IPv4 + IPv6) |
| `.v4.txt.gz` | IPv4-only paths |
| `.v6.txt.gz` | IPv6-only paths |

For example: `bview.rrc00.20260101.0000.gz` → `bview.rrc00.20260101.0000.txt.gz`

Address family is detected from the prefix field (column 9 in bgpreader output): a colon (`:`) in the prefix indicates IPv6.

Output files are **gzip-compressed** (`.txt.gz`). `build-topology.py` detects this automatically via magic bytes.

---

## Path cleaning rules

Applied before writing each path:

- **Prepend removal** — consecutive duplicate ASNs are collapsed: `64500 64500 64501` → `64500 64501`
- **AS set truncation** — paths containing AS sets (e.g. `{64500,64501}`) are truncated at that point; edges *before* the set are kept

---

## Justfile

The `process` recipe runs twice — once for `.gz` files (RIS) and once for `.bz2` files (RouteViews):

```bash
just date=20260101 process
```

If no files match a glob, the invocation prints a notice and exits cleanly (not an error).

---

## Examples

```bash
# Process all RIS files for a date
uv run extract-paths.py \
  --input-files "./mrt/20260101/*.gz" \
  --output-dir ./paths/20260101

# Process all RouteViews files for the same date
uv run extract-paths.py \
  --input-files "./mrt/20260101/*.bz2" \
  --output-dir ./paths/20260101
```
