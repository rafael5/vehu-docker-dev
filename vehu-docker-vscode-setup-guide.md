# VEHU Docker + VS Code Setup Guide

## Should each analysis phase be a standalone script?

**Yes.** Standalone scripts are the best format for iterating with Claude:

| | Standalone scripts | Jupyter notebook |
|---|---|---|
| Claude can read & edit | ✓ directly | ✗ JSON cell surgery |
| Claude can run & see output | ✓ `python scripts/phase1.py` | limited |
| Targeted single-line edits | ✓ | ✗ |
| pytest integration | ✓ | ✗ |
| Git diffs are readable | ✓ | ✗ (JSON noise) |
| Interactive inline output | ✗ | ✓ |
| Non-linear exploration | ✗ | ✓ |

**Recommended workflow:**
- `scripts/analysis/phase*.py` — authoritative, runnable, Claude-editable scripts
- `notebooks/fileman_analysis.ipynb` — interactive runner that calls the scripts for exploration

---

## Part 1 — Prerequisites

### 1.1 Install Docker Engine (official method)

Do **not** use `apt install docker.io` or `apt install docker-compose` — those are outdated Ubuntu packages that install Docker 20.x and docker-compose v1, which are incompatible with modern images and the Compose V2 plugin.

Install Docker Engine from Docker's official apt repository:

```bash
# Remove any old/conflicting packages
sudo apt remove docker docker-engine docker.io containerd runc \
    docker-compose docker-compose-plugin docker-compose-v2 2>/dev/null

# Install prerequisites
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker's apt repository
# NOTE: Linux Mint is Ubuntu-based. Map the Mint codename to its Ubuntu base:
#   Mint 21.x → ubuntu jammy   (22.04)
#   Mint 22.x → ubuntu noble   (24.04)
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  noble stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose plugin
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

# Verify
docker --version
docker compose version
```

Expected output:
```
Docker version 27.x.x, ...
Docker Compose version v2.x.x
```

### 1.2 Add your user to the docker group

Without this, every `docker` command requires `sudo`:

```bash
sudo usermod -aG docker $USER
```

**Apply the change** — choose one:

```bash
newgrp docker          # activates in current shell only (no re-login needed)
# -- or --
# log out and log back in (permanent for all shells)
```

Verify:
```bash
groups | grep docker   # should print a line containing "docker"
docker ps              # should work without sudo
```

### 1.3 Enable and start Docker

```bash
sudo systemctl enable docker   # start Docker automatically on boot
sudo systemctl start docker
sudo systemctl status docker   # confirm it is "active (running)"
```

### 1.4 Install VS Code

Download from https://code.visualstudio.com/ and install the `.deb` package:

```bash
sudo dpkg -i code_*.deb
sudo apt install -f   # fix any dependency issues
```

### 1.5 VS Code extensions (install on the host)

Open VS Code → Extensions sidebar (`Ctrl+Shift+X`) → search and install:

| Extension | ID | Purpose |
|---|---|---|
| Dev Containers | `ms-vscode-remote.remote-containers` | Connect to Docker containers |
| Claude Code | `anthropic.claude-code` | Claude AI inside VS Code |
| Docker | `ms-azuretools.vscode-docker` | Container management sidebar |

### 1.6 Start the VEHU container

```bash
cd ~/projects/vehu-docker-dev
docker compose up -d          # note: "docker compose", not "docker-compose"
docker compose ps             # verify vehu container is "running"
```

---

## Part 2 — Connecting VS Code to the Container

The project already has `.devcontainer/devcontainer.json` configured.
VS Code reads it automatically — no manual setup required.

### First connection

1. Open VS Code
2. `File → Open Folder` → select `/home/rafael/projects/vehu-docker-dev`
3. VS Code detects `.devcontainer/` and shows a notification:
   **"Folder contains a Dev Container configuration file. Reopen in Container?"**
   Click **Reopen in Container**

   — or use the Command Palette (`Ctrl+Shift+P`):
   **Dev Containers: Reopen in Container**

4. VS Code attaches to the running `vehu` container. The bottom-left corner
   turns green and shows **Dev Container: VEHU FileMan Browser**

