# FileMan Data Dictionary Analysis Guide

## Purpose

This guide provides a stepwise approach to comprehensive FileMan data dictionary
analysis using the `vista_fm_browser` Python library.  The end goal is normalization
of the data dictionary across all VistA packages: identifying what data exists,
how it is typed and stored, where it overlaps or conflicts across packages, and what
a clean relational or columnar representation would look like.

This is a read-only analysis — no VistA data is modified.  All examples run inside
the VEHU container or via the RPC Broker from the host.

---

## Background: What "Normalization" Means Here

FileMan's data dictionary (`^DD`) defines schema in a package-centric, denormalized
way: each package defines its own files and fields without coordination with other
packages.  The same concept — a patient identifier, a provider name, a clinical date
— may appear in dozens of files under different field numbers, labels, and type codes.

**Normalization analysis** means:

1. **Inventory** — what files and fields exist
2. **Typing** — what data types are actually used, and how consistently
3. **Pointer topology** — how files reference each other (the join graph)
4. **Naming conventions** — how labels cluster across packages
5. **Overlap / redundancy** — the same logical field in multiple files
6. **Coverage** — which fields have data vs. are empty
7. **Standard field patterns** — `.01` NAME, `.03` SEX, `.05` DATE OF BIRTH, etc.

---

## Setup

All examples assume you are inside the VEHU container with YottaDB activated:

```bash
docker-compose up -d
docker exec -it vehu bash
source /etc/yottadb/env
cd /opt/vista-fm-browser
source .venv/bin/activate
python3
```

Or from the host via RPC Broker:

```python
from vista_fm_browser.rpc_broker import VistARpcBroker

broker = VistARpcBroker(host="localhost", port=9430)
broker.connect(app="FM BROWSER", uci="VAH")
broker.call("XUS SIGNON SETUP")
broker.authenticate("PRO1234", "PRO1234!!")
```

Standard imports used throughout this guide:

```python
from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary, FieldAttributes
from vista_fm_browser.inventory import FileInventory, FileRecord
from pathlib import Path
import json, csv, collections
```

---

## Step 1 — Build the File and Package Inventory

The first step is a complete catalog of every FileMan file and its owning VistA package.

```python
with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()

    summary = fi.summary()
    print(f"Total files:    {summary['total_files']}")
    print(f"Total packages: {summary['total_packages']}")
    print(f"Unpackaged:     {summary['unpackaged_files']}")

    # Export the full inventory for offline analysis
    fi.export_json(Path("~/data/vista-fm-browser/output/").expanduser())
```

### What to look for

- **Total file count** — VEHU has ~2,500+ files; a typical production VistA has 3,000+
- **Unpackaged files** — these are sub-files (multiples) and utility files; they will
  not appear in the package map but are important for sub-file analysis
- **Package file distribution** — a few packages (REGISTRATION, LAB, PHARMACY) own
  most files; many packages own 1-5 files

### Output: file inventory by package

```python
grouped = fi.files_by_package()
for pkg_name, files in sorted(grouped.items(), key=lambda x: -len(x[1])):
    if pkg_name == "(unpackaged)":
        continue
    print(f"{pkg_name:40s} {len(files):4d} files")
```

Save the grouped inventory for Step 2:

```python
all_files: list[FileRecord] = fi.list_files()
packaged  = [f for f in all_files if f.package_name]
unpackaged = [f for f in all_files if not f.package_name]
```

---

## Step 2 — Enumerate All Fields Across All Files

Walk `^DD` for every file and collect field metadata.  This is the core schema dump.

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    all_files = [fn for fn, _label in dd.list_files()]

    schema: list[dict] = []
    for file_num in all_files:
        fd = dd.get_file(file_num)
        if fd is None:
            continue
        for field_num, fld in fd.fields.items():
            schema.append({
                "file_number":   file_num,
                "file_label":    fd.label,
                "field_number":  field_num,
                "field_label":   fld.label,
                "datatype_code": fld.datatype_code,
                "datatype_name": fld.datatype_name,
                "pointer_file":  fld.pointer_file,
            })
