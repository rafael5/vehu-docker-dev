# FileMan Python API Guide

## What This Covers

This guide documents every FileMan, YottaDB, and VistA RPC function wrapped in Python
by the `vista_fm_browser` package.  It is the reference for anyone building analytics
or extraction tools against a VistA FileMan instance.

The framework operates in two modes:

| Mode | Access path | When to use |
|---|---|---|
| **Direct** | `YdbConnection` → YottaDB globals | Bulk enumeration, high throughput, no RPC auth needed |
| **RPC Broker** | `VistARpcBroker` → DDR RPCs | Remote access, computed fields, proper auth, external values |

Both modes work inside the VEHU container.  The RPC Broker mode also works from
the host (port 9430 is mapped by `docker-compose.yml`).

---

## Module Map

```
src/vista_fm_browser/
    connection.py       YdbConnection — raw YottaDB global access
    fm_datetime.py      FileMan date/time conversion utilities
    data_dictionary.py  DataDictionary — reads ^DD and ^.11
    file_reader.py      FileReader — iterates data globals
    inventory.py        FileInventory — file/package map from ^DIC
    rpc_broker.py       VistARpcBroker — XWB NS-mode DDR RPC client
    exporter.py         Exporter — CSV/JSON export
    cli.py              fm-browser CLI (Click)
    web/app.py          Flask web UI
```

---

## 1. Date/Time Conversion — `fm_datetime`

**Module:** `vista_fm_browser.fm_datetime`

FileMan stores dates and times as a single number in `YYYMMDD.HHMMSS` format where
`YYY = actual_year − 1700`.  Because YottaDB persists these as floats, trailing
zeros in the time fraction are dropped:  `14:30:00 → .143`,  `08:00:00 → .08`.

### Functions

#### `fm_to_dt(fm_date: str) → datetime | None`

Convert a FileMan internal date string to a Python `datetime`.

```python
from vista_fm_browser.fm_datetime import fm_to_dt

fm_to_dt("3160101")          # → datetime(2016, 1, 1, 0, 0, 0)
fm_to_dt("3160101.143")      # → datetime(2016, 1, 1, 14, 30, 0)
fm_to_dt("3160101.143015")   # → datetime(2016, 1, 1, 14, 30, 15)
fm_to_dt("3160101.08")       # → datetime(2016, 1, 1, 8, 0, 0)
fm_to_dt("2450101")          # → datetime(1945, 1, 1, 0, 0, 0)
fm_to_dt("")                 # → None
fm_to_dt("0")                # → None
```

Partial dates (month or day = 0) are normalised to 1.  Unparseable input returns `None`.

#### `dt_to_fm(dt: datetime) → str`

Convert a Python `datetime` to FileMan internal format.  Trailing zeros in the time
fraction are stripped to match how YottaDB stores the value.

```python
from vista_fm_browser.fm_datetime import dt_to_fm

dt_to_fm(datetime(2016, 1, 1))             # → "3160101"
dt_to_fm(datetime(2016, 1, 1, 14, 30, 0)) # → "3160101.143"
dt_to_fm(datetime(2016, 1, 1, 8, 0, 0))   # → "3160101.08"
dt_to_fm(datetime(1945, 1, 1))             # → "2450101"
```

**Roundtrip guarantee:** `fm_to_dt(dt_to_fm(dt)) == dt` for all datetimes that
do not use sub-second precision.

#### `fm_date_display(fm_date: str, *, include_time: bool = True) → str`

Format a FileMan internal date as a human-readable string.

```python
from vista_fm_browser.fm_datetime import fm_date_display

fm_date_display("3160101")                     # → "Jan 01, 2016"
fm_date_display("3160101.143")                 # → "Jan 01, 2016 14:30:00"
fm_date_display("3160101.143", include_time=False)  # → "Jan 01, 2016"
fm_date_display("")                            # → ""
```

### FileMan Date Format Reference

| Internal value | External meaning |
|---|---|
| `3160101` | Jan 01, 2016 |
| `3160101.143` | Jan 01, 2016 14:30:00 |
| `2450101` | Jan 01, 1945 |
| `0` or `""` | No date |
| `3160100` | Jan 01, 2016 (day 00 → 01) |

---

## 2. Data Dictionary — `DataDictionary`

**Module:** `vista_fm_browser.data_dictionary`
**Global read:** `^DD` (data dictionary), `^.11` (INDEX file — new-style cross-references)

The `DataDictionary` class is the primary interface for schema introspection.
It reads `^DD` directly via `YdbConnection` (no RPC needed).

### Dataclasses

#### `FieldDef`

Basic field definition from the `^DD(file, field, 0)` zero-node.

