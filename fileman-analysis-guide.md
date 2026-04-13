# FileMan Data Dictionary Analysis Guide

## Purpose and Strategy

This guide provides a systematic approach to comprehensive FileMan data dictionary
analysis using the `vista_fm_browser` Python library.  The goal is a complete picture
of the VistA data estate: its scope, volume, variety, and structure — sufficient to
plan normalization, schema export, API wrapping, or migration.

**Strategy: big picture first, details second.**

The steps are ordered so that each phase answers the broadest remaining question
before any drill-down.  After Phase 1 you know the scope.  After Phase 2 you know
where the data lives.  After Phase 3 you understand the structural topology.  Only
then do Phases 4 and 5 drill into field-level schema and normalization specifics.

This ordering matters because FileMan contains ~3,000 files and ~50,000 fields.
Without the big picture first, field-level analysis produces facts with no context.

### What "normalization analysis" means here

FileMan's data dictionary (`^DD`) is package-centric: each of the 127 VistA
application packages defines its own files and fields without coordination.  The same
concept — patient identifier, provider name, clinical date, active/inactive status —
appears in dozens of files under different field numbers, labels, and type codes.

The analysis surfaces:
- **Scope** — total files, fields, packages, and the distribution across them
- **Volume** — which files hold real data and how much
- **Topology** — how files reference each other (the join/pointer graph)
- **Variety** — what data types exist and how consistently they are used
- **Naming** — how the same concept is labeled across packages
- **Overlap** — the same logical field defined in multiple files
- **Coverage** — which defined fields are actually populated
- **Standard patterns** — `.01` NAME, `.03` DATE, hub file FK conventions

All steps are **read-only**.  No VistA data is modified.

---

## Background: FileMan at a Glance

From `va_fileman_guide.md` and `va_fileman_summary.md` in `vista-docs/guides/fileman/`:

```
M Runtime
    └── VA FileMan (DI namespace, v22.2)   ← universal data substrate
            └── Kernel + MailMan           ← operating environment
                    └── 127 application packages (ADT, CPRS, Lab, Pharmacy, …)
```

| Concept | Modern analogy |
|---|---|
| File | Database table; identified by a unique numeric file number |
| Field | Column; has a number, label, data type, and executable validation |
| Entry | Row; addressed by IEN (Internal Entry Number, auto-increment PK) |
| Multiple | One-to-many child sub-file (child table with FK to parent IEN) |
| Data Dictionary (`^DD`) | `information_schema` + DDL + inline validation, live at runtime |
| Cross-reference | B-tree index + trigger + CDC notification — one object |
| Pointer | FK storing an IEN from another file |
| Variable Pointer | Polymorphic FK that can reference any of a set of files |

Key hub files referenced by almost every clinical package:

| File # | Name | Global | Owner package |
|---|---|---|---|
| 2 | PATIENT | `^DPT` | Registration (DG) |
| 200 | NEW PERSON | `^VA(200,` | Kernel (XU) |
| 4 | INSTITUTION | `^DIC(4,` | Kernel (XU) |
| 19 | OPTION | `^DIC(19,` | Kernel (XU) |
| 50 | DRUG | `^PSDRUG(` | Pharmacy (PS) |
| 63 | LAB DATA | `^LR(` | Laboratory (LR) |
| 100 | ORDER | `^OR(100,` | CPRS (OE/RR) |
| 101 | PROTOCOL | `^ORD(101,` | Kernel (XU) |

---

## Setup

### Inside the VEHU container (full access — recommended)

```bash
docker-compose up -d
docker exec -it vehu bash
source /etc/yottadb/env
cd /opt/vista-fm-browser
source .venv/bin/activate
python3
```

### From the host via RPC Broker

```python
from vista_fm_browser.rpc_broker import VistARpcBroker

broker = VistARpcBroker(host="localhost", port=9430)
broker.connect(app="FM BROWSER", uci="VAH")
broker.call("XUS SIGNON SETUP")
broker.authenticate("PRO1234", "PRO1234!!")
```

### Standard imports (used throughout)

```python
from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory
from vista_fm_browser.file_reader import FileReader
from pathlib import Path
import json, csv, collections
```

---

## Phase 1 — Scope Survey (15 minutes)

**Goal:** Know the total size of the problem in five numbers before touching any field.

### 1.1 Package and file counts

```python
with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()

    s = fi.summary()
    print(f"Files total:      {s['total_files']}")
    print(f"Packages total:   {s['total_packages']}")
    print(f"Unpackaged files: {s['unpackaged_files']}")

    # Top 20 packages by file count
    grouped = fi.files_by_package()
    by_count = sorted(
        ((k, len(v)) for k, v in grouped.items() if k != "(unpackaged)"),
        key=lambda x: -x[1]
    )
    print("\nTop 20 packages by file count:")
    for name, count in by_count[:20]:
        print(f"  {name:45s} {count:4d} files")
```