```

### Write to CSV for spreadsheet analysis

```python
out = Path("~/data/vista-fm-browser/output/all_fields.csv").expanduser()
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=schema[0].keys())
    w.writeheader()
    w.writerows(schema)
print(f"Wrote {len(schema)} field records to {out}")
```

### Quick type distribution

```python
type_counts = collections.Counter(r["datatype_code"] for r in schema)
for code, count in type_counts.most_common():
    name = next((r["datatype_name"] for r in schema if r["datatype_code"] == code), code)
    print(f"  {code:4s}  {name:20s}  {count:6d}")
```

Expected distribution (approximate):

| Type | Count | Notes |
|---|---|---|
| `F` FREE TEXT | ~40% | Most common; variable length, no inherent structure |
| `P` POINTER | ~20% | Join graph edges; critical for topology analysis |
| `D` DATE/TIME | ~10% | FileMan FM format |
| `N` NUMERIC | ~10% | Integer or decimal |
| `S` SET OF CODES | ~8% | Enumeration; finite value set |
| `M` MULTIPLE | ~8% | Sub-file reference; not a leaf field |
| `W` WORD PROCESSING | ~2% | Narrative text; sub-global storage |
| `C` COMPUTED | ~1% | Derived; not in data global |
| `K` MUMPS | <1% | Arbitrary M code |

---

## Step 3 — Analyse Field Labels for Naming Patterns

Extract label-level statistics to identify shared naming conventions.

### Label frequency across all files

```python
label_counter = collections.Counter(r["field_label"] for r in schema)
print("Most common field labels across all files:")
for label, count in label_counter.most_common(30):
    print(f"  {label:40s} {count:5d}")
```

Common results include: `NAME`, `DATE`, `STATUS`, `DESCRIPTION`, `TYPE`,
`ACTIVE`, `INACTIVE DATE`, `PACKAGE PREFIX`.  These represent conceptual
normalization targets.

### Fields at canonical positions

FileMan has informal conventions for field numbers at specific positions:

```python
canonical = {
    0.01: "NAME / identifier",
    0.02: "CATEGORY / TYPE",
    0.03: "DATE OF BIRTH / DATE",
    0.07: "SEX",
    0.09: "SOCIAL SECURITY NUMBER",
}

print("\nCanonical field positions:")
for field_num, expected in canonical.items():
    hits = [r for r in schema if r["field_number"] == field_num]
    labels = collections.Counter(r["field_label"] for r in hits)
    print(f"  Field {field_num:.2f}  ({expected}):")
    for label, cnt in labels.most_common(5):
        print(f"    {label:35s} in {cnt} files")
```

### Label clustering by keyword

```python
keywords = ["NAME", "DATE", "STATUS", "CODE", "TYPE", "NUMBER", "ID", "SSN"]
for kw in keywords:
    matching = [r for r in schema if kw in r["field_label"].upper()]
    files_with = len(set(r["file_number"] for r in matching))
    print(f"  '{kw}' in label: {len(matching):5d} fields across {files_with} files")
```

---

## Step 4 — Map the Pointer Topology

Pointer fields (`P` type) form a directed graph where files are nodes and pointers
are edges.  Mapping this graph reveals the core relational structure of VistA.

### Build the pointer graph

```python
pointer_fields = [r for r in schema if r["datatype_code"] == "P"
                  and r["pointer_file"] is not None]

# file_number → {target_file: [field_labels]}
pointer_graph: dict[float, dict[float, list[str]]] = {}
for r in pointer_fields:
    src = r["file_number"]
    tgt = r["pointer_file"]
    pointer_graph.setdefault(src, {}).setdefault(tgt, []).append(r["field_label"])

# Most-referenced target files (hub files)
inbound: dict[float, int] = collections.Counter()
for src, targets in pointer_graph.items():
    for tgt in targets:
        inbound[tgt] += 1

