# Installation & Dependencies

This page lists every system-level dependency needed to run the pipeline. Python packages are managed automatically by `uv` — you do not install them by hand.

---

## Dependency overview

| Tool | Role | Pre-installed? |
|---|---|---|
| `bgpreader` | Parse MRT/bview files | No — see below |
| `uv` | Python 3.12+ runtime + packages | No |
| `just` | Pipeline task runner | No |
| `bash 4+` | Required for shell scripts | macOS ships bash 3 |
| `python3` | Date math in dispatch/status scripts | Usually yes |
| `tmux` | Fleet dispatch (background sessions) | Often yes on Linux |
| `rsync` | Path file collection across fleet | Usually yes |
| `ssh` (key-based) | Fleet access — no password prompts | Setup required |

---

## macOS

### Homebrew

All dependencies are available via [Homebrew](https://brew.sh).

```bash
brew install bgpstream uv just bash tmux
```

!!! warning "bash 4+ is required"
    macOS ships with bash 3.2 (GPL2 license restriction). `collect.sh` and `dispatch.sh` use `mapfile` and `export -f`, which require bash 4+. After installing:
    ```bash
    # Verify the new bash is on PATH (Homebrew installs to /opt/homebrew/bin or /usr/local/bin)
    bash --version          # should show 5.x
    which bash              # /opt/homebrew/bin/bash
    ```
    The scripts use `#!/usr/bin/env bash`, which will find the Homebrew bash if it is earlier on `PATH` than `/bin/bash`. If it isn't, add `/opt/homebrew/bin` to the front of `PATH` in your shell profile.

---

## Linux

=== "Homebrew on Linux"

    [Homebrew runs on Linux](https://docs.brew.sh/Homebrew-on-Linux) and is the simplest path:

    ```bash
    # Install Homebrew if you haven't already
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    brew install bgpstream uv just tmux
    ```

=== "Ubuntu / Debian + uv"

    **bgpstream** has no official apt package — build from source:

    ```bash
    # Build dependencies
    sudo apt install -y build-essential libbz2-dev zlib1g-dev \
        libcurl4-openssl-dev liblzma-dev automake autoconf libtool

    # libbgpstream (provides bgpreader)
    git clone https://github.com/CAIDA/libbgpstream.git
    cd libbgpstream
    ./autogen.sh
    ./configure
    make -j$(nproc)
    sudo make install
    sudo ldconfig
    cd ..

    # Verify
    bgpreader --help
    ```

    **uv** (Python manager):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    **just** (task runner):
    ```bash
    curl --proto '=https' --tlsv1.2 -sSf \
        https://just.systems/install.sh | bash -s -- --to ~/.local/bin
    ```

    **tmux** (fleet dispatch):
    ```bash
    sudo apt install -y tmux
    ```

=== "Fedora / RHEL"

    ```bash
    # Build dependencies for bgpstream
    sudo dnf install -y gcc gcc-c++ make automake autoconf libtool \
        bzip2-devel zlib-devel libcurl-devel xz-devel

    # bgpstream from source (same as Ubuntu instructions above)

    # uv
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # just
    curl --proto '=https' --tlsv1.2 -sSf \
        https://just.systems/install.sh | bash -s -- --to ~/.local/bin

    # tmux
    sudo dnf install -y tmux
    ```

---

## Python packages

Once `uv` is installed, it manages Python 3.12 and all package dependencies automatically. No `pip install` needed:

```bash
# From the repo root — installs into .venv automatically on first run
uv run get-mrt.py --help
```

All scripts are invoked as `uv run <script>` — this is intentional and handles the venv transparently.

---

## Fleet: SSH key setup

The fleet dispatch, status, and collect scripts connect to remote machines via SSH without passwords. Set up key-based auth from the central machine to every node:

```bash
# Generate a key if you don't have one
ssh-keygen -t ed25519

# Copy to each fleet node
ssh-copy-id carlos@gauss.xt6labs.io
ssh-copy-id carlos@node2.example.com

# Verify (should not ask for a password)
ssh carlos@gauss.xt6labs.io "echo ok"
```

`StrictHostKeyChecking=no` is set in the SSH options used by the scripts, so new hosts are accepted automatically. If you prefer explicit host verification, pre-populate `~/.ssh/known_hosts` using `ssh-keyscan`:

```bash
ssh-keyscan gauss.xt6labs.io >> ~/.ssh/known_hosts
```

---

## Verify the installation

```bash
bgpreader --help          # bgpstream — should print usage
uv run get-mrt.py --help  # Python toolchain
just --list               # task runner
bash --version            # must be 4.x or 5.x
tmux -V                   # fleet dispatch
```