```python
@dataclass
class FieldDef:
    file_number: float
    field_number: float
    label: str              # e.g. "NAME", "DATE OF BIRTH"
    datatype_code: str      # "F", "N", "D", "S", "P", "M", "C", "W", "K"
    datatype_name: str      # "FREE TEXT", "DATE/TIME", "POINTER", etc.
    title: str              # long description from 0-node piece 4
    set_values: dict[str, str]   # code→label for SET type, e.g. {"M":"MALE"}
    pointer_file: float | None   # target file# for POINTER type, e.g. 2.0
```

Pointer file numbers are parsed from the raw type code (`"P50.68"` → `pointer_file=50.68`,
`datatype_code="P"`).

#### `FieldAttributes`

Extended field definition including all readable `^DD` nodes.  Returned by
`get_field_attributes()`.

```python
@dataclass
class FieldAttributes:
    # All FieldDef fields, plus:
    input_transform: str    # ^DD(file, field, 1) — M validation/transform code
    help_prompt: str        # ^DD(file, field, 3) — short help text
    description: list[str]  # ^DD(file, field, 21, n, 0) — word-processing lines
    last_edited: str        # ^DD(file, field, "DT") — FM date of last DD edit
    global_subscript: str   # storage location from 0-node piece 3, e.g. "0;1"
```

#### `FileDef`

File definition from `^DD(file, 0)`.

```python
@dataclass
class FileDef:
    file_number: float
    label: str          # e.g. "PATIENT", "DRUG"
    global_root: str    # e.g. "DPT(", "PS(50,"
    fields: dict[float, FieldDef]
    field_count: int    # property
```

#### `CrossRefInfo`

One cross-reference entry from the INDEX (`^.11`) file.

```python
@dataclass
class CrossRefInfo:
    ien: str
    file_number: float
    name: str        # xref name, e.g. "B", "AC", "ADFN"
    xref_type: str   # "REGULAR" or "MUMPS"
    description: str
```

### DataDictionary Methods

#### `DataDictionary(conn: YdbConnection)`

```python
from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary

with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
```

#### `list_files() → list[tuple[float, str]]`

Return `(file_number, label)` for every FileMan file in `^DD`, sorted by file number.

```python
files = dd.list_files()
# [(2.0, "PATIENT"), (44.0, "HOSPITAL LOCATION"), (50.0, "DRUG"), ...]
```

#### `get_file(file_number: float) → FileDef | None`

Return the full `FileDef` (header + all fields) for a file.  Results are cached.

```python
patient = dd.get_file(2)      # FileDef for PATIENT
patient.label                 # "PATIENT"
patient.global_root           # "DPT("
patient.field_count           # number of fields

for fld in patient.fields.values():
    print(fld.field_number, fld.label, fld.datatype_name)
```

#### `search_files(query: str) → list[tuple[float, str]]`

Case-insensitive label search.

```python
dd.search_files("patient")   # [(2.0, "PATIENT")]
dd.search_files("drug")      # [(50.0, "DRUG"), ...]
```

#### `get_field_attributes(file_number, field_number) → FieldAttributes | None`

Return the full `FieldAttributes` for a single field, reading extended `^DD` nodes.

```python
fa = dd.get_field_attributes(2, 0.01)   # NAME field of PATIENT
fa.label           # "NAME"
fa.datatype_code   # "F"
fa.input_transform # "K:$L(X)>30!(X'?.ANP) X"  (M validation code)
fa.help_prompt     # "ENTER PATIENT NAME (LAST,FIRST)"
fa.last_edited     # "3160101"  (FileMan date)
fa.global_subscript  # "0;1"  (node 0, piece 1)

fa2 = dd.get_field_attributes(2, 0.02)  # SEX field
fa2.set_values     # {"M": "MALE", "F": "FEMALE"}

fa3 = dd.get_field_attributes(50, 100)  # pointer field
fa3.datatype_code  # "P"
fa3.pointer_file   # 50.68
```

This is the Python equivalent of the FileMan DBS calls `FIELD^DID` and `$$GET1^DID`.

#### `format_external(field_attrs, internal_value, *, resolve_pointer=False) → str`

Convert a raw internal global value to its human-readable external form.

```python
fa_name = dd.get_field_attributes(2, 0.01)
fa_sex  = dd.get_field_attributes(2, 0.02)
fa_dob  = dd.get_field_attributes(2, 0.03)
fa_ptr  = dd.get_field_attributes(50, 100)

dd.format_external(fa_name, "SMITH,JOHN")    # → "SMITH,JOHN"  (FREE TEXT as-is)
dd.format_external(fa_sex, "M")              # → "MALE"        (SET: code→label)
dd.format_external(fa_dob, "2450101")        # → "Jan 01, 1945" (DATE formatted)
dd.format_external(fa_ptr, "42")             # → "IEN:42"      (POINTER, no resolve)
dd.format_external(fa_ptr, "42",
                   resolve_pointer=True)      # → "LASIX 40MG"  (looks up target)
```