**Expected scope on VEHU:**
- ~2,500 total files
- ~90 packages
- ~600 unpackaged files (sub-files / utility files)
- Top packages: REGISTRATION, PHARMACY DATA MANAGEMENT, KERNEL, LAB SERVICE own 200+ files each

### 1.2 Total field count

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    all_files = dd.list_files()
    total_fields = 0
    for file_num, _label in all_files:
        fd = dd.get_file(file_num)
        if fd:
            total_fields += fd.field_count
    print(f"Total files:    {len(all_files)}")
    print(f"Total fields:   {total_fields}")
    print(f"Avg fields/file: {total_fields / len(all_files):.1f}")
```

### 1.3 Field type distribution — the variety picture

This is the single fastest way to understand what kinds of data FileMan holds.

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)

    type_counts: dict[str, int] = collections.Counter()
    type_names:  dict[str, str] = {}
    for file_num, _label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for fld in fd.fields.values():
            type_counts[fld.datatype_code] += 1
            type_names[fld.datatype_code] = fld.datatype_name

    print(f"\n{'Type':6s}  {'Name':22s}  {'Count':>7s}  {'%':>6s}")
    print("-" * 50)
    total = sum(type_counts.values())
    for code, count in type_counts.most_common():
        name = type_names.get(code, code)
        pct = 100 * count / total
        print(f"  {code:4s}  {name:22s}  {count:7,d}  {pct:5.1f}%")
    print(f"  {'TOTAL':4s}  {'':22s}  {total:7,d}  100.0%")
```

Typical distribution:

| Type | Name | Approx % | Notes |
|---|---|---|---|
| `F` | FREE TEXT | 38% | Largest category; variable length, unstructured |
| `P` | POINTER | 21% | Every pointer is a foreign key — the join graph |
| `S` | SET OF CODES | 11% | Enumeration; finite value set; code→label |
| `D` | DATE/TIME | 10% | FileMan internal YYYMMDD format |
| `N` | NUMERIC | 8% | Integer or decimal |
| `M` | MULTIPLE | 7% | Sub-file reference; one-to-many relationship |
| `W` | WORD PROCESSING | 3% | Narrative text; stored in sub-global nodes |
| `C` | COMPUTED | 1% | Not in data global; requires M execution |
| `K` | MUMPS | <1% | Executable M code stored as data |
| `V` | VARIABLE POINTER | <1% | Polymorphic FK; can reference multiple files |

### 1.4 Export the inventory for offline reference

```python
with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()
    out = fi.export_json(
        Path("~/data/vista-fm-browser/output/").expanduser()
    )
    print(f"Inventory written to {out}")
```

**Output:** `output/inventory.json` — packages, file numbers, labels, field counts.
Use this as the master reference for all subsequent phases.

---

## Phase 2 — Volume Survey (30 minutes)

**Goal:** Find out where the actual data lives.  Files with millions of entries
demand different treatment than files with a handful.  This phase separates the
heavyweight clinical files from the small configuration files.

### 2.1 Entry counts for all files with data

```python
with YdbConnection.connect() as conn:
    reader = FileReader(conn, DataDictionary(conn))
    fi = FileInventory(conn)
    fi.load()

    volume: list[tuple[int, float, str]] = []
    for fr in fi.list_files():
        count = reader.count_entries(fr.file_number)
        if count > 0:
            volume.append((count, fr.file_number, fr.label))

    volume.sort(reverse=True)
    print(f"Files with data: {len(volume)} of {len(fi.list_files())}")
    print(f"\nTop 40 files by entry count:")
    for count, num, label in volume[:40]:
        pkg = next(
            (fr.package_name for fr in fi.list_files() if fr.file_number == num),
            "?"
        )
        print(f"  {num:8.2f}  {label:40s}  {count:>10,}  [{pkg}]")

    # Save full volume list
    out = Path("~/data/vista-fm-browser/output/file_volume.json").expanduser()
    out.write_text(json.dumps(
        [{"file_number": n, "label": l, "entry_count": c}
         for c, n, l in volume],
        indent=2
    ))
    print(f"\nVolume data written to {out}")
```

### 2.2 Volume tiers — classify files by magnitude

```python
tiers = {
    "massive (>100K entries)": [],
    "large (10K–100K)":        [],
    "medium (1K–10K)":         [],
    "small (100–1K)":          [],
    "tiny (<100)":             [],
    "empty (0)":               [],
}
for count, num, label in volume:
    if count == 0:         tiers["empty (0)"].append((num, label))
    elif count < 100:      tiers["tiny (<100)"].append((num, label, count))
    elif count < 1000:     tiers["small (100–1K)"].append((num, label, count))
    elif count < 10000:    tiers["medium (1K–10K)"].append((num, label, count))
    elif count < 100000:   tiers["large (10K–100K)"].append((num, label, count))
    else:                  tiers["massive (>100K entries)"].append((num, label, count))

for tier, files in tiers.items():
    print(f"{tier}: {len(files)} files")
```