print("Most-referenced files (hub files in pointer graph):")
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    for file_num, count in inbound.most_common(20):
        fd = dd.get_file(file_num)
        label = fd.label if fd else "?"
        print(f"  File {file_num:8.2f}  {label:40s}  referenced by {count} files")
```

Expected hub files include: PATIENT (2), NEW PERSON (200), HOSPITAL LOCATION (44),
DRUG (50), ICD DIAGNOSIS (80), TERM/CONCEPT (757).

### Outbound pointer count per file

```python
print("\nFiles with most outbound pointers (most denormalized):")
outbound = {src: len(targets) for src, targets in pointer_graph.items()}
for file_num, count in sorted(outbound.items(), key=lambda x: -x[1])[:20]:
    fd = dd.get_file(file_num)
    label = fd.label if fd else "?"
    print(f"  File {file_num:8.2f}  {label:40s}  → {count} target files")
```

### Export the pointer graph

```python
edges = []
for src, targets in pointer_graph.items():
    for tgt, labels in targets.items():
        edges.append({"from": src, "to": tgt, "fields": labels})

out = Path("~/data/vista-fm-browser/output/pointer_graph.json").expanduser()
out.write_text(json.dumps(edges, indent=2))
print(f"Wrote {len(edges)} pointer edges to {out}")
```

---

## Step 5 — Extract Extended Field Attributes

The basic field loop (Step 2) only reads the zero-node.  Extended attributes —
input transforms, help prompts, descriptions, last-edit dates — require reading
additional `^DD` sub-nodes.  Do this for files of interest rather than all files.

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)

    # Extended analysis for a specific file
    file_num = 2   # PATIENT

    fd = dd.get_file(file_num)
    extended = []
    for field_num in fd.fields:
        fa: FieldAttributes | None = dd.get_field_attributes(file_num, field_num)
        if fa is None:
            continue
        extended.append({
            "field_number":    fa.field_number,
            "label":           fa.label,
            "datatype":        fa.datatype_name,
            "global_subscript": fa.global_subscript,   # storage location "0;1"
            "help_prompt":     fa.help_prompt,
            "has_description": bool(fa.description),
            "input_transform": fa.input_transform[:80] if fa.input_transform else "",
            "last_edited":     fa.last_edited,
            "set_values":      json.dumps(fa.set_values) if fa.set_values else "",
            "pointer_file":    fa.pointer_file,
        })

    # Sort by field number for readability
    extended.sort(key=lambda x: x["field_number"])
    for row in extended:
        print(f"  {row['field_number']:8.4f}  {row['label']:30s}  {row['datatype']:15s}"
              f"  loc={row['global_subscript']:8s}  {row['help_prompt'][:40]}")
```

### Storage location analysis

`global_subscript` (e.g. `"0;1"`, `"1;2"`, `".1;3"`) tells you which global node
and which caret-piece stores the field.  This is critical for direct global reading
and for understanding storage efficiency.

```python
# Map node → fields stored there
from collections import defaultdict

node_map: dict[str, list[str]] = defaultdict(list)
for row in extended:
    loc = row["global_subscript"]
    if ";" in loc:
        node = loc.split(";")[0]
        node_map[node].append(f"{row['field_number']} {row['label']}")

print("\nFields per storage node:")
for node, fields in sorted(node_map.items()):
    print(f"  Node {node:6s}: {', '.join(fields[:5])}"
          + ("..." if len(fields) > 5 else ""))
```

---

## Step 6 — Enumerate SET-OF-CODES Values

SET-OF-CODES (`S` type) fields have finite enumerated values.  Collecting all
value sets reveals:
- Standard code lists reused across packages (sex codes, status flags, yes/no)
- Package-specific enumerations
- Inconsistent coding of the same concept (e.g. ACTIVE=1 vs ACTIVE=A vs ACTIVE=Y)