**Type handling:**

| Type code | Input | Output |
|---|---|---|
| `F` FREE TEXT | `"SMITH,JOHN"` | `"SMITH,JOHN"` (as-is) |
| `N` NUMERIC | `"42"` | `"42"` (as-is) |
| `D` DATE/TIME | `"2450101"` | `"Jan 01, 1945"` |
| `S` SET OF CODES | `"M"` | `"MALE"` |
| `P` POINTER | `"42"` | `"IEN:42"` or resolved name |
| `M` MULTIPLE | any | `"[Multiple]"` |
| `W` WORD PROCESSING | any | `"[Word Processing]"` |
| `C` COMPUTED | any | returned as-is |

This is the Python equivalent of `$$EXTERNAL^DILFD` in the FileMan DBS.

**Pointer resolution** (`resolve_pointer=True`) requires one extra global read per
pointer field to look up the `.01` of the target entry.  For bulk extraction, resolve
pointers in a second pass after collecting IENs.

#### `list_cross_refs(file_number: float) → list[CrossRefInfo]`

Return all new-style cross-references for a file from the INDEX (`^.11`) file.

```python
refs = dd.list_cross_refs(2)
for ref in refs:
    print(ref.name, ref.xref_type)
# B  REGULAR
# SSN  REGULAR
# ADFN  MUMPS
```

Use cross-reference names as the `xref` parameter to `VistARpcBroker.list_entries()`
for ordered lookups.  "B" is always the name/label index.

> **Note:** `^.11` was introduced in FileMan 22.0.  Old-style cross-references
> defined in `^DD(file, field, 1)` are not returned here.

---

## 3. File Data Reader — `FileReader`

**Module:** `vista_fm_browser.file_reader`
**Global read:** Data globals (`^DPT`, `^PS(50,`, etc.)

Iterates raw entries from a FileMan file's data global.  Useful for bulk extraction
without an RPC connection.

### `FileReader(conn, dd)`

```python
from vista_fm_browser.file_reader import FileReader

with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
```

### `iter_entries(file_number, limit=None) → Iterator[FileEntry]`

Yield `FileEntry` objects for every record in the file.

```python
for entry in reader.iter_entries(2, limit=100):
    print(entry.ien, entry.raw_nodes.get("0", ""))
```

`FileEntry` attributes:
- `ien: str` — internal entry number
- `file_number: float`
- `raw_nodes: dict[str, str]` — node key → raw global string (e.g. `{"0": "SMITH,JOHN^M^..."}`)
- `fields: dict[float, str]` — approximate field decode from zero-node pieces

### `get_entry(file_number, ien) → FileEntry | None`

Fetch one entry by IEN.

```python
entry = reader.get_entry(2, "1")
zero_node = entry.raw_nodes.get("0", "")   # "SMITH,JOHN^M^2450101^..."
```

### `count_entries(file_number) → int`

Count total entries in a file without loading them.

```python
count = reader.count_entries(2)  # PATIENT file entry count
```

---

## 4. File and Package Inventory — `FileInventory`