5. The `postAttachCommand` runs automatically:
   ```bash
   /opt/venv/bin/pip install -e '/opt/vista-fm-browser[dev]' -q
   ```
   This registers the `fm-browser` CLI entry point in the container venv.

### Reconnecting later

```
Ctrl+Shift+P → Dev Containers: Reopen in Container
```

The container must be running (`docker compose up -d`) before reconnecting.

---

## Part 3 — Python Interpreter

The container has **two Python environments**. Always use `/opt/venv`:

| Path | What it is | Use |
|---|---|---|
| `/opt/venv/bin/python` | Container venv (pre-built in image) | ✓ **use this** |
| `/opt/vista-fm-browser/.venv/bin/python` | Host-synced venv (root-owned) | ✗ avoid in container |

VS Code is already configured to use `/opt/venv` via `devcontainer.json`:
```json
"python.defaultInterpreterPath": "/opt/venv/bin/python"
```

To verify: bottom-right of VS Code status bar should show **Python 3.12 (/opt/venv/bin/python)**.

If it shows a different path: `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `/opt/venv/bin/python`.

---

## Part 4 — Extensions Auto-Installed in the Container

`devcontainer.json` installs these automatically when VS Code attaches:

| Extension | Purpose |
|---|---|
| Python | Language support, IntelliSense |
| Pylance | Type checking, autocomplete |
| Debugpy | Breakpoint debugger |
| Ruff | Linter + formatter (replaces black/flake8) |
| Mypy | Static type checker |
| AutoDocstring | Docstring scaffolding |
| GitLens | Git blame, history |

Claude Code is a host extension — it tunnels into the container automatically
and has full access to all files and the integrated terminal.

---

## Part 5 — Integrated Terminal

The VS Code terminal (`` Ctrl+` ``) opens a bash shell **inside the container**
with the YottaDB environment and venv already activated (via `/etc/bashrc`).

Verify:
```bash
echo $ydb_gbldir     # should print a .gld path
which python         # should print /opt/venv/bin/python
fm-browser --help    # should show the CLI
```

If the environment is not active:
```bash
source /usr/local/etc/ydb_env_set
export PATH=/opt/venv/bin:$PATH
```

---

## Part 6 — Running Analysis Scripts from VS Code

### Run a script directly

Open any `.py` file → click the **▶ Run Python File** button (top-right),
or right-click → **Run Python File in Terminal**.

### Run from the terminal

```bash
python scripts/analysis/phase1_scope.py
python scripts/analysis/phase2_volume.py
# etc.
```

### Run with arguments

```bash
python scripts/to_treemap.py --mode inventory \
    --input ~/data/vista-fm-browser/output/inventory.json \
    --output ~/data/vista-fm-browser/output/treemap.html
```

### Run tests

```bash
pytest tests/                          # unit tests
pytest tests/ -m integration          # integration tests (needs YDB env)
make test                              # same as unit tests via Makefile
```

---

## Part 7 — Debugger

1. Open a `.py` file
2. Click the gutter (left of line numbers) to set a breakpoint (red dot)
3. `Run → Start Debugging` (F5) or click the **Debug** icon in the sidebar
4. VS Code uses Debugpy (already installed in `/opt/venv`)

For scripts that connect to YottaDB, the debug session runs inside the container
where `$ydb_gbldir` is set, so live YDB reads work inside debugger.

**launch.json** (create `.vscode/launch.json` to pre-configure):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Phase 1 — Scope Survey",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/scripts/analysis/phase1_scope.py",
      "console": "integratedTerminal",
      "env": {}
    },
    {
      "name": "Current File",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal"
    }
  ]
}
```

---

## Part 8 — Jupyter Notebook in VS Code

VS Code can run the notebook **without a separate JupyterLab server**.

1. Open `notebooks/fileman_analysis.ipynb` in VS Code
2. VS Code detects it as a notebook and opens the cell editor
3. Top-right: **Select Kernel** → pick `/opt/venv/bin/python`
4. Run cells with `Shift+Enter` (next cell) or `Ctrl+Enter` (same cell)
5. All matplotlib output renders inline in VS Code

No browser, no token, no port forwarding needed for notebook use.

To start the full JupyterLab web UI (for the browser experience):
```bash
jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
```
Then open `http://localhost:8888` on the host. Port 8888 is mapped in `docker-compose.yml`.

