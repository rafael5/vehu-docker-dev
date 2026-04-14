# Claude Project Context — vista-fm-browser

## What this project is
A FileMan browser for inspecting and analyzing all FileMan data in a VistA server instance.
Connects to the VEHU Docker container (yottadb/octo-vehu — built nightly by YottaDB Inc.) running YottaDB.
Provides both a CLI (`fm-browser`) and a web UI (Flask) for browsing the FileMan data dictionary
and record data. Exports to JSON/CSV. Entry point for VA VistA data analysis.

## Skills to load at session start
- `~/claude/skills/vista-fileman/` — FileMan globals, data dictionary layout, field types
- `~/claude/skills/vista-system/` — VistA package names, namespaces, architecture
- `~/claude/skills/ydb-library/` — ydb shell tools and YottaDB library modules

## Data paths
```
~/data/vista-fm-browser/input/    # downloaded VistA globals, raw exports
~/data/vista-fm-browser/output/   # exported CSV/JSON files
~/data/vista-fm-browser/db/       # local SQLite cache (future)
```

## Two execution environments

### Host machine (unit tests only)
- `yottadb` package NOT available — importing it raises `ImportError`
- Run: `make test` (uses YdbFake, no container needed)
- All unit tests must pass here

### VEHU container (integration tests + live usage)
- YottaDB C library present; `source /etc/bashrc` activates full env
- VEHU database: `/home/vehu/g/vehu.gld` — must be the active `ydb_gbldir`
- Run: `source /etc/bashrc && pytest tests/ -m integration`
- CLI: `fm-browser files`, `fm-browser serve`
- Container name: `vehu`, project mounted at `/opt/vista-fm-browser`

## Dev workflow
```bash
make install    # create .venv, install deps, install pre-commit hooks
make test       # run pytest (unit tests only) — host safe
make test-lf    # rerun only the tests that failed last time
make watch      # TDD mode: auto-rerun tests on file save
make cov        # run pytest with coverage report
make check      # lint + mypy + cov (full gate — same as CI)
make format     # auto-format with ruff
make push       # check + git push
make pull       # git pull origin main
```

Container dev:
```bash
docker compose up -d                     # start VEHU container
docker compose exec vehu bash            # open shell inside container
source /etc/bashrc                       # activate YDB + VEHU env (if not auto-sourced)
uv pip install -e '/opt/vista-fm-browser[dev,analysis]' -q  # install project
fm-browser files                         # CLI smoke test
fm-browser serve                         # web UI at http://localhost:5000
pytest tests/ -m integration             # integration tests
```

YottaDB env note:
- `source /etc/bashrc` sets all three required steps:
  1. `ydb_env_set` — YDB library paths (LD_LIBRARY_PATH, ydb_dist)
  2. `/home/vehu/etc/env` — VEHU database paths (gtmgbldir)
  3. `export ydb_gbldir=/home/vehu/g/vehu.gld` — Python connector points to VEHU data
- **Never** use `source /usr/local/etc/ydb_env_set` alone — it points to an empty database.

## Project structure
```
src/vista_fm_browser/
    __init__.py
    connection.py       # YdbConnection + host guard (ImportError)
    data_dictionary.py  # DataDictionary, FileDef, FieldDef — reads ^DD global
    file_reader.py      # FileReader, FileEntry — reads data globals
    exporter.py         # Exporter — CSV/JSON export
    cli.py              # Click CLI (fm-browser command)
    web/
        app.py          # Flask factory + routes
        templates/      # Jinja2 HTML templates

tests/
    conftest.py         # YdbFake, FAKE_DD, FAKE_PATIENT_GLOBAL fixtures
    test_connection.py
    test_data_dictionary.py
    test_file_reader.py
    test_exporter.py

scripts/
    setup-container.sh  # idempotent container setup

docker-compose.yml
.devcontainer/devcontainer.json
```

## Testing conventions
- Write the test first (TDD) — always
- Unit tests use `YdbFake` (in-memory fake, same interface as `YdbConnection`)
- Integration tests marked `@pytest.mark.integration` — run only in container
- No mocks — `YdbFake` is a real implementation of the interface
- Coverage excludes `web/` (templates difficult to unit test); minimum 80% on rest
- One test file per source module

## FileMan global conventions
```
^DD(file#, 0)           = file header: "name^global^count"
^DD(file#, field#, 0)   = field header: "label^type^..."
^DD(file#, "B", name, field#) = field name index

Key file numbers:
  2       = PATIENT
  44      = HOSPITAL LOCATION
  50      = DRUG
  100     = ORDER
  200     = NEW PERSON
  8925    = TIU DOCUMENT
```

Datatype codes: F=Free text, N=Numeric, D=Date, P=Pointer, S=Set of codes,
                M=Mumps, C=Computed, W=Word processing

## YottaDB connection notes
- `yottadb.get(varname, subsarray)` — get a node value
- `yottadb.subscript_next(varname, subsarray)` — iterate subscripts
- `yottadb.data(varname, subsarray)` — 0=none, 1=value, 10=children, 11=both
- Required env vars (set by `source /etc/bashrc`):
  `ydb_gbldir=/home/vehu/g/vehu.gld`, `ydb_dist`, `LD_LIBRARY_PATH`, `gtmgbldir`
- `YdbConnection.connect()` raises `ImportError` on host (expected, not a bug)

## Environment
- Python 3.12, managed via `uv`
- Virtual env: `.venv/` (auto-activated via direnv + `.envrc`)
- Deps declared in `pyproject.toml`
- Lockfile: `uv.lock` — always commit after adding/changing dependencies

## Adding a dependency
```bash
# 1. Add to pyproject.toml under [project.dependencies] or [project.optional-dependencies].dev
# 2. Re-lock and sync:
uv lock && uv sync --extra dev
# 3. Commit both pyproject.toml and uv.lock
```

## Code style
- Formatter + linter: `ruff` only (no black)
- Line length: 88
- Rules: E, F, I (errors, pyflakes, isort)
- Pre-commit hooks enforce style on every commit

## Git conventions
- Main branch: `main`
- Pre-push hook runs `pytest` — push fails if tests fail
- `make push` runs full `check` before pushing
- Commit messages: short imperative ("add retry logic", "fix timeout bug")
- Always commit `uv.lock` alongside `pyproject.toml` changes

## Claude guidelines
- TDD first — write the test, confirm it fails, then implement
- No mocks — use `YdbFake` (real fake, same interface)
- `logging` not `print()` in library code
- `web/` is excluded from coverage — don't fuss over template coverage
- Keep functions small and independently testable
- This is a hobbyist project — keep solutions simple and direct
- Prefer editing existing files over creating new ones