**What to expect:**
- **Massive:** LAB DATA (#63), TIU DOCUMENT (#8925), ORDER (#100), PHARMACY PATIENT (#55)
  — these are the primary clinical record stores, 100K–10M+ entries
- **Large:** PATIENT (#2), APPOINTMENT (#2.98), VISIT (#9000010)
- **Small/tiny:** Configuration files, code sets, option lists
- **Empty:** ~40% of defined files may have zero entries in VEHU (a demo system)

### 2.3 Data density — bytes per entry estimate

For the top 20 files, spot-check a sample entry to estimate record size:

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)

    for count, num, label in volume[:20]:
        entry = reader.get_entry(num, "1")
        if not entry:
            continue
        raw_size = sum(len(v) for v in entry.raw_nodes.values())
        field_count = dd.get_file(num).field_count if dd.get_file(num) else 0
        print(f"  {num:8.2f}  {label:35s}  "
              f"{count:>8,} entries  "
              f"{raw_size:4d} bytes/entry (sample)  "
              f"{field_count:3d} fields")
```

---

## Phase 3 — Structural Topology (1–2 hours)

**Goal:** Map the pointer graph — how files reference each other.
This reveals the relational backbone of VistA and identifies the hub files
that appear as foreign key targets across dozens of packages.

FMQL (George Leal, 2010–2018) discovered that FileMan's pointer model maps
naturally to a **directed graph** where files are nodes and pointer fields are
edges.  The hub files are the most-referenced nodes; they are the anchor points
for any normalization or integration design.

### 3.1 Build the full schema (one pass)

Run this once and cache the result — it reads every `^DD` entry.

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    fi = FileInventory(conn)
    fi.load()

    pkg_by_file: dict[float, str] = {
        fr.file_number: (fr.package_name or "(unpackaged)")
        for fr in fi.list_files()
    }

    schema: list[dict] = []
    for file_num, file_label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for field_num, fld in fd.fields.items():
            schema.append({
                "file_number":   file_num,
                "file_label":    file_label,
                "package":       pkg_by_file.get(file_num, "(unpackaged)"),
                "field_number":  field_num,
                "field_label":   fld.label,
                "datatype_code": fld.datatype_code,
                "datatype_name": fld.datatype_name,
                "pointer_file":  fld.pointer_file,
                "set_values":    fld.set_values,
            })

    # Cache to disk — use for all subsequent phases
    out = Path("~/data/vista-fm-browser/output/all_fields.json").expanduser()
    out.write_text(json.dumps(schema, indent=2, default=str))
    print(f"Schema: {len(schema):,} fields across {len(dd.list_files()):,} files")
    print(f"Written to {out}")
```

### 3.2 Pointer graph — hub file identification

```python
pointer_fields = [r for r in schema
                  if r["datatype_code"] == "P" and r["pointer_file"]]

# Inbound edge count per target file (how many files point TO it)
inbound: dict[float, set[float]] = {}
for r in pointer_fields:
    tgt = r["pointer_file"]
    inbound.setdefault(tgt, set()).add(r["file_number"])

print(f"\nPointer fields: {len(pointer_fields):,}")
print(f"Unique targets:  {len(inbound):,} files referenced by pointers")
print(f"\nTop 30 hub files (most-referenced):")
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    for tgt, srcs in sorted(inbound.items(), key=lambda x: -len(x[1]))[:30]:
        fd = dd.get_file(tgt)
        label = fd.label if fd else "?"
        print(f"  File {tgt:8.2f}  {label:40s}  ← referenced by {len(srcs):3d} files")
```

Expected top hubs (in order):
```
File     2.00  PATIENT                      ← ~80+ files reference PATIENT
File   200.00  NEW PERSON                   ← ~70+ files (provider, author, etc.)
File     4.00  INSTITUTION                  ← ~60+ files (site, treating facility)
File    50.00  DRUG                         ← ~40+ files
File    44.00  HOSPITAL LOCATION            ← ~35+ files (clinic, ward)
File   101.00  PROTOCOL                     ← ~30+ files
File    80.00  ICD DIAGNOSIS                ← ~25+ files
```

### 3.3 Pointer graph — outbound density per file

Files with many outbound pointers are the most "denormalized" — they hold
references to many other concepts and are the best candidates for join-intensive
analytical queries.

```python
# Outbound: distinct target files per source file
outbound: dict[float, set[float]] = {}
for r in pointer_fields:
    outbound.setdefault(r["file_number"], set()).add(r["pointer_file"])

print("\nTop 20 files by outbound pointer count (most FK-rich):")
for file_num, targets in sorted(outbound.items(), key=lambda x: -len(x[1]))[:20]:
    fd_label = next((r["file_label"] for r in schema
                     if r["file_number"] == file_num), "?")
    pkg = pkg_by_file.get(file_num, "?")
    print(f"  File {file_num:8.2f}  {fd_label:40s}  → {len(targets):3d} targets  [{pkg}]")
```

### 3.4 Export the pointer graph

```python
edges = []
for r in pointer_fields:
    edges.append({
        "from_file":   r["file_number"],
        "from_label":  r["file_label"],
        "from_pkg":    r["package"],
        "field_num":   r["field_number"],
        "field_label": r["field_label"],
        "to_file":     r["pointer_file"],
    })

out = Path("~/data/vista-fm-browser/output/pointer_graph.json").expanduser()
out.write_text(json.dumps(edges, indent=2, default=str))
print(f"Pointer graph: {len(edges):,} edges written to {out}")
```

### 3.5 Variable pointer files (polymorphic FKs)

Variable pointer (`V` type) fields point to different files depending on the
value prefix.  These represent polymorphic relationships — the FileMan equivalent
of a discriminated union or union type.

```python
variable_pointers = [r for r in schema if r["datatype_code"] == "V"]
print(f"\nVariable pointer fields: {len(variable_pointers)}")
# Group by file to see which files use polymorphic references
vp_by_file = collections.Counter(r["file_number"] for r in variable_pointers)
for file_num, count in vp_by_file.most_common(10):
    label = next((r["file_label"] for r in schema
                  if r["file_number"] == file_num), "?")
    print(f"  File {file_num:.2f}  {label:40s}  {count} variable pointer fields")
```

### 3.6 Multiple (sub-file) depth map

MULTIPLE (`M` type) fields define one-to-many sub-file relationships.
The sub-file number is the `pointer_file` value.

```python
multiple_fields = [r for r in schema if r["datatype_code"] == "M"]
print(f"\nMULTIPLE fields (sub-files): {len(multiple_fields)}")

# Files with most sub-files (deepest nesting)
multiples_per_file = collections.Counter(r["file_number"] for r in multiple_fields)
print("Files with most MULTIPLE fields (most complex object hierarchy):")
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    for file_num, count in multiples_per_file.most_common(15):
        fd = dd.get_file(file_num)
        label = fd.label if fd else "?"
        print(f"  File {file_num:8.2f}  {label:40s}  {count} sub-files")
```

---

## Phase 4 — Data Variety and Naming Analysis (1–2 hours)

**Goal:** Understand what values exist (SET-OF-CODES), how naming is used
consistently or inconsistently, and where the same concept appears under
different labels.

### 4.1 SET-OF-CODES inventory — all enumerated value sets

SET fields (`S` type) are enumeration fields: each has a defined list of
code→label pairs.  Collecting all value sets reveals:
- Shared enumerations reused across packages (YES/NO, ACTIVE/INACTIVE)
- Package-specific code lists
- Inconsistent coding of the same concept (ACTIVE=1 vs ACTIVE=A vs ACTIVE=Y)

```python
set_fields = [r for r in schema if r["datatype_code"] == "S" and r["set_values"]]
print(f"\nSET-OF-CODES fields with defined values: {len(set_fields)}")

# Canonicalize value sets for comparison
def canon_set(sv: dict) -> frozenset:
    return frozenset(
        (k.strip().upper(), v.strip().upper()) for k, v in sv.items()
    )

seen_sets: dict[frozenset, list[dict]] = {}
for r in set_fields:
    key = canon_set(r["set_values"])
    seen_sets.setdefault(key, []).append(r)

shared = [(key, grp) for key, grp in seen_sets.items() if len(grp) >= 5]
shared.sort(key=lambda x: -len(x[1]))

print(f"\nValue sets shared across ≥5 fields ({len(shared)} total):")
for key, group in shared[:15]:
    sample_codes = dict(list(key)[:4])
    print(f"\n  codes={sample_codes}")
    print(f"  used in {len(group)} fields across "
          f"{len(set(r['file_number'] for r in group))} files:")
    for r in group[:4]:
        print(f"    File {r['file_number']:.2f} {r['file_label']:30s} "
              f"· {r['field_label']}")
```

### 4.2 Boolean equivalents — YES/NO patterns

```python
boolean_patterns = [
    frozenset({("Y","YES"),("N","NO")}),
    frozenset({("1","YES"),("0","NO")}),
    frozenset({("A","ACTIVE"),("I","INACTIVE")}),
    frozenset({("1","ACTIVE"),("0","INACTIVE")}),
]

for pattern in boolean_patterns:
    matches = seen_sets.get(pattern, [])
    if matches:
        codes = dict(list(pattern))
        print(f"  {codes}: {len(matches)} fields in "
              f"{len(set(r['file_number'] for r in matches))} files")
```

### 4.3 Label frequency — what concepts appear across all packages

```python
label_counter = collections.Counter(
    r["field_label"].strip().upper() for r in schema
)
print(f"\nTop 40 field labels across all files:")
for label, count in label_counter.most_common(40):
    print(f"  {label:45s}  {count:5,}")
```

Common leaders: `NAME`, `DATE`, `STATUS`, `TYPE`, `DESCRIPTION`, `CODE`,
`ACTIVE`, `INACTIVE DATE`, `USER`, `LOCATION`, `COMMENT`.

### 4.4 Label-type consistency — same label, different types

This is a primary normalization signal: where the same concept is typed
differently across packages.

```python
label_groups: dict[str, list[dict]] = {}
for r in schema:
    key = r["field_label"].strip().upper()
    label_groups.setdefault(key, []).append(r)

inconsistent = []
for label, rows in label_groups.items():
    if len(rows) < 5:
        continue
    types = set(r["datatype_code"] for r in rows)
    if len(types) > 1:
        type_dist = collections.Counter(r["datatype_code"] for r in rows)
        inconsistent.append({
            "label": label,
            "occurrences": len(rows),
            "types": dict(type_dist),
            "files": len(set(r["file_number"] for r in rows)),
        })

inconsistent.sort(key=lambda x: -x["occurrences"])
print(f"\nLabels with same name but inconsistent types "
      f"(≥5 occurrences): {len(inconsistent)}")
for item in inconsistent[:20]:
    print(f"  {item['label']:40s}  in {item['occurrences']:4d} fields  "
          f"types={item['types']}")
```

Typical findings:
- `STATUS` — appears as `S` (SET), `F` (FREE TEXT), `N` (NUMERIC)
- `DATE` — appears as `D`, `F`, and even `N` in some packages
- `TYPE` — appears as `S`, `P`, `F` depending on context
- `ACTIVE` — appears as `S` (A/I codes), `D` (date activated), `F`

### 4.5 Canonical field positions

FileMan has informal conventions for field numbers at specific positions.
Mapping these reveals the degree of convention adherence across packages.

```python
canonical_positions = {
    0.01: "PRIMARY NAME/IDENTIFIER",
    0.02: "CATEGORY/TYPE",
    0.03: "PARENT REFERENCE or DATE",
    0.05: "SEX or SECONDARY IDENTIFIER",
    0.07: "STATUS",
    0.09: "SSN or UNIQUE ID",
    1.0:  "SECONDARY CONTENT or ADDRESS",
    99.0: "CLASS/CATEGORY",
}

print("\nCanonical field position analysis:")
for pos, concept in canonical_positions.items():
    hits = [r for r in schema if abs(r["field_number"] - pos) < 0.001]
    if not hits:
        continue
    type_dist = collections.Counter(r["datatype_code"] for r in hits)
    top_labels = collections.Counter(r["field_label"].upper() for r in hits)
    print(f"\n  Field {pos:.2f}  ({concept}):  {len(hits)} definitions")
    print(f"    Types:  {dict(type_dist.most_common(4))}")
    print(f"    Labels: {dict(top_labels.most_common(5))}")
```

---

## Phase 5 — Schema Deep Dive (per file or package)

**Goal:** After the big picture is clear, drill into specific files to get the
full field-level schema including storage layout, validation logic, help text,
and last-edit dates.

### 5.1 Full field attributes for one file

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    file_num = 2  # PATIENT — start with the most important file

    fd = dd.get_file(file_num)
    print(f"File {file_num}: {fd.label}  ({fd.field_count} fields)")

    extended = []
    for field_num in sorted(fd.fields.keys()):
        fa = dd.get_field_attributes(file_num, field_num)
        if fa is None:
            continue
        extended.append({
            "field":           fa.field_number,
            "label":           fa.label,
            "type":            fa.datatype_name,
            "storage":         fa.global_subscript,   # "0;1" = node 0, piece 1
            "pointer_file":    fa.pointer_file,
            "set_values":      fa.set_values,
            "help_prompt":     fa.help_prompt[:60],
            "has_description": bool(fa.description),
            "input_transform": bool(fa.input_transform),
            "last_edited":     fa.last_edited,
        })
        print(f"  {fa.field_number:8.4f}  {fa.label:30s}  {fa.datatype_name:15s}  "
              f"loc={fa.global_subscript:8s}")
```

### 5.2 Storage layout — zero-node density

FileMan stores multiple fields in a single caret-delimited global node.
The zero-node (`"0;n"`) typically holds the most-accessed fields.
Understanding storage layout is essential for direct global reads.

```python
from collections import defaultdict

node_map: dict[str, list[str]] = defaultdict(list)
for row in extended:
    loc = row["storage"]
    if ";" in loc:
        node, piece = loc.split(";", 1)
        node_map[node].append(f"{row['field']:.4f} {row['label']}")

print(f"\nStorage nodes for {fd.label}:")
for node in sorted(node_map.keys()):
    fields_here = node_map[node]
    print(f"  Node {node:6s}: {len(fields_here)} fields — "
          f"{', '.join(fields_here[:4])}"
          + ("..." if len(fields_here) > 4 else ""))
```

### 5.3 Cross-reference inventory

```python
refs = dd.list_cross_refs(file_num)
print(f"\nCross-references for {fd.label}:")
for ref in refs:
    print(f"  '{ref.name}' ({ref.xref_type})  {ref.description[:60]}")
```

### 5.4 Per-package schema batch export

For systematic coverage, export the full schema for every package:

```python
with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()
    dd = DataDictionary(conn)

    out_dir = Path("~/data/vista-fm-browser/output/packages/").expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    for pkg_name, files in fi.files_by_package().items():
        pkg_schema = []
        for fr in files:
            fd = dd.get_file(fr.file_number)
            if not fd:
                continue
            for field_num, fld in fd.fields.items():
                pkg_schema.append({
                    "file_number":  fr.file_number,
                    "file_label":   fr.label,
                    "field_number": field_num,
                    "field_label":  fld.label,
                    "type_code":    fld.datatype_code,
                    "type_name":    fld.datatype_name,
                    "pointer_file": fld.pointer_file,
                })
        safe = pkg_name.replace("/", "_").replace(" ", "_").lower()[:40]
        (out_dir / f"{safe}.json").write_text(
            json.dumps(pkg_schema, indent=2, default=str)
        )
    print(f"Package schemas written to {out_dir}")
```

---

## Phase 6 — Data Coverage Analysis

**Goal:** Determine which defined fields are actually populated in the data
vs. defined-but-unused.  Coverage data shows which fields matter operationally.

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    fi = FileInventory(conn)
    fi.load()

    file_num = 2  # analyse PATIENT first
    fd = dd.get_file(file_num)
    SAMPLE = 500

    field_hits: dict[float, int] = defaultdict(int)
    count = 0
    for entry in reader.iter_entries(file_num, limit=SAMPLE):
        count += 1
        for field_num, val in entry.fields.items():
            if val.strip():
                field_hits[field_num] += 1

    print(f"\nCoverage for {fd.label} (n={count}):")
    print(f"{'Field':8s}  {'Label':30s}  {'%Pop':>6s}  {'Type':15s}")
    print("-" * 65)
    for field_num in sorted(fd.fields.keys()):
        fld = fd.fields[field_num]
        hits = field_hits.get(field_num, 0)
        pct = 100 * hits / count if count else 0
        bar = "▓" * int(pct / 10)
        print(f"  {field_num:6.4f}  {fld.label:30s}  {pct:5.1f}%  "
              f"{fld.datatype_name:15s}  {bar}")
```

Fields with 0% coverage across a large sample are candidates for:
- Deprecation annotation
- Exclusion from schema exports
- Investigation (is the field used only in certain configurations?)

---

## Phase 7 — Normalization Candidate Identification

**Goal:** Apply rules to the schema data collected in Phases 3–6 to produce a
ranked list of normalization targets.

### 7.1 Rule application

```python
candidates = []

# Rule 1: Same label, different types (≥5 occurrences)
for label, rows in label_groups.items():
    types = set(r["datatype_code"] for r in rows)
    if len(rows) >= 5 and len(types) > 1:
        dominant = collections.Counter(
            r["datatype_code"] for r in rows
        ).most_common(1)[0][0]
        candidates.append({
            "rule":           "label_type_conflict",
            "label":          label,
            "occurrences":    len(rows),
            "types":          dict(collections.Counter(
                                  r["datatype_code"] for r in rows)),
            "recommended_type": dominant,
            "priority":       len(rows),
        })

# Rule 2: High-inbound hub file (>10 files reference it)
for tgt, srcs in inbound.items():
    if len(srcs) >= 10:
        fd_label = next((r["file_label"] for r in schema
                         if r["file_number"] == tgt), "?")
        candidates.append({
            "rule":         "hub_file_reference",
            "file":         tgt,
            "label":        fd_label,
            "source_files": len(srcs),
            "priority":     len(srcs),
        })

# Rule 3: DATE field stored as FREE TEXT (type mismatch)
for r in schema:
    if "DATE" in r["field_label"].upper() and r["datatype_code"] == "F":
        candidates.append({
            "rule":         "date_as_free_text",
            "file":         r["file_number"],
            "file_label":   r["file_label"],
            "field":        r["field_number"],
            "field_label":  r["field_label"],
            "package":      r["package"],
            "priority":     5,
        })

# Rule 4: Orphan pointer (points to a file with no data)
# Requires volume data from Phase 2
volume_map = {num: count for count, num, _ in volume}
for r in schema:
    if r["datatype_code"] == "P" and r["pointer_file"]:
        if volume_map.get(r["pointer_file"], -1) == 0:
            candidates.append({
                "rule":         "pointer_to_empty_file",
                "file":         r["file_number"],
                "file_label":   r["file_label"],
                "field":        r["field_number"],
                "field_label":  r["field_label"],
                "target_file":  r["pointer_file"],
                "priority":     3,
            })

candidates.sort(key=lambda x: -x["priority"])
out = Path("~/data/vista-fm-browser/output/normalization_candidates.json").expanduser()
out.write_text(json.dumps(candidates, indent=2, default=str))
print(f"Normalization candidates: {len(candidates):,} written to {out}")
```

---

## Phase 8 — Normalization Report

Produce the final summary report combining all phase outputs.

```python
report = {
    "scope": {
        "total_files":    len(dd.list_files()),
        "total_fields":   len(schema),
        "total_packages": len(fi.list_packages()),
        "files_with_data": len(volume),
        "files_empty":    len(dd.list_files()) - len(volume),
    },
    "volume": {
        "massive_100k_plus": len([v for v in volume if v[0] >= 100_000]),
        "large_10k_100k":    len([v for v in volume if 10_000 <= v[0] < 100_000]),
        "medium_1k_10k":     len([v for v in volume if 1_000 <= v[0] < 10_000]),
        "small_under_1k":    len([v for v in volume if 0 < v[0] < 1_000]),
    },
    "type_distribution":   dict(type_counts),
    "pointer_topology": {
        "total_pointer_fields": len(pointer_fields),
        "hub_files_10plus_refs": len([t for t, s in inbound.items() if len(s) >= 10]),
        "top_hubs": [
            {"file": tgt, "inbound_count": len(srcs)}
            for tgt, srcs in sorted(inbound.items(), key=lambda x: -len(x[1]))[:20]
        ],
    },
    "variety": {
        "set_fields_total": len(set_fields),
        "unique_value_sets": len(seen_sets),
        "shared_value_sets_5plus": len(shared),
        "label_type_conflicts": len([c for c in candidates
                                     if c["rule"] == "label_type_conflict"]),
        "date_as_free_text":   len([c for c in candidates
                                    if c["rule"] == "date_as_free_text"]),
    },
    "normalization_candidates_total": len(candidates),
}

out = Path("~/data/vista-fm-browser/output/normalization_report.json").expanduser()
out.write_text(json.dumps(report, indent=2, default=str))
print(f"Normalization report written to {out}")
```

---

## Analysis Output Reference

| File | Contents | Phase |
|---|---|---|
| `output/inventory.json` | All files, packages, field counts | 1 |
| `output/file_volume.json` | Entry count per file | 2 |
| `output/all_fields.json` | Full schema: all fields across all files | 3 |
| `output/pointer_graph.json` | All pointer edges (FK graph) | 3 |
| `output/packages/` | Per-package field schema JSONs | 5 |
| `output/normalization_candidates.json` | Rule-flagged candidates | 7 |
| `output/normalization_report.json` | Summary report | 8 |

---

## Next Steps

### Immediate: verify DDR LISTER and FINDER against live data

The `list_entries()`, `find_entry()`, and `find_entries()` parameter encodings
are implemented as literal TY=0 params.  Verify against live VEHU:

```python
with VistARpcBroker(host="localhost", port=9430) as broker:
    broker.connect()
    broker.call("XUS SIGNON SETUP")
    broker.authenticate("PRO1234", "PRO1234!!")

    # Browse PATIENT by name
    patients = broker.list_entries(file_number=2, max_entries=20)
    for p in patients:
        print(p.ien, p.external_value)

    # Get all fields for first patient
    if patients:
        fields = broker.gets_entry_data_parsed(
            file_number=2, ien=patients[0].ien, fields="*"
        )
        for f in fields:
            print(f"  {f.field_number}: {f.value}")
```

### Short term: old-style cross-reference analysis

`list_cross_refs()` only reads `^.11` (new-style indexes, FileMan 22.0+).
Old-style cross-references live in `^DD(file, field, 1)` as SET logic.
Add a scanner for `^DD(file, "IX", xref_name)` nodes.

### Short term: variable pointer resolution

For `V` type fields, read `^DD(file, field, "V", n, 0)` to discover which
files each variable pointer can reference.  Map these as multi-target edges
in the pointer graph.

### Short term: sub-file depth traversal

MULTIPLE (`M`) fields point to sub-files.  Recursively enumerate sub-file
fields to map the full parent-child hierarchy.  Sub-files often contain the
highest-volume clinical event data (e.g. lab results within a lab order).

### Medium term: data profiling alongside schema profiling

Once the schema is mapped, sample actual data values:
- **Cardinality** of SET fields (are all defined codes in active use?)
- **Date range** of DATE fields (oldest record, newest, null rate)
- **Text length distribution** of FREE TEXT fields
- **Null rate** per field across a representative sample
- **Referential integrity** of POINTER fields (dangling IENs?)

```python
# Pointer integrity check sketch
fa = dd.get_field_attributes(2, 0.03)   # example pointer field
if fa and fa.pointer_file:
    target_fd = dd.get_file(fa.pointer_file)
    dangling = 0
    for entry in reader.iter_entries(2, limit=500):
        val = entry.fields.get(0.03, "").strip()
        if val and target_fd:
            if not conn.node_exists(f"^{target_fd.global_root}", [val]):
                dangling += 1
    print(f"Dangling pointer rate: {dangling}/500")
```

### Long term: relational schema generation

Generate a SQL or columnar schema from the FileMan data dictionary.
From `fileman-api-wrapper-specification.md` §8:

| FileMan type | SQL type | Notes |
|---|---|---|
| `F` FREE TEXT | `VARCHAR(256)` | Max length from input transform if available |
| `N` NUMERIC | `NUMERIC(15, 4)` | Precision from DECIMAL DEFAULT node |
| `D` DATE/TIME | `TIMESTAMP` | Convert from `YYYMMDD.HHMMSS` |
| `S` SET OF CODES | `VARCHAR(20)` + `CHECK` | Enum from `set_values` dict |
| `P` POINTER | `BIGINT` + FK | FK to target file's IEN column |
| `M` MULTIPLE | child table | Composite PK: `(parent_ien, sub_ien)` |
| `W` WORD PROCESSING | `TEXT` | Read from sub-global nodes |
| `C` COMPUTED | computed column / view | Cannot be stored directly |
| `K` MUMPS | `VARCHAR(512)` | M code stored as text; non-queryable |
| `V` VARIABLE POINTER | `VARCHAR(30)` | Store file-prefix + IEN |
| `DC` COMPUTED DATE | `TIMESTAMP` | Same as `D` |

Each FileMan file → one table (or one Parquet file per partition).
Cross-references → SQL indexes.  Keys → `UNIQUE` constraints.
Sub-files (MULTIPLE) → child tables joined on parent IEN.

### Long term: gRPC wrapper integration

The `fileman-api-wrapper-specification.md` and
`fileman-api-grpc-wrapper-yottadb.md` in `vista-docs/guides/fileman-api-wrapper/`
describe a two-tier gRPC architecture:

1. A **gRPC gateway** (Go, co-located with YottaDB) calling FileMan DBS routines
   via the YottaDB C call-in interface — sub-millisecond latency, no RPC Broker
   dependency
2. **Language-native SDKs** (Python, Go, Rust, TypeScript) as gRPC clients,
   presenting idiomatic typed APIs

The `vista_fm_browser` Python library is the prototype SDK for the Python tier.
Its `VistARpcBroker` currently uses the XWB TCP transport; replacing the transport
layer with a gRPC client call is a contained change that does not affect the
`DataDictionary`, `FileInventory`, or `FileReader` classes at all.

---

## Quick Reference: Common Analysis Queries

```python
# All files that reference a given hub file
target = 2.0  # PATIENT
refs = [(r["file_number"], r["file_label"], r["field_label"])
        for r in schema
        if r["datatype_code"] == "P" and r["pointer_file"] == target]

# All SET fields with a specific code
code = "A"
matches = [(r["file_label"], r["field_label"], r["set_values"][code])
           for r in schema
           if r["datatype_code"] == "S" and code in (r["set_values"] or {})]

# All DATE fields stored as FREE TEXT (normalization error)
bad_dates = [r for r in schema
             if "DATE" in r["field_label"].upper() and r["datatype_code"] == "F"]

# All fields in a package that contain a keyword in their label
pkg = "REGISTRATION"
pkg_files = {fr.file_number for fr in fi.files_by_package().get(pkg, [])}
matches = [r for r in schema
           if r["file_number"] in pkg_files and "SSN" in r["field_label"].upper()]

# All fields stored on node 0 (zero-node) of a specific file
# (requires extended attribute read)
zero_node_fields = [r for r in extended if r["storage"].startswith("0;")]
```
