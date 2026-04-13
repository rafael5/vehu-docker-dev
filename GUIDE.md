# vista-fm-browser — User Guide

## What it does

`vista-fm-browser` lets you explore all FileMan data in a VistA server instance.
It connects to the VEHU Docker container (the WorldVistA Electronic Health Universe demo),
reads the YottaDB globals directly, and gives you a browsable view of:

- **The data dictionary** — every FileMan file (table) and its fields
- **Record data** — the actual patient, drug, order, etc. records
- **Exports** — download any file as CSV or JSON

## Quick start

### 1. Start the VEHU container

```bash
cd ~/projects/vista-fm-browser
docker-compose up -d
```

This starts a VistA/YottaDB server on your machine. First pull is large (~2 GB).

### 2. Set up the container (first time only)

```bash
bash scripts/setup-container.sh
```

Installs Python, the yottadb connector, and project dependencies inside the container.
Safe to run again — it's idempotent.

### 3. Open in VSCode dev container

1. Open `~/projects/vista-fm-browser` in VSCode
2. Command palette → **"Reopen in Container"**
3. VSCode attaches to the running `vehu` container

### 4. Activate YottaDB environment

Inside the container terminal:

```bash
source /etc/yottadb/env
```

This sets the required environment variables (`ydb_gbldir`, `ydb_routines`, etc.)
that tell the YottaDB connector where the VistA data lives.

### 5. Use the CLI

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
    cli.py              fm-browser CLI (Click)
    web/app.py          Flask web UI

tests/
    conftest.py         YdbFake + fixture data (FAKE_DD, FAKE_PATIENT_GLOBAL)
    test_*.py           one file per source module

docker-compose.yml      VEHU container definition
scripts/setup-container.sh  idempotent container setup
.devcontainer/          VSCode dev container config
```

---

## Troubleshooting

### `ImportError: No module named 'yottadb'`
Expected on the host. The yottadb connector only works inside the VEHU container
where the YottaDB C library is installed. Run inside the container.

### `ydb_gbldir not set` or similar YDB errors
Run `source /etc/yottadb/env` inside the container before using fm-browser.

### Container won't start
```bash
docker-compose logs vehu
docker-compose down && docker-compose up -d
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
