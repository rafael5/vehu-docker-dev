# vista-fm-browser — User Guide

## What it does

`vista-fm-browser` lets you explore all FileMan data in a VistA server instance.
It connects to the VEHU Docker container (`yottadb/octo-vehu` — built nightly by
YottaDB Inc. with the latest YottaDB, Octo, and synthetic patient data),
reads the YottaDB globals directly, and gives you a browsable view of:

- **The data dictionary** — every FileMan file (table) and its fields
- **Record data** — the actual patient, drug, order, etc. records
- **Exports** — download any file as CSV or JSON

## Quick start

### 1. Build and start the VEHU container

```bash
cd ~/projects/vista-fm-browser
docker-compose up -d --build
```

First run pulls the VEHU base image (~2 GB) and builds the dev image with Python 3.12,
all project dependencies, and the YottaDB connector pre-installed. Subsequent starts
use the cached image — no `--build` needed.

> **No manual setup step.** The Dockerfile handles everything that
> `setup-container.sh` used to do.

### 2. Open in VSCode dev container

1. Open this folder in VSCode
2. Command palette → **"Reopen in Container"**
3. VSCode attaches to the running `vehu` container and runs
   `pip install -e .` to register the `fm-browser` entry point

> The YottaDB environment is auto-sourced in every container shell session —
> no manual `source /etc/yottadb/env` needed.

### 3. Use the CLI

```bash
# List all FileMan files
fm-browser files

# List all fields in a file
fm-browser fields 2          # PATIENT file

# Browse record data
fm-browser data 2            # first 20 PATIENT records
fm-browser data 2 --limit 5  # first 5 records

# Export the data dictionary to CSV
fm-browser export-dd ~/data/vista-fm-browser/output/

# Export a file's data to JSON
fm-browser export-file 2 ~/data/vista-fm-browser/output/
```

### 6. Use the web UI

```bash
fm-browser serve
# → http://localhost:5000
```

Browse files, click into fields, page through records. Port 5000 is mapped to
the host — open it in your regular browser.

---

## Understanding FileMan data

### Files and fields

FileMan organizes VistA data into **files** (like database tables). Each file has:
- A **file number** (e.g., `2` = PATIENT, `50` = DRUG, `200` = NEW PERSON)
- A **name** (stored in the data dictionary)
- A set of **fields**, each with a number, label, and datatype

### Datatype codes

| Code | Meaning | Example |
|------|---------|---------|
| F | Free text | patient name |
| N | Numeric | age, count |
| D | Date/time | DOB, order date |
| P | Pointer | links to another file |
| S | Set of codes | YES/NO, M/F |
| M | MUMPS code | computed fields |
| C | Computed | derived values |
| W | Word processing | notes, documents |

### Key file numbers

| Number | File name |
|--------|-----------|
| 2 | PATIENT |
| 44 | HOSPITAL LOCATION |
| 50 | DRUG |
| 100 | ORDER |
| 200 | NEW PERSON |
| 8925 | TIU DOCUMENT |

### How data is stored in YottaDB

