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

The output filename is the **full input filename** (including the `.gz`/`.bz2` extension) with an additional suffix appended:

| Suffix | Contents |
|---|---|
| `.gz.txt` / `.bz2.txt` | All paths (combined IPv4 + IPv6) |
| `.gz.v4.txt` / `.bz2.v4.txt` | IPv4-only paths |
| `.gz.v6.txt` / `.bz2.v6.txt` | IPv6-only paths |

Address family is detected from the prefix field (column 9 in bgpreader output): a colon (`:`) in the prefix indicates IPv6.

Output files are **gzip-compressed** despite the `.txt` extension. `build-topology.py` detects this automatically via magic bytes.

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