```python
set_fields = [r for r in schema if r["datatype_code"] == "S"]

with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    value_sets: list[dict] = []
    for r in set_fields:
        fa = dd.get_field_attributes(r["file_number"], r["field_number"])
        if fa is None or not fa.set_values:
            continue
        value_sets.append({
            "file_number": r["file_number"],
            "file_label":  r["file_label"],
            "field_number": r["field_number"],
            "field_label":  r["field_label"],
            "values":       fa.set_values,   # {"M": "MALE", "F": "FEMALE"}
        })
```

### Find duplicate value sets (same codes, different fields)

```python
# Canonicalize: frozenset of (code, label) tuples
def canon(sv: dict) -> frozenset:
    return frozenset((k.strip().upper(), v.strip().upper()) for k, v in sv.items())

seen: dict[frozenset, list[dict]] = defaultdict(list)
for vs in value_sets:
    key = canon(vs["values"])
    seen[key].append(vs)

print("Shared value sets (same codes, multiple fields):")
for key, group in sorted(seen.items(), key=lambda x: -len(x[1])):
    if len(group) < 3:
        continue
    sample = dict(list(key)[:4])
    print(f"\n  {sample}  — used in {len(group)} fields:")
    for item in group[:5]:
        print(f"    File {item['file_number']:.0f} {item['file_label']:30s}"
              f" · {item['field_label']}")
```

### Find YES/NO equivalents

```python
yesno_patterns = [{"Y", "N"}, {"1", "0"}, {"YES", "NO"}, {"A", "I"}]
yesno_fields = []
for vs in value_sets:
    codes = set(vs["values"].keys())
    if codes in yesno_patterns or len(codes) == 2:
        yesno_fields.append(vs)
print(f"\nBoolean-equivalent SET fields: {len(yesno_fields)}")
```

---

## Step 7 — Identify Cross-File Name Patterns

Labels that appear in many files often represent the same concept.  Gather them
by label and compare their types and pointer targets.

```python
# Group schema rows by normalized label
label_groups: dict[str, list[dict]] = defaultdict(list)
for r in schema:
    key = r["field_label"].strip().upper()
    label_groups[key].append(r)

# Find labels in 10+ files with inconsistent types
inconsistent = []
for label, rows in label_groups.items():
    if len(rows) < 10:
        continue
    types = set(r["datatype_code"] for r in rows)
    if len(types) > 1:
        type_dist = collections.Counter(r["datatype_code"] for r in rows)
        inconsistent.append({
            "label": label,
            "occurrences": len(rows),
            "types": dict(type_dist),
        })

inconsistent.sort(key=lambda x: -x["occurrences"])
print("Fields with same label but inconsistent types:")
for item in inconsistent[:20]:
    print(f"  {item['label']:35s} in {item['occurrences']:4d} files  "
          f"types={item['types']}")
```

Typical findings:
- `STATUS` appears as `S` (SET), `F` (FREE TEXT), `N` (NUMERIC) in different packages
- `DATE` appears as `D`, `F`, and even `N` in some packages
- `TYPE` appears as `S`, `P`, `F` depending on context

These inconsistencies are prime candidates for normalization annotations.

---

## Step 8 — Analyse Data Coverage

For files with live data, measure which fields are populated vs. empty.  This
distinguishes "defined but never used" from "active fields".

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)

    # Analyse coverage for PATIENT file (file 2)
    file_num = 2
    fd = dd.get_file(file_num)

    # Read up to 200 entries and check field presence
    from vista_fm_browser.file_reader import FileReader
    reader = FileReader(conn, dd)

    field_hits: dict[float, int] = defaultdict(int)
    entry_count = 0

    for entry in reader.iter_entries(file_num, limit=200):
        entry_count += 1
        for field_num, val in entry.fields.items():
            if val.strip():
                field_hits[field_num] += 1

    print(f"Coverage analysis for file {file_num} ({fd.label}), "
          f"{entry_count} entries sampled:")
    for field_num in sorted(fd.fields.keys()):
        fld = fd.fields[field_num]
        hits = field_hits.get(field_num, 0)
        pct = 100 * hits / entry_count if entry_count else 0
        bar = "#" * int(pct / 5)
        print(f"  {field_num:8.4f}  {fld.label:30s}  {pct:5.1f}%  {bar}")
