# eda — Exploratory Data Analysis

Jupyter notebooks for exploring and visualising the AS-level topology data produced by the main pipeline.

## Setup

Dependencies are managed by the root `uv` project. No separate setup needed.

```bash
# Start JupyterLab from the repo root (listens on Tailscale interface)
just lab
```

This binds JupyterLab to the Tailscale address (`100.115.131.82`) so it is reachable remotely over the tailnet but not exposed on other interfaces. The server URL is printed on startup — open it in your browser. Notebooks default to the `eda/` directory.

## Data inputs

Notebooks in this directory consume files produced by the pipeline and the `graph-analysis/` tools:

| File | Description |
|---|---|
| `output/<date>/topology.txt` | Full AS-level edge list (`ASN1 ASN2`) |
| `output/<date>/topology-asns.txt` | Sorted list of all ASNs in the topology |
| `output/<date>/topology-paths.txt` | Deduplicated AS paths |
| `output/<date>/topology-core.txt` | Degree-filtered edge list (from `core.py`) |
| `output/<date>/topology.gml` | NetworkX GML graph (from `topo-to-nx.py`) |

## Dependencies

Installed in the root `uv` project:

- **jupyterlab** — notebook environment
- **ipykernel** — Python kernel for Jupyter
- **pandas** — tabular data manipulation
- **matplotlib** — plotting
- **seaborn** — statistical visualisation
- **networkx** — graph analysis (shared with pipeline tools)

## Notebooks

<!-- Add a one-line description for each notebook as you create it -->