---

## Part 9 — Claude Code Inside the Container

Claude Code in VS Code has full access to the container filesystem and terminal.

### What Claude can do from VS Code

| Action | How |
|---|---|
| Read any file | Direct file access via the container mount |
| Edit scripts | Targeted line edits with full context |
| Run a script and see output | Terminal execution + result capture |
| Iterate on a failing phase | Edit → run → read error → fix → repeat |
| Generate new analysis code | Write new files directly into `scripts/analysis/` |
| Run tests | `pytest tests/` in terminal |

### Effective prompts for analysis work

```
# Run phase 3 and fix whatever error occurs
Run scripts/analysis/phase3_topology.py and fix any errors.

# Iterate on a specific output
The pointer graph in phase3 has too many isolated nodes.
Update the hub threshold from 10 to 20 inbound references.

# Add a new analysis
Add a phase 4b script that finds all SET fields where
the same code letter maps to different labels across packages.
```

### Claude can see output files

After a phase runs, Claude can read the output JSON/CSV:
```
Read ~/data/vista-fm-browser/output/inventory.json
and summarize the top 5 packages by file count.
```

---

## Part 10 — Port Forwarding Reference

All ports are mapped in `docker-compose.yml`:

| Port | Service | URL |
|---|---|---|
| 5000 | Flask web UI (`fm-browser serve`) | http://localhost:5000 |
| 8888 | JupyterLab | http://localhost:8888 |
| 9430 | VistA RPC Broker | — |
| 1338 | Rocto (SQL interface) | psql -h localhost -p 1338 |
| 8001 | VistA HTTP server | http://localhost:8001 |
| 8080 | YottaDB GUI | http://localhost:8080 |

VS Code also shows detected ports in the **Ports** panel (bottom panel tabs).

---

## Part 11 — Recommended Workflow: Claude + VS Code + Container

```
┌─────────────────────────────────────────────────────┐
│  Host: VS Code (Dev Container attached)             │
│  ┌─────────────────────────────────────────────┐   │
│  │  Container: /opt/vista-fm-browser           │   │
│  │  Python: /opt/venv/bin/python               │   │
│  │  YDB: $ydb_gbldir set                       │   │
│  │                                             │   │
│  │  scripts/analysis/phase1_scope.py   ←─────────── Claude edits here
│  │  scripts/analysis/phase2_volume.py  ←─────────── Claude edits here
│  │  ...                                        │   │
│  │  ~/data/vista-fm-browser/output/   ←─────────── Claude reads results
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  Claude Code sidebar ──────────────────────────────→ edits + runs scripts
│  Integrated Terminal ──────────────────────────────→ inside container bash
│  Notebook editor ──────────────────────────────────→ interactive exploration
└─────────────────────────────────────────────────────┘
```

**Day-to-day loop:**

1. `docker compose up -d` (once, on login)
2. VS Code → Reopen in Container
3. Open Claude Code sidebar
4. Ask Claude to run a phase, read the output, and iterate
5. Use the notebook for exploratory visualization
6. `make push` when done (runs tests + pushes)

---

## Quick Reference

```bash
# Container management (on host)
docker compose up -d            # start
docker compose restart vehu     # restart (clears stale processes)
docker compose down             # stop
docker compose ps               # list container status

# Inside container terminal (VS Code integrated terminal)
source /usr/local/etc/ydb_env_set   # if env vars not set
fm-browser files                     # list all FileMan files
fm-browser serve                     # Flask UI at :5000
jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root

# Analysis scripts
python scripts/analysis/phase1_scope.py
python scripts/analysis/phase2_volume.py
python scripts/analysis/phase3_topology.py
python scripts/analysis/phase4_variety.py
python scripts/analysis/phase5_deep_dive.py
python scripts/analysis/phase6_coverage.py
python scripts/analysis/phase7_candidates.py
python scripts/analysis/phase8_report.py

# Tests
make test                        # unit tests
pytest tests/ -m integration    # integration tests (needs YDB)
make check                       # full gate: lint + types + tests
```