```

Fields with 0% coverage in a large sample are candidates for removal or are
vestigial from a previous installation.

---

## Step 9 — Build the Normalization Candidate Map

Combine findings from Steps 3-8 to identify the strongest normalization candidates.

```python
candidates = []

# Rule 1: Same label, different types
for label, rows in label_groups.items():
    types = set(r["datatype_code"] for r in rows)
    if len(rows) >= 5 and len(types) > 1:
        candidates.append({
            "rule": "label_type_conflict",
            "label": label,
            "files": len(rows),
            "types": sorted(types),
            "recommendation": "standardize to single type",
        })

# Rule 2: Pointer fields pointing to same hub file
pointer_to_hub: dict[float, list[dict]] = defaultdict(list)
for r in schema:
    if r["datatype_code"] == "P" and r["pointer_file"]:
        pointer_to_hub[r["pointer_file"]].append(r)

for hub_file, refs in pointer_to_hub.items():
    if len(refs) >= 10:
        with YdbConnection.connect() as conn:
            dd = DataDictionary(conn)
            hub_fd = dd.get_file(hub_file)
            hub_label = hub_fd.label if hub_fd else str(hub_file)
        candidates.append({
            "rule": "high_inbound_pointer",
            "hub_file": hub_file,
            "hub_label": hub_label,
            "reference_count": len(refs),
            "recommendation": f"canonical FK reference to {hub_label}",
        })

# Rule 3: Fields named "NAME" or "DESCRIPTION" using non-text type
for r in schema:
    if r["field_label"].upper() in ("NAME", "DESCRIPTION", "TITLE"):
        if r["datatype_code"] not in ("F", "W", "C"):
            candidates.append({
                "rule": "name_field_wrong_type",
                "file": r["file_number"],
                "file_label": r["file_label"],
                "field": r["field_number"],
                "actual_type": r["datatype_code"],
                "recommendation": "should be FREE TEXT or WORD PROCESSING",
            })

out = Path("~/data/vista-fm-browser/output/normalization_candidates.json").expanduser()
out.write_text(json.dumps(candidates, indent=2, default=str))
print(f"Wrote {len(candidates)} normalization candidates to {out}")
```

---

## Step 10 — Per-Package Schema Export

For package-level normalization, export the complete schema for each package
separately.  This makes it easy to compare how PHARMACY defines a concept vs.
how REGISTRATION does.

```python
with YdbConnection.connect() as conn:
    fi = FileInventory(conn)
    fi.load()
    dd = DataDictionary(conn)

    output_dir = Path("~/data/vista-fm-browser/output/packages/").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped = fi.files_by_package()
    for pkg_name, files in grouped.items():
        pkg_schema = []
        for fr in files:
            fd = dd.get_file(fr.file_number)
            if fd is None:
                continue
            for field_num, fld in fd.fields.items():
                pkg_schema.append({
                    "file_number":   fr.file_number,
                    "file_label":    fr.label,
                    "field_number":  field_num,
                    "field_label":   fld.label,
                    "type_code":     fld.datatype_code,
                    "type_name":     fld.datatype_name,
                    "pointer_file":  fld.pointer_file,
                    "set_values":    fld.set_values,
                })

        safe_name = pkg_name.replace("/", "_").replace(" ", "_").lower()[:40]
        out = output_dir / f"{safe_name}.json"
        out.write_text(json.dumps(pkg_schema, indent=2, default=str))

    print(f"Package schema files written to {output_dir}")
```

---

## Step 11 — Cross-Package Field Comparison

Compare how specific fields (e.g. patient name, date fields, status flags) are
defined across all packages.  This is the core normalization deliverable.

```python
def compare_field_across_packages(
    schema: list[dict],
    fi: FileInventory,
    label_keyword: str,
) -> list[dict]:
    """Return all fields whose label contains label_keyword, annotated with package."""
    pkg_by_file = {
        fr.file_number: fr.package_name
        for fr in fi.list_files()
    }
    results = []
    for r in schema:
        if label_keyword.upper() not in r["field_label"].upper():
            continue
        r2 = dict(r)
        r2["package"] = pkg_by_file.get(r["file_number"], "(unpackaged)")
        results.append(r2)
    return results