FileMan uses global variables (YottaDB's persistent storage):

```
^DD(2, 0)               = "PATIENT^DPT^..."      ← file header
^DD(2, .01, 0)          = "NAME^RF^..."          ← field .01 header
^DPT(1, 0)              = "SMITH,JOHN^1942..."   ← patient IEN=1, zero node
^DPT(1, "C")            = cross-reference data
```

The browser reads `^DD` for structure and the file's global (e.g., `^DPT`) for data.

---

## Development

### Running tests on the host (no container needed)

```bash
cd ~/projects/vista-fm-browser
make install    # first time only
make test       # runs all unit tests using YdbFake
```

Unit tests use `YdbFake` — an in-memory implementation of the same interface
as the real YottaDB connector. No Docker required.

### Running integration tests (inside container)

```bash
# Inside the container terminal:
source /etc/yottadb/env
cd /opt/vista-fm-browser
pytest tests/ -m integration
```

Integration tests hit the real YottaDB globals in the VEHU container.

### TDD workflow

```bash
make watch      # auto-reruns tests on file save
```

Write the test first. Confirm it fails. Implement. Confirm green. Commit.

### Full quality gate

```bash
make check      # lint + mypy + coverage (must pass before push)
make push       # runs check then git push
```

---

## Project layout

```
src/vista_fm_browser/
    connection.py       YdbConnection — wraps yottadb calls; raises ImportError on host
    data_dictionary.py  DataDictionary — reads ^DD global; FileDef, FieldDef
    file_reader.py      FileReader — reads record data from data globals
    exporter.py         Exporter — exports to CSV/JSON
    rpc_broker.py       VistARpcBroker — TCP RPC Broker client (XWB NS mode)
    cli.py              fm-browser CLI (Click)
    web/app.py          Flask web UI

tests/
    conftest.py         YdbFake + fixture data (FAKE_DD, FAKE_PATIENT_GLOBAL)
    test_*.py           one file per source module (unit tests only)
                        integration tests inside each file, @pytest.mark.integration

Dockerfile              Custom dev image (extends worldvista/vehu-interim)
docker-compose.yml      VEHU container definition (uses Dockerfile build)
.devcontainer/          VSCode dev container config
scripts/setup-container.sh  Legacy — superseded by Dockerfile
```

---

## Using the RPC Broker

The RPC Broker client (`VistARpcBroker`) connects to VistA via TCP (port 9430) and
executes VistA Remote Procedure Calls. This is an alternative to direct YottaDB
global access and is the standard way CPRS and other VistA clients communicate.

```python
from vista_fm_browser.rpc_broker import VistARpcBroker

with VistARpcBroker(host="localhost", port=9430) as broker:
    broker.connect(app="FM BROWSER", uci="VAH")
    broker.call("XUS SIGNON SETUP")                    # get intro text
    duz = broker.authenticate("fakedoc1", "1Doc!@#$")  # returns DUZ
    print(f"Authenticated as DUZ={duz}")

    # Get PATIENT file entry IEN=1, field .01 (NAME)
    data = broker.gets_entry_data(file_number=2, ien="1", fields=".01")
    print(data)

    # Call any VistA RPC with literal string parameters
    result = broker.call("XWB GET VARIABLE VALUE", "$ZV")
    print(result)  # YottaDB version string
```

The RPC Broker is available from:
- **Inside the container**: `localhost:9430`
- **From the host**: `localhost:9430` (mapped in docker-compose.yml)

---

## Troubleshooting

### `ImportError: No module named 'yottadb'`
Expected on the host. The yottadb connector only works inside the VEHU container
where the YottaDB C library is installed. Run inside the container.

### `ydb_gbldir not set` or similar YDB errors
The YottaDB env is auto-sourced in bash sessions (via `/etc/bash.bashrc`).
If running a non-interactive script, source the env manually:
```bash
# yottadb/octo-vehu image:
source /usr/local/etc/ydb_env_set
# or: source $ydb_dist/ydb_env_set
# older worldvista/* images:
source /etc/yottadb/env
```

### Container won't start
```bash
docker-compose logs vehu
docker-compose down && docker-compose up -d --build
```

### Python deps missing inside container
The Dockerfile installs deps into `/opt/venv` which is on `PATH`.
If `fm-browser` command is not found, the editable install step may not
have run yet:
```bash
# Inside container:
/opt/venv/bin/pip install -e '/opt/vista-fm-browser[dev]' -q
# Or: make container-install
```

### RPC Broker connection refused
Ensure the VEHU container is started and the broker has had time to initialize
(may take ~10s after container start):
```bash
docker-compose ps           # verify container is running
nc -zv localhost 9430       # test TCP port from host
```

### Port 5000 already in use
```bash
fm-browser serve --port 5001
```

### Tests fail on host
```bash
make test-lf    # rerun only last failures
pytest --pdb    # drop into debugger on first failure
```