**Module:** `vista_fm_browser.inventory`
**Globals read:** `^DIC` (File #1 registry), `^DIC(9.4,...)` (PACKAGE file), `^DD`

Builds a complete map of every FileMan file and its owning VistA package.
Essential for planning any systematic analysis.

### `FileInventory(conn).load()`

```python
from vista_fm_browser.inventory import FileInventory
from pathlib import Path

with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()

files    = fi.list_files()         # list[FileRecord]
packages = fi.list_packages()      # list[PackageInfo] sorted by name
grouped  = fi.files_by_package()   # dict[pkg_name, list[FileRecord]]
summary  = fi.summary()            # high-level counts
fi.export_json(Path("output/"))    # write inventory.json
```

### `FileRecord`

```python
@dataclass
class FileRecord:
    file_number: float
    label: str
    global_root: str      # e.g. "^DPT("  — normalised to include "^"
    field_count: int      # fields in ^DD
    package_name: str | None
    package_prefix: str | None   # namespace prefix, e.g. "LR", "PS", "DG"
    package_ien: str | None
```

### `PackageInfo`

```python
@dataclass
class PackageInfo:
    ien: str
    name: str             # e.g. "REGISTRATION", "PHARMACY DATA MANAGEMENT"
    prefix: str           # namespace prefix, e.g. "DG", "PSS"
    version: str          # installed version string
    file_numbers: list[float]
```

### `summary() → dict`

Returns counts and top packages by file count:

```python
s = fi.summary()
s["total_files"]     # total number of FileMan files
s["total_packages"]  # total number of VistA packages
s["unpackaged_files"] # files not assigned to any package
s["top_packages_by_file_count"]  # list of {"name": ..., "file_count": ...}
```

### `to_dict() → dict` / `export_json(dir) → Path`

Full JSON-serializable inventory including all packages and files.
`export_json()` writes `inventory.json` to the given directory.

### Unpackaged files

Files not assigned to any package appear under the key `"(unpackaged)"` in
`files_by_package()`.  These are typically sub-files (multiples) and utility files.

---

## 5. RPC Broker Client — `VistARpcBroker`

**Module:** `vista_fm_browser.rpc_broker`
**Protocol:** VistA XWB NS-mode TCP (port 9430)

Connects to the VistA RPC Broker over TCP and executes Remote Procedure Calls.
This is how CPRS and other VistA GUI applications communicate with VistA.

### Connection and Authentication

```python
from vista_fm_browser.rpc_broker import VistARpcBroker

with VistARpcBroker(host="localhost", port=9430) as broker:
    broker.connect(app="FM BROWSER", uci="VAH")
    broker.call("XUS SIGNON SETUP")                # get intro/banner
    duz = broker.authenticate("PRO1234", "PRO1234!!")
    print(f"Authenticated as DUZ={duz}")
```

**VEHU credentials:**

| User | Access code | Verify code | DUZ |
|---|---|---|---|
| PROGRAMMER,ONE | `PRO1234` | `PRO1234!!` | 1 |
| PROVIDER,VERO | `CAS123` | `CAS123..` | 5 |

`authenticate()` automatically encrypts credentials with the ENCRYP^XUSRB1
substitution cipher before sending.  The raw access;verify string is never
transmitted in plaintext — the server decrypts and checks.

### `connect(app, uci) → str`

Perform the NS-mode TCP handshake.  Returns the server acknowledgement (`"accept"`).
Raises `RpcError` if the server rejects the connection.

```python
ack = broker.connect(app="FM BROWSER", uci="VAH")
# ack == "accept"
```

### `call(rpc_name, *params) → str`

Execute any VistA RPC.  Each parameter is either a `str` (literal, TY=0) or a
`dict[str, str]` (list-type M array, TY=2).  Returns the response as a string.
Raises `RpcError` on M errors or broker errors.

```python
# Literal string params (TY=0)
result = broker.call("XUS SIGNON SETUP")
result = broker.call("XWB GET VARIABLE VALUE", "$ZV")

# List-type array param (TY=2) — used for DDR RPCs that take M array params
result = broker.call("DDR GETS ENTRY DATA",
                     {"FILE": "2", "IENS": "1,", "FIELDS": "*", "FLAGS": ""})
```

### `authenticate(access_code, verify_code) → str`

Encrypt credentials and call XUS AV CODE.  Returns DUZ string on success.
Raises `RpcError` on failure or DUZ=0.

```python
duz = broker.authenticate("PRO1234", "PRO1234!!")  # → "1"
```

Must be called after `connect()` and after `broker.call("XUS SIGNON SETUP")`.

### Protocol Helpers (pure functions, no network)

These are exported for testing and low-level protocol work:

```python
from vista_fm_browser.rpc_broker import (
    _sread, _lread, _build_connect_packet, _build_rpc_packet,
    _build_list_param, _parse_response, _xusrb1_encrypt,
)

_sread("PATIENT")    # → b"\x07PATIENT"    (1-byte length prefix)
_lread("PATIENT")    # → b"007PATIENT"     (3-digit decimal prefix)

_build_list_param({"FILE": "2", "IENS": "1,"})
# → b'2006"FILE"0012t006"IENS"0021,f'
# Subscripts are M-quoted so LINST^XWBPRS can use indirect assignment.

_xusrb1_encrypt("PRO1234;PRO1234!!")   # → encrypted string for XUS AV CODE

pkt = _build_rpc_packet("XUS SIGNON SETUP", [])
pkt = _build_rpc_packet("DDR GETS ENTRY DATA",
                         [{"FILE": "2", "IENS": "1,", "FIELDS": "*", "FLAGS": ""}])
```

---

## 6. DDR Data Retrieval RPCs

The DDR (FileMan Delphi Components) RPCs wrap the FileMan DBS API calls and
expose them over the RPC Broker.  They are implemented in VistA routines
`DDR` through `DDR4`.

### `gets_entry_data()` — Read Fields of a Record

Wraps `GETS^DIQ` (DBS API, ICR #2056).

**Important:** DDR GETS ENTRY DATA passes parameters as a local M array (TY=2
list-type encoding), not as individual literal string params.  The wrapper handles
this automatically.  IENS must have a trailing comma (`"1,"`) for single-level
entries — `gets_entry_data()` adds the comma automatically.

```python
# Raw string response
raw = broker.gets_entry_data(
    file_number=2,
    ien="1",          # trailing comma added automatically → "1,"
    fields="*",       # "*"=all top-level, "**"=all including sub-multiples
    flags="",         # "I"=internal values, "E"=external, "N"=omit nulls
)

# Parsed GetsEntry list
entries = broker.gets_entry_data_parsed(file_number=2, ien="1")
for e in entries:
    print(e.field_number, e.value)
```

**`fields` parameter values:**

| Value | Meaning |
|---|---|
| `"*"` | All top-level fields |
| `"**"` | All fields including sub-multiple data |
| `".01"` | Single field |
| `".01^.02^.03"` | Specific fields (caret-separated) |

**`flags` parameter values:**

| Flag | Meaning |
|---|---|
| `"I"` | Return internal values (codes, IENs, FM dates) |
| `"E"` | Return external values (labels, display dates) |
| `"N"` | Omit null/empty values |
| `"R"` | Resolve field numbers to field names in subscripts |

### `GetsEntry` Dataclass

```python
@dataclass
class GetsEntry:
    file_number: float   # FileMan file number
    iens: str            # e.g. "1," for top-level, "1,2," for subfile entry
    field_number: float  # e.g. 0.01
    value: str           # field value (external unless "I" flag)
```

### `parse_gets_response(raw: str) → list[GetsEntry]`

Parse the raw DDR GETS ENTRY DATA response string into `GetsEntry` objects.
A module-level function — no broker connection needed.

```python
from vista_fm_browser.rpc_broker import parse_gets_response

raw = "2^1,^.01^SMITH,JOHN\r\n2^1,^.02^M\r\n2^1,^.03^2450101\r\n"
entries = parse_gets_response(raw)
# [GetsEntry(file_number=2.0, iens="1,", field_number=0.01, value="SMITH,JOHN"),
#  GetsEntry(file_number=2.0, iens="1,", field_number=0.02, value="M"),
#  GetsEntry(file_number=2.0, iens="1,", field_number=0.03, value="2450101")]
```

Lines not matching `file^iens^field^value` format are silently skipped.

---

### `list_entries()` — Browse a File

Wraps `LIST^DIC` via the `DDR LISTER` RPC.  Use for ordered browsing, partial-match
lookups, and paginated results.

```python
entries = broker.list_entries(
    file_number=2,
    xref="B",              # cross-reference to use for ordering
    value="SMITH",         # value to match/start from
    from_value="",         # start from here (use last entry for pagination)
    part=True,             # True=prefix match, False=exact
    max_entries=44,        # maximum entries to return (CPRS standard)
    screen="",             # M filter expression
    identifier="",         # M expression appended to display value
    fields="",             # additional fields to retrieve
)

for entry in entries:
    print(entry.ien, entry.external_value)
```

**Pagination pattern:**

```python
page_size = 44
from_val = ""
while True:
    page = broker.list_entries(file_number=2, max_entries=page_size,
                                from_value=from_val)
    if not page:
        break
    for entry in page:
        process(entry)
    from_val = page[-1].external_value  # start next page after last entry
```

### `ListerEntry` Dataclass

```python
@dataclass
class ListerEntry:
    ien: str                      # internal entry number
    external_value: str           # display value (from xref, typically .01)
    extra_fields: dict[str, str]  # additional field values if requested
```

---

### `find_entry()` — Exact Lookup

Wraps `$$FIND1^DIC` via the `DDR FIND1` RPC.  Returns the IEN of the first
entry matching the exact value, or `""` if not found.

```python
ien = broker.find_entry(
    file_number=2,
    value="SMITH,JOHN",
    xref="B",
    screen="",
)
# → "1" or ""
```

---

### `find_entries()` — Multi-Match Search

Wraps `FIND^DIC` via the `DDR FINDER` RPC.  Returns a list of IEN strings
for all entries matching a value prefix.

```python
iens = broker.find_entries(
    file_number=2,
    value="SMITH",
    xref="B",
    screen="",
    max_entries=100,
)
# → ["1", "42", "107", ...]
```

---

## 7. YottaDB Connection — `YdbConnection`

**Module:** `vista_fm_browser.connection`

Low-level wrapper around the `yottadb` Python connector.  Works only inside
the VEHU container where the YottaDB C library is installed.

```python
from vista_fm_browser.connection import YdbConnection

with YdbConnection.connect() as conn:
    # Get a single node value
    value = conn.get("^DD", ["2", "0"])
    # → "PATIENT^DPT(^3160101^"

    # Iterate subscripts at a level
    for file_num in conn.subscripts("^DD", [""]):
        ...  # yields "2", "44", "50", "200", ...

    # Check if a node or any children exist
    exists = conn.node_exists("^DPT", ["1"])
```

### `conn.get(global_name, subscripts) → str`

Return the string value at a global node.  Returns `""` if the node has no value.

### `conn.subscripts(global_name, subscripts) → Iterator[str]`

Yield all subscripts at the given level in M collation order (numeric before string).

```python
for ien in conn.subscripts("^DPT", [""]):
    if ien.startswith('"'):
        continue   # skip "B", "D", etc. cross-reference nodes
    zero = conn.get("^DPT", [ien, "0"])
```

### `conn.node_exists(global_name, subscripts) → bool`

Return True if the node or any of its children exist (YottaDB `$DATA`).

### Host guard

On the host machine (outside the container), `YdbConnection.connect()` raises
`ImportError` because the `yottadb` package is not installed.  All unit tests use
`YdbFake` (in-memory fake) to avoid this.  Use `RpcBroker` from the host instead.

---

## 8. Exporter — `Exporter`

**Module:** `vista_fm_browser.exporter`

Exports FileMan file data to CSV or JSON.

```python
from vista_fm_browser.exporter import Exporter
from pathlib import Path

with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    exp = Exporter(conn, dd, reader)

    # Export PATIENT file to CSV
    out = exp.export_csv(file_number=2, output_dir=Path("output/"), limit=1000)

    # Export DRUG file to JSON
    out = exp.export_json(file_number=50, output_dir=Path("output/"))
```

Output files are named `{file_number}_{label}.csv` / `.json`.

---

## 9. Key FileMan Globals Reference

| Global | Contents |
|---|---|
| `^DD(file, 0)` | File header: `"label^global_root^date^..."` |
| `^DD(file, field, 0)` | Field header: `"label^type^storage^title"` |
| `^DD(file, field, 1)` | INPUT TRANSFORM (M code) |
| `^DD(file, field, 3)` | HELP-PROMPT text |
| `^DD(file, field, "DT")` | Date field last edited (FM format) |
| `^DD(file, field, "V", code)` | SET-OF-CODES: code → label |
| `^DD("B", label, file)` | File name index |
| `^DIC(file, 0)` | File registry (same structure as `^DD`) |
| `^DIC(9.4, pkg, 0)` | PACKAGE file: `"name^prefix^version^..."` |
| `^DIC(9.4, pkg, 11, n, 0)` | FILE multiple: file# owned by package |
| `^.11(ien, 0)` | INDEX file: `"file#^name^type^..."` (new-style xrefs) |
| `^DPT(ien, 0)` | PATIENT file zero-node |
| `^PS(50, ien, 0)` | DRUG file zero-node |
| `^SC(ien, 0)` | HOSPITAL LOCATION zero-node |
| `^VA(200, ien, 0)` | NEW PERSON zero-node |

### FileMan Field Type Codes

| Code | Type | Notes |
|---|---|---|
| `F` | FREE TEXT | Stored as-is |
| `N` | NUMERIC | May have DECIMAL DEFAULT |
| `D` | DATE/TIME | Internal: `YYYMMDD.HHMMSS` |
| `S` | SET OF CODES | Values in `^DD(file,field,"V",code)` |
| `P<n>` | POINTER | `n` = target file number (e.g. `P2` → PATIENT) |
| `M` | MULTIPLE | Sub-file; `n` = subfile number |
| `C` | COMPUTED | Not stored in data global |
| `DC` | COMPUTED DATE | Computed date value |
| `K` | MUMPS | Arbitrary M code stored/executed |
| `V` | VARIABLE POINTER | Points to one of several files depending on prefix |
| `W` | WORD PROCESSING | Multi-line text; sub-global nodes |

---

## 10. FileMan DBS API → Python Mapping

| FileMan DBS call | Python equivalent | Notes |
|---|---|---|
| `GETS^DIQ` | `broker.gets_entry_data_parsed()` | Via DDR GETS ENTRY DATA (TY=2 param) |
| `$$GET1^DIQ` | `broker.gets_entry_data(fields=".01")` | Single field |
| `FIND^DIC` | `broker.find_entries()` | Via DDR FINDER |
| `$$FIND1^DIC` | `broker.find_entry()` | Via DDR FIND1 |
| `LIST^DIC` | `broker.list_entries()` | Via DDR LISTER |
| `FIELD^DID` | `dd.get_field_attributes()` | Direct `^DD` read |
| `FILE^DID` | `dd.get_file()` | Direct `^DD` read |
| `$$GET1^DID` | `dd.get_field_attributes()` | Returns full `FieldAttributes` |
| `FILELST^DID` | `dd.list_files()` | Direct `^DD` walk |
| `$$ROOT^DILFD` | `FileDef.global_root` | From `get_file().global_root` |
| `$$EXTERNAL^DILFD` | `dd.format_external()` | Python implementation |
| `$$FLDNUM^DILFD` | `FileDef.fields` dict by label | Search `fields.values()` |
| `EN^DIS` | `broker.find_entries(screen=...)` | With M screen expression |

---

## 11. Workflows

### Extract all patients with formatted fields

```python
from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader

with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)

    file_def = dd.get_file(2)        # PATIENT file
    attrs = {
        field_num: dd.get_field_attributes(2, field_num)
        for field_num in file_def.fields
    }

    for entry in reader.iter_entries(2, limit=100):
        zero = entry.raw_nodes.get("0", "").split("^")
        name = zero[0] if zero else ""
        sex_raw = zero[1] if len(zero) > 1 else ""
        dob_raw = zero[2] if len(zero) > 2 else ""

        sex_fa = attrs.get(0.02)
        dob_fa = attrs.get(0.03)

        sex = dd.format_external(sex_fa, sex_raw) if sex_fa else sex_raw
        dob = dd.format_external(dob_fa, dob_raw) if dob_fa else dob_raw
        print(entry.ien, name, sex, dob)
```

### Read a record via RPC with full authentication

```python
from vista_fm_browser.rpc_broker import VistARpcBroker

with VistARpcBroker(host="localhost", port=9430) as broker:
    broker.connect(app="FM BROWSER", uci="VAH")
    broker.call("XUS SIGNON SETUP")
    duz = broker.authenticate("PRO1234", "PRO1234!!")

    # Read all fields for PATIENT IEN=1
    entries = broker.gets_entry_data_parsed(file_number=2, ien="1", fields="*")
    for e in entries:
        print(e.field_number, e.value)

    # Get field 0.01 (NAME) only, in internal format
    raw = broker.gets_entry_data(file_number=2, ien="1", fields=".01", flags="I")

    # Find all patients whose name starts with "SMITH"
    matches = broker.list_entries(file_number=2, value="SMITH", part=True)
    for entry in matches:
        print(entry.ien, entry.external_value)
```

### Build a package-aware file catalog

```python
from vista_fm_browser.inventory import FileInventory
from pathlib import Path

with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()
    fi.export_json(Path("output/"))

    # Print files for a specific package
    grouped = fi.files_by_package()
    for fr in grouped.get("REGISTRATION", []):
        print(fr.file_number, fr.label, fr.global_root, fr.field_count)

    # Unpackaged files (sub-files, utility files)
    for fr in grouped.get("(unpackaged)", []):
        print(fr.file_number, fr.label)
```

### Discover cross-references for query planning

```python
refs = dd.list_cross_refs(2)
for ref in refs:
    print(f"  xref '{ref.name}' type={ref.xref_type}")

# Use a named cross-reference for an indexed search
entries = broker.list_entries(file_number=2, xref="SSN", value="123456789")
```

### Paginate a large file via DDR LISTER

```python
page_size = 100
from_val = ""
all_entries = []

with VistARpcBroker(host="localhost", port=9430) as broker:
    broker.connect()
    broker.call("XUS SIGNON SETUP")
    broker.authenticate("PRO1234", "PRO1234!!")

    while True:
        page = broker.list_entries(
            file_number=200,          # NEW PERSON
            xref="B",
            max_entries=page_size,
            from_value=from_val,
        )
        if not page:
            break
        all_entries.extend(page)
        from_val = page[-1].external_value
```

---

## 12. Running in Both Environments

### Host machine (unit tests only)

```bash
make test       # uses YdbFake, no Docker required
make check      # lint + mypy + coverage
make watch      # TDD mode: auto-rerun on file save
```

### Inside VEHU container (integration + live usage)

```bash
docker-compose up -d                  # start container
source /etc/yottadb/env               # activate YottaDB (auto in bash)
fm-browser inventory                  # CLI: print file inventory
fm-browser serve                      # web UI at http://localhost:5000
pytest tests/ -m integration -v       # integration tests against live VistA
```

### YottaDB environment variables (inside container)

```bash
echo $ydb_gbldir       # path to global directory file
echo $ydb_routines     # routine search path
echo $ydb_dist         # YottaDB installation directory
```

---

## 13. Testing Strategy

### Unit tests (no container, no RPC)

All unit tests use `YdbFake` — an in-memory dict-based implementation of
`YdbConnection`.  DDR RPC tests use `_ThreadedFakeServer` — a real TCP server
that speaks the XWB NS protocol over loopback.

```
tests/
    conftest.py              YdbFake, FAKE_DD, FAKE_PATIENT_GLOBAL fixtures
    test_connection.py       YdbConnection interface tests
    test_fm_datetime.py      Date/time conversion — 37 tests
    test_data_dictionary.py  DD reading + extended methods — 51 tests
    test_file_reader.py      FileReader global iteration
    test_inventory.py        FileInventory package/file map
    test_rpc_broker.py       XWB protocol + DDR methods — 71 tests
    test_exporter.py         CSV/JSON export
```

### Integration tests (run inside VEHU container)

```bash
pytest tests/ -m integration -v
```

### Adding tests for new wrappers

Follow the pattern in `test_data_dictionary.py` — define inline fake data,
build a `YdbFake`, pass to the class under test.  No mocks needed.

---

## 14. XWB NS-mode Protocol Reference

The XWB NS-mode protocol used by all DDR RPCs.  Implemented in `rpc_broker.py`,
derived from `XWBPRS.m` and `XWBTCPMT.m` source analysis.

### Packet structure

```
Connection handshake (once per session):
  [XWB]1030               — magic + PRSP (ver=1 type=0 lenv=3 rt=0)
  4 + SREAD("TCPConnect") — chunk4: command
  5                       — chunk5 header
  + "0" + LREAD(ip)  + "f"
  + "0" + LREAD(port) + "f"
  + "0" + LREAD(app)  + "f"
  + "0" + LREAD(uci)  + "f"
  + \x04                  — EOT

RPC call:
  [XWB]1030
  1 + SREAD("") + SREAD("")          — chunk1: empty ver + return_type
  2 + SREAD("0") + SREAD(rpc_name)   — chunk2: rpc
  5 + [params] + \x04                — chunk5: params + EOT

Response: \x00\x00{content}\x04
  Leading \x00\x00 and trailing \x04 are stripped.
  M errors: \x00\x00\x18M  ERROR=...\x04
```

### Param TY encodings in chunk5

| TY byte | Meaning | Wire format |
|---|---|---|
| `b"0"` (ASCII 48) | Literal string | `TY + LREAD(value) + b"f"` |
| `b"2"` (ASCII 50) | List-type M array | `TY + (LREAD(m_quoted_sub) + LREAD(val) + CONT)... ` |
| `b"\x04"` | EOT — end of params | Always last byte of chunk5 |

**Critical:** TY byte must be ASCII digit `b"0"`, NOT `b"\x00"`.  MUMPS `IF TY=0`
is a string comparison matching `"0"`, not `chr(0)`.

**List-type subscript quoting:** Subscripts in TY=2 params must be sent with embedded
M string quotes (e.g. `"FILE"` → sent as `'"FILE"'`).  `LINST^XWBPRS` uses M
indirection: `S @(array_"("_subscript_")")=value` — without quotes the subscript is
treated as a local variable name and raises `LVUNDEF`.

### ENCRYP^XUSRB1 cipher

XUS AV CODE requires credentials to be encrypted before transmission.
`_xusrb1_encrypt(plaintext)` implements the matching Python cipher.

```python
plaintext = "PRO1234;PRO1234!!"   # access;verify
encrypted = _xusrb1_encrypt(plaintext)
result = broker.call("XUS AV CODE", encrypted)
```

The cipher: pick two different random row indices (1-20), use one as the key
(identifier) and one as the cipher (associator).  Translate each character.
Wrap with `chr(idix+31)` prefix and `chr(associx+31)` suffix.

---

## 15. Key File Numbers

| Number | File name | Global |
|---|---|---|
| 1 | FILE | `^DIC` |
| 2 | PATIENT | `^DPT` |
| 3.5 | DEVICE | `^%ZIS(1,` |
| 9.4 | PACKAGE | `^DIC(9.4,` |
| 19 | OPTION | `^DIC(19,` |
| 44 | HOSPITAL LOCATION | `^SC` |
| 50 | DRUG | `^PSDRUG(` |
| 100 | ORDER | `^OR(100,` |
| 200 | NEW PERSON | `^VA(200,` |
| 8925 | TIU DOCUMENT | `^TIU(8925,` |
| .11 | INDEX (cross-references) | `^.11` |
| .9 | TEMPLATE | `^DIBT` |
| 1.5 | ENTITY | `^DDE` |

---

## 16. Limitations and Known Gaps

- **Computed fields** (`C` type) cannot be read from raw globals — they require
  executing M code.  Use `gets_entry_data()` via the RPC Broker to retrieve
  computed values server-side.

- **Word-processing fields** (`W` type) are stored in sub-global nodes.
  `format_external()` returns `"[Word Processing]"` as a placeholder.  Read WP
  content directly from the global sub-nodes or use
  `gets_entry_data(fields="10", flags="Z")`.

- **DDR LISTER / FINDER / FIND1** parameter encoding is sent as literal TY=0 params.
  This has not been verified against live VEHU for all parameter combinations.
  Verify `list_entries()`, `find_entry()`, and `find_entries()` against a live
  container before production use.

- **Variable Pointer** (`V` type) fields reference one of several files.
  `format_external()` returns the raw value for V-type fields.  Full resolution
  requires reading the variable pointer definition from `^DD`.

- **ENTITY file** (`^DDE`, file #1.5) is not yet wrapped.  `$$GET1^DDE` and
  `GET^DDE` provide structured extraction across multiple files — a future
  `entity.py` module would wrap these.

- **Sub-file iteration** via `gets_entry_data(fields="**")` is the correct way to
  retrieve sub-multiple data via RPC.  Direct global iteration of sub-file nodes
  requires knowing the storage location from `global_subscript` in `FieldAttributes`.