# Example: all DATE-related fields
date_fields = compare_field_across_packages(schema, fi, "DATE")
print(f"\nDATE fields by type:")
type_dist = collections.Counter(r["datatype_code"] for r in date_fields)
for code, count in type_dist.most_common():
    print(f"  {code}: {count}")

# Find packages that store dates as FREE TEXT instead of DATE/TIME
wrong_date = [r for r in date_fields
              if r["datatype_code"] == "F" and "DATE" in r["field_label"].upper()]
for r in wrong_date[:10]:
    print(f"  Package {r['package']:30s}  File {r['file_number']:.0f}"
          f"  Field {r['field_label']}")
```

---

## Step 12 — Produce the Normalization Report

Combine all findings into a structured report.

```python
report = {
    "summary": {
        "total_files":     len(all_files),
        "total_fields":    len(schema),
        "pointer_edges":   len(edges),
        "set_value_sets":  len(value_sets),
        "norm_candidates": len(candidates),
    },
    "type_distribution": dict(type_counts),
    "top_hub_files": [
        {"file_number": fn, "inbound_pointer_count": cnt}
        for fn, cnt in inbound.most_common(20)
    ],
    "shared_value_sets": [
        {
            "codes": dict(list(key)),
            "field_count": len(group),
            "example_fields": [
                f"{g['file_label']} · {g['field_label']}" for g in group[:3]
            ],
        }
        for key, group in sorted(seen.items(), key=lambda x: -len(x[1]))[:20]
    ],
    "label_type_conflicts": [
        c for c in candidates if c["rule"] == "label_type_conflict"
    ][:30],
}

out = Path("~/data/vista-fm-browser/output/normalization_report.json").expanduser()
out.write_text(json.dumps(report, indent=2, default=str))
print(f"Normalization report written to {out}")
```

---

## Next Steps

### Immediate: verify DDR LISTER and FINDER with live data

```python
# Verify list_entries() against live VEHU
with VistARpcBroker(host="localhost", port=9430) as broker:
    broker.connect()
    broker.call("XUS SIGNON SETUP")
    broker.authenticate("PRO1234", "PRO1234!!")

    # Browse PATIENT file
    entries = broker.list_entries(file_number=2, max_entries=10)
    print(f"Patient count (sample): {len(entries)}")
    for e in entries:
        print(f"  IEN={e.ien}  name={e.external_value}")

    # Get full record for first patient via DDR GETS ENTRY DATA
    if entries:
        fields = broker.gets_entry_data_parsed(
            file_number=2, ien=entries[0].ien, fields="*"
        )
        for f in fields:
            print(f"  field {f.field_number}: {f.value}")
```

### Short term: cross-reference analysis depth

1. **Old-style cross-references** — scan `^DD(file, field, 1)` for SET triggers
   and B cross-reference patterns.  The current `list_cross_refs()` only reads
   `^.11` (new-style).  Add a `list_old_xrefs(file_number)` method that reads
   `^DD(file, "IX", xref_name)` nodes.

2. **Variable pointer targets** — for `V` type fields, read `^DD(file, field, "V",n,0)`
   to discover which files each variable pointer can reference.

3. **Multiple (sub-file) depth** — track the full nesting hierarchy.  A MULTIPLE
   field points to a sub-file (e.g. file `2.0361`).  Recursively enumerate sub-file
   fields to map the full object graph.

### Medium term: automated normalization annotation

Build a `NormalizationAnnotator` class that:

1. Reads the full schema (Step 2)
2. Applies the candidate rules (Step 9)
3. Outputs a structured annotation file with confidence scores
4. Can be re-run after DD changes to track normalization drift

```python
# Target API (not yet implemented)
from vista_fm_browser.normalization import NormalizationAnnotator

annotator = NormalizationAnnotator(schema, fi)
annotations = annotator.run()
annotator.export(Path("output/annotations.json"))
```

### Medium term: data profile alongside schema profile

Once the schema is mapped, sample actual data values and compute:

- **Cardinality** of SET fields (are all defined codes in use?)
- **Date range** of DATE fields (oldest, newest, null rate)
- **Text length distribution** of FREE TEXT fields
- **Null rate** per field across all records
- **Referential integrity** of POINTER fields (dangling IENs?)

```python
# Sketch: pointer integrity check
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)

    # Check PATIENT(.03 → file 10 STATE) pointer integrity
    fa = dd.get_field_attributes(2, 0.03)   # example: MARITAL STATUS
    dangling = 0
    for entry in reader.iter_entries(2, limit=500):
        val = entry.fields.get(0.03, "").strip()
        if val and fa and fa.pointer_file:
            target_fd = dd.get_file(fa.pointer_file)
            if target_fd:
                exists = conn.node_exists(
                    f"^{target_fd.global_root}", [val]
                )
                if not exists:
                    dangling += 1
    print(f"Dangling pointer rate for field 0.03: {dangling}/500")
```

### Long term: relational schema generation

Generate a SQL or columnar schema from the FileMan data dictionary:

1. Each FileMan file → one table (or one Parquet file)
2. Field types mapped: `F→VARCHAR`, `N→NUMERIC`, `D→TIMESTAMP`, `S→VARCHAR(enum)`,
   `P→BIGINT FK`, `W→TEXT`, `M→separate table`
3. Pointer fields → foreign key constraints with referential integrity flags
4. SET-OF-CODES fields → `CHECK` constraints or enum types
5. Sub-files (MULTIPLE) → child tables with composite PKs (`(parent_ien, sub_ien)`)

```
FileMan type → SQL type mapping (target):
  F   → VARCHAR(256)
  N   → NUMERIC(15, 4)
  D   → TIMESTAMP
  S   → VARCHAR(20)  -- with CHECK constraint from set_values
  P   → BIGINT       -- with FK to target table
  M   → (child table)
  W   → TEXT
  C   → (computed column or view)
  K   → VARCHAR(512) -- M code stored as text, non-queryable
  V   → VARCHAR(30)  -- variable pointer: store file_prefix + ien
```

---

## Reference: Key Analysis Outputs

| File | Contents | Step |
|---|---|---|
| `output/inventory.json` | All files + packages | 1 |
| `output/all_fields.csv` | Full field schema dump | 2 |
| `output/pointer_graph.json` | Directed pointer edges | 4 |
| `output/normalization_candidates.json` | Rules-based candidates | 9 |
| `output/packages/` | Per-package schema JSONs | 10 |
| `output/normalization_report.json` | Summary report | 12 |

---

## Reference: Analysis Query Patterns

### Find all files that reference a given file

```python
target = 2.0  # PATIENT
refs = [(r["file_number"], r["file_label"], r["field_label"])
        for r in schema
        if r["datatype_code"] == "P" and r["pointer_file"] == target]
```

### Find all SET fields with a specific code

```python
code = "A"  # e.g. "ACTIVE"
matches = [(vs["file_label"], vs["field_label"], vs["values"][code])
           for vs in value_sets
           if code in vs["values"]]
```

### Find fields by data type in a package

```python
pkg = "REGISTRATION"
pkg_files = {fr.file_number for fr in fi.files_by_package().get(pkg, [])}
pkg_date_fields = [r for r in schema
                   if r["file_number"] in pkg_files
                   and r["datatype_code"] == "D"]
```

### Get all fields stored on the zero-node of a file

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    fd = dd.get_file(2)  # PATIENT
    for field_num in fd.fields:
        fa = dd.get_field_attributes(2, field_num)
        if fa and fa.global_subscript.startswith("0;"):
            print(f"  field {field_num} '{fa.label}' at {fa.global_subscript}")
```
