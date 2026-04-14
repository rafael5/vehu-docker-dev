# FileMan Data Dictionary Analysis Guide

## Table of Contents

- [Purpose and Strategy](#purpose-and-strategy)
- [Background: FileMan at a Glance](#background-fileman-at-a-glance)
- [Setup](#setup)
- [Phase 1 — Scope Survey (15 minutes)](#phase-1--scope-survey-15-minutes)
  - [1.0 File #1 — the file registry itself](#10-file-1--the-file-registry-itself)
  - [1.1 Package and file counts](#11-package-and-file-counts)
  - [1.2 Total field count](#12-total-field-count)
  - [1.3 Field type distribution — the variety picture](#13-field-type-distribution--the-variety-picture)
  - [1.4 Export the inventory for offline reference](#14-export-the-inventory-for-offline-reference)
- [Phase 2 — Volume Survey (30 minutes)](#phase-2--volume-survey-30-minutes)
  - [2.1 Entry counts for all files with data](#21-entry-counts-for-all-files-with-data)
  - [2.2 Volume tiers](#22-volume-tiers--classify-files-by-magnitude)
  - [2.3 Data density](#23-data-density--bytes-per-entry-estimate)
- [Phase 3 — Structural Topology (1–2 hours)](#phase-3--structural-topology-12-hours)
  - [3.1 Build the full schema (one pass)](#31-build-the-full-schema-one-pass)
  - [3.2 Pointer graph — hub file identification](#32-pointer-graph--hub-file-identification)
  - [3.3 Pointer graph — outbound density per file](#33-pointer-graph--outbound-density-per-file)
  - [3.4 Export the pointer graph](#34-export-the-pointer-graph)
  - [3.5 Variable pointer files (polymorphic FKs)](#35-variable-pointer-files-polymorphic-fks)
  - [3.6 Multiple (sub-file) depth map](#36-multiple-sub-file-depth-map)
- [Phase 4 — Data Variety and Naming Analysis (1–2 hours)](#phase-4--data-variety-and-naming-analysis-12-hours)
  - [4.1 SET-OF-CODES inventory](#41-set-of-codes-inventory--all-enumerated-value-sets)
  - [4.2 Boolean equivalents](#42-boolean-equivalents--yesno-patterns)
  - [4.3 Label frequency](#43-label-frequency--what-concepts-appear-across-all-packages)
  - [4.4 Label-type consistency](#44-label-type-consistency--same-label-different-types)
  - [4.5 Canonical field positions](#45-canonical-field-positions)
- [Phase 5 — Schema Deep Dive (per file or package)](#phase-5--schema-deep-dive-per-file-or-package)
  - [5.1 Full field attributes for one file](#51-full-field-attributes-for-one-file)
  - [5.2 Storage layout — zero-node density](#52-storage-layout--zero-node-density)
  - [5.3 Cross-reference inventory](#53-cross-reference-inventory)
  - [5.4 Per-package schema batch export](#54-per-package-schema-batch-export)
- [Phase 6 — Data Coverage Analysis](#phase-6--data-coverage-analysis)
- [Phase 7 — Normalization Candidate Identification](#phase-7--normalization-candidate-identification)
- [Phase 8 — Normalization Report](#phase-8--normalization-report)
- [Analysis Output Reference](#analysis-output-reference)
- [Next Steps](#next-steps)
- [Quick Reference: Common Analysis Queries](#quick-reference-common-analysis-queries)
- [Appendix — Visualization Toolkit](#appendix--visualization-toolkit)
  - [Shared design principles](#shared-design-principles)
  - [to_treemap.py — Zoomable Treemap](#to_treemappy--zoomable-treemap)
    - [inventory mode](#inventory-mode)
    - [volume mode](#volume-mode)
    - [schema mode](#schema-mode)
    - [coverage mode](#coverage-mode)
    - [candidates mode](#candidates-mode)
  - [viz_library.py — Visualization Library](#viz_librarypy--visualization-library)
    - [heatmap — package × field-type matrix](#heatmap--package--field-type-matrix)
    - [correlogram — file attribute scatter matrix](#correlogram--file-attribute-scatter-matrix)
    - [wordcloud — field label frequency cloud](#wordcloud--field-label-frequency-cloud)
    - [dendrogram — package → file radial tree](#dendrogram--package--file-radial-tree)
    - [sankey — cross-package pointer flow](#sankey--cross-package-pointer-flow)
    - [bundle — hierarchical edge bundling](#bundle--hierarchical-edge-bundling)

---

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

Key files — meta-files and clinical hub files:

| File # | Name | Global | Owner package | Role |
|---|---|---|---|---|
| **1** | **FILE** | **`^DIC`** | **Kernel (XU)** | **File registry — every file has an entry here** |
| **9.4** | **PACKAGE** | **`^DIC(9.4,`** | **Kernel (XU)** | **Package registry — owns File #1's FILE MULTIPLE** |
| 2 | PATIENT | `^DPT` | Registration (DG) | Clinical hub — referenced by 80+ files |
| 200 | NEW PERSON | `^VA(200,` | Kernel (XU) | Provider/user hub — referenced by 70+ files |
| 4 | INSTITUTION | `^DIC(4,` | Kernel (XU) | Site/facility hub |
| 19 | OPTION | `^DIC(19,` | Kernel (XU) | Menu system hub |
| 50 | DRUG | `^PSDRUG(` | Pharmacy (PS) | Drug catalog hub |
| 63 | LAB DATA | `^LR(` | Laboratory (LR) | Primary lab record store |
| 100 | ORDER | `^OR(100,` | CPRS (OE/RR) | CPRS order hub |
| 101 | PROTOCOL | `^ORD(101,` | Kernel (XU) | Menu/protocol hub |

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

### 1.0 File #1 — the file registry itself

Before using `FileInventory`, understand what you are reading.  **File #1** is the
FILE file — the FileMan meta-file that registers every other FileMan file.  Its global
root is `^DIC`.  Every call to `FileInventory.load()` reads `^DIC(file#, 0)` — it is
reading File #1.

File #1 has its own data dictionary in `^DD(1, ...)`, with fields that describe the
structure of every file entry:

| Field # | Label | Type | Notes |
|---|---|---|---|
| `.01` | NAME | FREE TEXT | File label (the primary name/identifier) |
| `1` | GLOBAL NAME | FREE TEXT | Root global name, e.g. `DPT(` or `PS(50,` |
| `2` | ACCESS | FREE TEXT | FileMan access string |
| `3` | DATE LAST EDITED | DATE | FM date of last schema change |
| `4` | PACKAGE | POINTER (#9.4) | Owning VistA package |
| `5` | NUMBER | NUMERIC | The file number (same as the subscript in `^DIC`) |

Inspect File #1's schema via `DataDictionary`:

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)

    fd1 = dd.get_file(1)
    print(f"File 1: {fd1.label}  global=^DIC  fields={fd1.field_count}")
    print()
    for field_num, fld in sorted(fd1.fields.items()):
        ptr = f" → File #{fld.pointer_file}" if fld.pointer_file else ""
        print(f"  {field_num:7.4f}  {fld.label:30s}  {fld.datatype_name}{ptr}")
```

Read File #1 entries directly through `FileReader` (same data `FileInventory` reads,
accessed via the standard FileMan interface):

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)

    # Total count of registered files
    total = reader.count_entries(1)
    print(f"File #1 has {total} entries (registered FileMan files)")

    # Sample the first 20 entries
    print("\nFirst 20 files in the registry:")
    for entry in reader.iter_entries(1, limit=20):
        name      = entry.fields.get(0.01, "").strip()
        gl_name   = entry.fields.get(1,    "").strip()
        pkg_ien   = entry.fields.get(4,    "").strip()
        print(f"  IEN {entry.ien:>6s}  {name:40s}  ^{gl_name}  pkg_ien={pkg_ien}")
```

Cross-references on File #1 (the `"B"` index and others) are how FileMan resolves a
file name string to a file number.  `^DIC("B", name, file#)` is the classic lookup
that the FileMan `FIND^DIC` API uses internally:

```python
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    xrefs = dd.list_cross_refs(1)
    print(f"File #1 cross-references ({len(xrefs)} total):")
    for xref in xrefs:
        print(f"  '{xref.name}'  ({xref.xref_type})  — {xref.description[:60]}")
```

> **Why this matters for analysis:** The entry count from `reader.count_entries(1)`
> is the authoritative total file count for the VistA instance — the same number
> `FileInventory` produces.  If they differ, the `^DIC` global has entries without
> a zero-node (orphan entries) that `FileInventory` silently skips.  Comparing
> the two counts is a quick data-quality check on the file registry itself.

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

### Phase 1 — Visualization

**Best output:** Two side-by-side charts saved as PNG — package bar and type pie.

> **Setup (once):** `uv add --optional dev matplotlib networkx` inside the container.
> In headless environments (container, server), add `matplotlib.use("Agg")` before
> importing `pyplot` so figures render to PNG without a display.

```python
import matplotlib
matplotlib.use("Agg")   # headless — must come before pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

# --- Chart 1: top packages by file count ---
s = fi.summary()
top = s["top_packages_by_file_count"][:20]
names  = [r["name"][:30] for r in reversed(top)]
counts = [r["file_count"] for r in reversed(top)]

fig, axes = plt.subplots(1, 2, figsize=(16, 8))

ax = axes[0]
bars = ax.barh(names, counts, color="steelblue")
ax.bar_label(bars, padding=3, fontsize=8)
ax.set_xlabel("File count")
ax.set_title(f"Top 20 VistA Packages by File Count\n"
             f"(total: {s['total_files']} files, {s['total_packages']} packages)")
ax.tick_params(axis="y", labelsize=8)

# --- Chart 2: field type distribution pie ---
# type_counts + type_names from section 1.3
ax2 = axes[1]
labels = [f"{code}\n{type_names.get(code, '')} ({count:,})"
          for code, count in type_counts.most_common()]
sizes  = [count for _, count in type_counts.most_common()]
explode = [0.05] * len(sizes)
ax2.pie(sizes, labels=labels, explode=explode, autopct="%1.1f%%",
        startangle=140, textprops={"fontsize": 8})
ax2.set_title("Field Type Distribution across All Files")

plt.tight_layout()
fig.savefig(out_dir / "phase1_scope.png", dpi=150, bbox_inches="tight")
print(f"Chart saved to {out_dir / 'phase1_scope.png'}")
```

**What to look for:**
- If one or two packages dominate the file count, the VistA instance is heavily skewed
  toward those clinical domains.
- The type pie shows your normalization burden at a glance: `F` (FREE TEXT) and `P`
  (POINTER) fractions determine how many fields need type mapping vs FK graph work.
- A large `C` / `K` slice signals executable-code-heavy files that cannot be exported
  to SQL without M runtime support.

**Interactive D3 alternative — zoomable treemap:**
`to_treemap.py` converts the inventory JSON to a click-to-drill D3 treemap where packages
are the top tier, files the second tier, and file size encodes field count. Domain color
families make the clinical footprint visible at a glance.

```bash
# Export inventory first
python3 -c "
from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.inventory import FileInventory
with YdbConnection.connect() as conn:
    fi = FileInventory(conn); fi.load()
    fi.export_json('~/data/vista-fm-browser/output/inventory.json')
"
python scripts/to_treemap.py --mode inventory \
    --input ~/data/vista-fm-browser/output/inventory.json \
    --output ~/data/vista-fm-browser/output/phase1_treemap.html
```

Open `phase1_treemap.html` in a browser — click any package tile to zoom into its files.

**Terminal alternative (no matplotlib):** The `rich` table already produced in 1.1
and 1.3 is the terminal equivalent — use `rich.table.Table` with color columns:

```python
from rich.console import Console
from rich.table import Table

console = Console()
t = Table(title="Field Type Distribution", show_lines=False)
t.add_column("Code", style="cyan", justify="center")
t.add_column("Name", style="white")
t.add_column("Count", style="yellow", justify="right")
t.add_column("%", style="green", justify="right")
total = sum(type_counts.values())
for code, count in type_counts.most_common():
    pct = 100 * count / total
    t.add_row(code, type_names.get(code, ""), f"{count:,}", f"{pct:.1f}%")
console.print(t)
```

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

### Phase 2 — Visualization

**Best output:** Log-scale horizontal bar chart — entry counts span 6+ orders of
magnitude, making a linear scale useless.  Color-code bars by volume tier.

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

TIER_COLORS = {
    "massive": "#d62728",   # red
    "large":   "#ff7f0e",   # orange
    "medium":  "#2ca02c",   # green
    "small":   "#1f77b4",   # blue
    "tiny":    "#aec7e8",   # light blue
}

def tier_color(count: int) -> str:
    if count >= 100_000: return TIER_COLORS["massive"]
    if count >= 10_000:  return TIER_COLORS["large"]
    if count >= 1_000:   return TIER_COLORS["medium"]
    if count >= 100:     return TIER_COLORS["small"]
    return TIER_COLORS["tiny"]

# Top 50 files with data
top50 = [(count, num, label) for count, num, label in volume if count > 0][:50]
labels_plot = [f"{label[:35]} (#{num:.0f})" for _, num, label in reversed(top50)]
counts_plot = [count for count, _, _ in reversed(top50)]
colors      = [tier_color(c) for c in counts_plot]

fig, ax = plt.subplots(figsize=(12, max(10, len(top50) * 0.28)))
ax.barh(labels_plot, counts_plot, color=colors, log=True)
ax.set_xlabel("Entry count (log scale)")
ax.set_title(f"Top {len(top50)} FileMan Files by Entry Count\n"
             f"({len(volume)} files with data of {len(volume) + len(tiers['empty (0)'])} total)")
ax.tick_params(axis="y", labelsize=7)

# Legend
patches = [mpatches.Patch(color=v, label=k) for k, v in TIER_COLORS.items()]
ax.legend(handles=patches, loc="lower right", fontsize=8)

plt.tight_layout()
fig.savefig(out_dir / "phase2_volume.png", dpi=150, bbox_inches="tight")
print(f"Chart saved to {out_dir / 'phase2_volume.png'}")
```

**Tier summary as a pandas DataFrame** (better for CSV export and further analysis):

```python
import pandas as pd

rows = []
for count, num, label in volume:
    if count == 0: tier = "empty"
    elif count < 100: tier = "tiny"
    elif count < 1_000: tier = "small"
    elif count < 10_000: tier = "medium"
    elif count < 100_000: tier = "large"
    else: tier = "massive"
    rows.append({"file_number": num, "label": label,
                 "entry_count": count, "tier": tier})

df = pd.DataFrame(rows)
print(df.groupby("tier")["file_number"].count().rename("files"))
df.to_csv(out_dir / "file_volume.csv", index=False)
print(f"Volume CSV: {out_dir / 'file_volume.csv'}")
```

**What to look for:**
- The massive tier (red) identifies the primary clinical record stores — these demand
  direct global reads or streaming extraction, not record-at-a-time RPC calls.
- A large empty tier (>50% of files) is normal for VEHU (demo data) but signals which
  files are safe to skip in schema analysis.
- Outliers with unexpectedly high counts (e.g. a configuration file with 500K entries)
  indicate audit logs or temporary data masquerading as configuration.

**Interactive D3 alternative — volume treemap:**
The `volume` mode sizes each file tile by its entry count (log-scale), making the
massive-tier files impossible to miss.

```bash
# Assumes file_volume.csv produced in Phase 2 pandas block
python scripts/to_treemap.py --mode volume \
    --input ~/data/vista-fm-browser/output/file_volume.csv \
    --output ~/data/vista-fm-browser/output/phase2_volume_treemap.html
```

**Cross-package flow — Sankey:**
After exporting `all_fields.json` (schema phase), `viz_library.py sankey` renders a
package-to-package pointer flow diagram showing which domains depend on which.

```bash
python scripts/viz_library.py sankey \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --inv    ~/data/vista-fm-browser/output/inventory.json \
    --output ~/data/vista-fm-browser/output/phase2_sankey.html
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

### Phase 3 — Visualization

**Best output:** NetworkX directed graph of hub files.  The full graph (3,000+ nodes,
10,000+ edges) is too dense to render legibly — filter to hub files and their
immediate neighbors.

**Install:** `uv add --optional dev networkx` (once).

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

# Build directed graph from pointer edges
G = nx.DiGraph()
for r in pointer_fields:
    G.add_edge(r["file_number"], r["pointer_file"],
               field_label=r["field_label"])

print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# Subgraph: keep only hub files (≥10 inbound) + their direct sources
hub_file_nums = {tgt for tgt, srcs in inbound.items() if len(srcs) >= 10}
neighbors = set()
for h in hub_file_nums:
    neighbors.update(G.predecessors(h))   # files that point to this hub
sub_nodes = hub_file_nums | neighbors
H = G.subgraph(sub_nodes).copy()

# Node labels: file number + short label
file_labels: dict[float, str] = {
    fr.file_number: f"#{fr.file_number:.0f}\n{fr.label[:18]}"
    for fr in fi.list_files()
}

# Node sizes: proportional to inbound degree in full graph
sizes = [
    3000 + 500 * len(inbound.get(n, set()))
    if n in hub_file_nums else 600
    for n in H.nodes()
]
colors = ["#d62728" if n in hub_file_nums else "#aec7e8" for n in H.nodes()]

pos = nx.spring_layout(H, k=2.5, seed=42)
fig, ax = plt.subplots(figsize=(20, 14))
nx.draw_networkx_nodes(H, pos, node_size=sizes, node_color=colors,
                       alpha=0.85, ax=ax)
nx.draw_networkx_labels(H, pos,
                        labels={n: file_labels.get(n, str(n)) for n in H.nodes()},
                        font_size=6, ax=ax)
nx.draw_networkx_edges(H, pos, alpha=0.2, arrows=True,
                       arrowsize=8, edge_color="gray", ax=ax)
ax.set_title(f"FileMan Pointer Graph — Hub Files (≥10 inbound) + Neighbors\n"
             f"Red = hub file, Blue = source file", fontsize=12)
ax.axis("off")
plt.tight_layout()
fig.savefig(out_dir / "phase3_pointer_graph.png", dpi=150, bbox_inches="tight")
print(f"Graph saved to {out_dir / 'phase3_pointer_graph.png'}")
```

**Package-to-package pointer matrix** — which packages reference which (heatmap):

```python
import pandas as pd

pkg_pairs: dict[tuple[str, str], int] = collections.Counter()
for r in pointer_fields:
    src_pkg = pkg_by_file.get(r["file_number"],   "(unpackaged)")
    tgt_pkg = pkg_by_file.get(r["pointer_file"],  "(unpackaged)")
    if src_pkg != tgt_pkg:
        pkg_pairs[(src_pkg, tgt_pkg)] += 1

# Build matrix for top 15 packages by cross-package pointer count
top_pkgs = [p for p, _ in
            collections.Counter(
                {p: sum(v for (s, t), v in pkg_pairs.items() if s == p or t == p)
                 for p in set(s for s, _ in pkg_pairs) | set(t for _, t in pkg_pairs)}
            ).most_common(15)]

matrix = pd.DataFrame(0, index=top_pkgs, columns=top_pkgs)
for (src, tgt), cnt in pkg_pairs.items():
    if src in top_pkgs and tgt in top_pkgs:
        matrix.loc[src, tgt] += cnt

fig, ax = plt.subplots(figsize=(14, 12))
im = ax.imshow(matrix.values, cmap="YlOrRd", aspect="auto")
ax.set_xticks(range(len(top_pkgs)))
ax.set_yticks(range(len(top_pkgs)))
ax.set_xticklabels([p[:20] for p in top_pkgs], rotation=45, ha="right", fontsize=7)
ax.set_yticklabels([p[:20] for p in top_pkgs], fontsize=7)
plt.colorbar(im, ax=ax, label="Cross-package pointer count")
ax.set_title("Cross-Package Pointer Dependency Matrix\n(row→column = 'row package points to column package')")
plt.tight_layout()
fig.savefig(out_dir / "phase3_pkg_matrix.png", dpi=150, bbox_inches="tight")
print(f"Package matrix saved to {out_dir / 'phase3_pkg_matrix.png'}")
```

**Export as Graphviz DOT** (for rendering with `dot -Tsvg`):

```python
dot_lines = ["digraph vista_pointers {", "  rankdir=LR;",
             "  node [shape=box fontsize=9];"]
for n in hub_file_nums:
    lbl = file_labels.get(n, str(n)).replace("\n", " ")
    dot_lines.append(f'  "{n}" [label="{lbl}" style=filled fillcolor=salmon];')
for u, v in H.edges():
    dot_lines.append(f'  "{u}" -> "{v}";')
dot_lines.append("}")
(out_dir / "phase3_pointer_graph.dot").write_text("\n".join(dot_lines))
print("DOT file written — render with: dot -Tsvg phase3_pointer_graph.dot -o graph.svg")
```

**What to look for:**
- Hub files (high inbound) with low volume (Phase 2) are reference data — normalize first.
- Dense cross-package edges between two packages indicate a tight coupling that must be
  preserved in any migration or API design.
- Islands (nodes with no paths to hub files) are standalone utility files — lowest
  integration priority.

**Interactive D3 alternatives:**

*Hierarchical edge bundling* — renders files arranged by package around a circle with
curved pointer edges. The bundle tension (`beta=0.85`) routes co-package edges close to
the circumference, making cross-package dependencies visually obvious. Click any node to
highlight its connections.

```bash
python scripts/viz_library.py bundle \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --inv    ~/data/vista-fm-browser/output/inventory.json \
    --output ~/data/vista-fm-browser/output/phase3_bundle.html \
    --max-files 200
```

*Sankey (cross-package flow)* — same command as Phase 2; re-run after Phase 3 to see
whether inter-package pointer counts match your hub-file findings.

*Package heatmap* — renders the package × package dependency matrix as a D3 heatmap
more readable than the matplotlib version at large package counts.

```bash
python scripts/viz_library.py heatmap \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/phase3_pkg_heatmap.html
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

### Phase 4 — Visualization

**Best outputs:**
- Horizontal bar for top label frequencies (shows shared vocabulary)
- Heatmap of label × type (shows inconsistency at a glance)

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

# --- Chart 1: top 40 field label frequencies ---
top_labels_list = label_counter.most_common(40)
lnames = [l for l, _ in reversed(top_labels_list)]
lcounts = [c for _, c in reversed(top_labels_list)]

fig, ax = plt.subplots(figsize=(10, 12))
ax.barh(lnames, lcounts, color="steelblue")
ax.set_xlabel("Number of fields with this label (across all files)")
ax.set_title("Top 40 Field Labels — Shared Vocabulary Across VistA Packages")
ax.tick_params(axis="y", labelsize=8)
plt.tight_layout()
fig.savefig(out_dir / "phase4_label_frequency.png", dpi=150, bbox_inches="tight")

# --- Chart 2: label-type inconsistency heatmap ---
# For the top 30 inconsistent labels, show type distribution as a heatmap
top_inconsistent = sorted(
    inconsistent, key=lambda x: -x["occurrences"]
)[:30]
all_types = ["F", "P", "S", "D", "N", "M", "W", "C", "K", "V"]
rows_data = []
for item in top_inconsistent:
    total = item["occurrences"]
    row = [item["types"].get(t, 0) / total for t in all_types]
    rows_data.append(row)

mat = np.array(rows_data)
ylabels = [item["label"][:35] for item in top_inconsistent]

fig2, ax2 = plt.subplots(figsize=(12, 10))
im = ax2.imshow(mat, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
ax2.set_xticks(range(len(all_types)))
ax2.set_yticks(range(len(ylabels)))
ax2.set_xticklabels(all_types, fontsize=9)
ax2.set_yticklabels(ylabels, fontsize=7)
plt.colorbar(im, ax=ax2, label="Fraction of occurrences with this type")
ax2.set_title("Label-Type Inconsistency — Same Label, Different Types\n"
              "(darker = most common type for that label; mixed row = inconsistent)")
plt.tight_layout()
fig2.savefig(out_dir / "phase4_label_type_heatmap.png", dpi=150, bbox_inches="tight")
print(f"Charts saved to {out_dir}")
```

**SET value cluster similarity matrix** — identify fields that share the same value
set even when the labels differ:

```python
# Jaccard similarity between the top 30 most-used SET value sets
top_sets = [(key, grp) for key, grp in sorted(
    seen_sets.items(), key=lambda x: -len(x[1]))[:30]]
n = len(top_sets)
sim = np.zeros((n, n))
for i, (ki, _) in enumerate(top_sets):
    for j, (kj, _) in enumerate(top_sets):
        if i == j:
            sim[i, j] = 1.0
        else:
            inter = len(ki & kj)
            union = len(ki | kj)
            sim[i, j] = inter / union if union else 0

set_labels_plot = [
    ", ".join(f"{k}={v}" for k, v in list(dict(key))[:2])[:25]
    for key, _ in top_sets
]

fig3, ax3 = plt.subplots(figsize=(12, 11))
im3 = ax3.imshow(sim, cmap="Blues", vmin=0, vmax=1)
ax3.set_xticks(range(n)); ax3.set_yticks(range(n))
ax3.set_xticklabels(set_labels_plot, rotation=45, ha="right", fontsize=6)
ax3.set_yticklabels(set_labels_plot, fontsize=6)
plt.colorbar(im3, ax=ax3, label="Jaccard similarity")
ax3.set_title("SET Value Set Similarity (top 30 most-used)\n"
              "1.0 = identical value sets used under different labels")
plt.tight_layout()
fig3.savefig(out_dir / "phase4_set_similarity.png", dpi=150, bbox_inches="tight")
print(f"SET similarity matrix saved.")
```

**What to look for:**
- Labels appearing in 100+ fields are cross-package vocabulary candidates — good targets
  for a shared `CONCEPT` table or enum definition.
- A row in the label-type heatmap that is half `F` and half `D` means "DATE" is stored
  as free text in some packages and as a proper date in others — a normalization error.
- SET value pairs with Jaccard > 0.8 but different labels are synonyms — candidates for
  a single shared enumeration.

**Interactive D3 alternatives:**

*Word cloud* — renders all field labels as a D3 word cloud where word size encodes
frequency and color encodes the dominant datatype. Immediately surfaces the shared
vocabulary of the schema.

```bash
python scripts/viz_library.py wordcloud \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/phase4_wordcloud.html \
    --top-n 200
```

*Field-type heatmap* — renders the package × field-type matrix (each cell = count of
fields of that type in that package). Hover for exact counts; per-type color scaling.

```bash
python scripts/viz_library.py heatmap \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/phase4_type_heatmap.html
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

### Phase 5 — Visualization

**Best output:** Attribute completeness heatmap — each field is a row, each
documentation attribute (help text, description, input transform, last edited) is a
column.  Shows at a glance which fields are well-defined vs schema skeletons.

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

# `extended` is the list built in section 5.1 for one file
# Rebuild as a matrix: rows=fields, cols=attributes

attrs = ["has_description", "input_transform", "has_description",
         "last_edited", "help_prompt"]
attr_labels = ["Description", "Input Transform", "Set Values",
               "Last Edited", "Help Prompt"]

def has_val(row, key):
    v = row.get(key)
    if v is None or v == "" or v is False: return 0
    return 1

def has_set(row):
    sv = row.get("set_values") or {}
    return 1 if sv else 0

mat = np.array([
    [has_val(r, "has_description"),
     has_val(r, "input_transform"),
     has_set(r),
     1 if row.get("last_edited") else 0,
     has_val(r, "help_prompt")]
    for row, r in zip(extended, extended)
], dtype=float)

field_names = [f"{r['field']:.4f} {r['label'][:30]}" for r in extended]

fig, ax = plt.subplots(figsize=(10, max(6, len(field_names) * 0.22)))
im = ax.imshow(mat, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
ax.set_xticks(range(len(attr_labels)))
ax.set_yticks(range(len(field_names)))
ax.set_xticklabels(attr_labels, fontsize=9)
ax.set_yticklabels(field_names, fontsize=6)
plt.colorbar(im, ax=ax, label="Present (1) / Absent (0)", shrink=0.4)
ax.set_title(f"Field Documentation Completeness — {fd.label} (File #{file_num})\n"
             "Green = attribute present, Red = missing")
plt.tight_layout()
fig.savefig(out_dir / f"phase5_schema_{int(file_num)}.png",
            dpi=150, bbox_inches="tight")
print(f"Schema heatmap saved.")
```

**Storage layout treemap** — shows how many fields share each global node, useful for
understanding read efficiency:

```python
# `node_map` from section 5.2
from rich.table import Table
from rich.console import Console

console = Console()
t = Table(title=f"Storage Nodes — {fd.label}", show_lines=True)
t.add_column("Node", style="cyan", justify="center", width=8)
t.add_column("Fields", style="yellow", justify="right", width=6)
t.add_column("Field list", style="white")
for node in sorted(node_map.keys(), key=lambda x: (len(x), x)):
    fields_str = ", ".join(node_map[node][:6])
    if len(node_map[node]) > 6:
        fields_str += f" … +{len(node_map[node]) - 6} more"
    t.add_row(node, str(len(node_map[node])), fields_str)
console.print(t)
```

**What to look for:**
- Fields where `has_description=0` and `input_transform=0` and `help_prompt=0` are
  undocumented schema stubs — present in the DD but never fully defined.
- A cluster of fields all edited on the same date (from `last_edited`) indicates a bulk
  migration or retroactive schema change — investigate what changed.
- Node 0 holding 10+ fields means reads from that file are very efficient (single global
  get); fields spread across many nodes require multiple gets per entry.

**Interactive D3 alternative — package dendrogram:**
`viz_library.py dendrogram` renders a radial cluster where packages are the inner ring
and files are the outer leaves. Node size encodes field count. Zoom and pan to explore
a specific package's file cluster.

```bash
python scripts/viz_library.py dendrogram \
    --input ~/data/vista-fm-browser/output/inventory.json \
    --output ~/data/vista-fm-browser/output/phase5_dendrogram.html \
    --max-files 300
```

The `schema` treemap mode gives a per-file view of field counts nested inside packages:

```bash
python scripts/to_treemap.py --mode schema \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/phase5_schema_treemap.html
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

### Phase 6 — Visualization

**Best output:** Sorted horizontal bar chart — fields ordered by population %, color-
coded by coverage tier.  Instantly separates essential fields from dormant schema.

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

# `field_hits` and `count` (sample size) are from the Phase 6 code block
# `fd` is the FileDef for the file being analyzed

rows_cov = []
for field_num in sorted(fd.fields.keys()):
    fld = fd.fields[field_num]
    hits = field_hits.get(field_num, 0)
    pct = 100 * hits / count if count else 0
    rows_cov.append((pct, field_num, fld.label, fld.datatype_name))

rows_cov.sort(key=lambda x: x[0])  # ascending so highest is at top

def cov_color(pct):
    if pct >= 80: return "#2ca02c"   # green — well populated
    if pct >= 20: return "#ff7f0e"   # orange — partially populated
    return "#d62728"                  # red — sparse / unused

labels_cov  = [f"{num:.4f} {lbl[:28]} ({dtype[:3]})"
               for _, num, lbl, dtype in rows_cov]
pcts        = [p for p, *_ in rows_cov]
bar_colors  = [cov_color(p) for p in pcts]

fig, ax = plt.subplots(figsize=(11, max(8, len(labels_cov) * 0.22)))
bars = ax.barh(labels_cov, pcts, color=bar_colors)
ax.set_xlim(0, 105)
ax.set_xlabel("% of sampled entries where field is populated")
ax.set_title(f"Field Coverage — {fd.label} (File #{file_num})\n"
             f"n={count} sampled entries  |  "
             "Green ≥80%, Orange 20–80%, Red <20%")
ax.tick_params(axis="y", labelsize=7)
ax.axvline(x=80, color="green",  linestyle="--", alpha=0.4, linewidth=0.8)
ax.axvline(x=20, color="orange", linestyle="--", alpha=0.4, linewidth=0.8)
plt.tight_layout()
fig.savefig(out_dir / f"phase6_coverage_{int(file_num)}.png",
            dpi=150, bbox_inches="tight")
print(f"Coverage chart saved.")
```

**Multi-file coverage comparison** — run Phase 6 for multiple important files and
compare population rates for the `.01` NAME field and other key positions:

```python
import pandas as pd

key_files = [(2, "PATIENT"), (200, "NEW PERSON"), (50, "DRUG"), (44, "HOSP LOC")]
summary_rows = []
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    for fnum, flabel in key_files:
        fd2 = dd.get_file(fnum)
        if not fd2: continue
        hits2: dict[float, int] = {}
        n2 = 0
        for entry in reader.iter_entries(fnum, limit=200):
            n2 += 1
            for fn, val in entry.fields.items():
                if val.strip(): hits2[fn] = hits2.get(fn, 0) + 1
        for fn, fld in fd2.fields.items():
            pct = 100 * hits2.get(fn, 0) / n2 if n2 else 0
            summary_rows.append({"file": flabel, "field": fld.label,
                                  "field_num": fn, "pct": pct})

df_cov = pd.DataFrame(summary_rows)
pivot = df_cov[df_cov["field_num"] == 0.01].pivot(
    index="file", columns="field", values="pct"
)
print("\n.01 NAME field coverage by file:")
print(pivot.to_string())
df_cov.to_csv(out_dir / "phase6_coverage_multi.csv", index=False)
```

**What to look for:**
- Fields with 0% coverage in 500+ entries are strong deprecation candidates; check
  before excluding — some fields only populate under specific clinical workflows.
- Fields with >95% coverage and `F` (FREE TEXT) type that contain mostly numeric-looking
  values are prime type-normalization targets.
- If the `.01` (NAME) field has <100% coverage, the file has orphan or header-only
  entries that may indicate data quality issues in the source system.

**Interactive D3 alternative — coverage treemap:**
`to_treemap.py --mode coverage` colors each file tile by its average field population
rate (green = well-populated, red = sparse). Drill down from package → file to see
which clinical areas have the most complete data.

```bash
# Requires phase6_coverage_multi.csv produced by the pandas block above
python scripts/to_treemap.py --mode coverage \
    --input ~/data/vista-fm-browser/output/phase6_coverage_multi.csv \
    --output ~/data/vista-fm-browser/output/phase6_coverage_treemap.html
```

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

### Phase 7 — Visualization

**Best outputs:**
- Grouped bar chart: candidate count by rule type (shows which rules fire most)
- Scatter plot: priority vs occurrences, colored by rule, labeled by file/label

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

out_dir = Path("~/data/vista-fm-browser/output/").expanduser()

df_cands = pd.DataFrame(candidates)

# --- Chart 1: candidates by rule type ---
rule_counts = df_cands["rule"].value_counts()

fig, axes = plt.subplots(1, 2, figsize=(16, 7))

ax = axes[0]
rule_colors = {
    "label_type_conflict":    "#d62728",
    "hub_file_reference":     "#ff7f0e",
    "date_as_free_text":      "#9467bd",
    "pointer_to_empty_file":  "#1f77b4",
}
colors_bar = [rule_colors.get(r, "gray") for r in rule_counts.index]
bars = ax.bar(rule_counts.index, rule_counts.values, color=colors_bar)
ax.bar_label(bars, padding=3)
ax.set_xlabel("Rule")
ax.set_ylabel("Candidate count")
ax.set_title("Normalization Candidates by Rule Type")
ax.tick_params(axis="x", rotation=20, labelsize=8)

# --- Chart 2: scatter priority vs occurrences ---
ax2 = axes[1]
for rule, grp in df_cands.groupby("rule"):
    if "occurrences" in grp.columns:
        x = grp["occurrences"].fillna(grp["priority"])
    else:
        x = grp["priority"]
    y = grp["priority"]
    ax2.scatter(x, y, label=rule, alpha=0.6,
                color=rule_colors.get(rule, "gray"), s=40)

ax2.set_xlabel("Occurrences (field count or source file count)")
ax2.set_ylabel("Priority score")
ax2.set_title("Normalization Candidates — Priority vs Occurrences")
ax2.legend(fontsize=8)

plt.tight_layout()
fig.savefig(out_dir / "phase7_candidates.png", dpi=150, bbox_inches="tight")
print(f"Candidates chart saved to {out_dir / 'phase7_candidates.png'}")
```

**Top candidates as a `rich` table** — for terminal review without matplotlib:

```python
from rich.console import Console
from rich.table import Table

console = Console()
t = Table(title=f"Top 30 Normalization Candidates (of {len(candidates)})",
          show_lines=False)
t.add_column("Priority", style="red",    justify="right", width=8)
t.add_column("Rule",     style="yellow", width=28)
t.add_column("Label/File",style="white", width=35)
t.add_column("Detail",   style="dim",    width=30)

for c in candidates[:30]:
    rule  = c["rule"]
    pri   = str(c["priority"])
    if rule == "label_type_conflict":
        name   = c.get("label", "")
        detail = str(c.get("types", ""))
    elif rule == "hub_file_reference":
        name   = c.get("label", "")
        detail = f"{c.get('source_files', '')} files reference it"
    elif rule == "date_as_free_text":
        name   = c.get("field_label", "")
        detail = f"File {c.get('file', '')} [{c.get('package', '')}]"
    else:
        name   = c.get("field_label", "")
        detail = f"→ empty File {c.get('target_file', '')}"
    t.add_row(pri, rule, name, detail)

console.print(t)
```

**What to look for:**
- If `label_type_conflict` dominates, the normalization work is primarily semantic
  (agreeing on canonical types for shared concepts) rather than structural.
- If `hub_file_reference` dominates with very high source counts (>50), those hub files
  are the load-bearing pillars of any relational schema design.
- If `pointer_to_empty_file` is large, many FK relationships are theoretically defined
  but point to unused reference tables — safe to drop in an export schema.

**Interactive D3 alternative — candidates treemap:**
`to_treemap.py --mode candidates` renders each candidate as a tile, grouped by rule type
at the top level and by package at the second level.  Tile size encodes priority score.

```bash
python scripts/to_treemap.py --mode candidates \
    --input ~/data/vista-fm-browser/output/normalization_candidates.json \
    --output ~/data/vista-fm-browser/output/phase7_candidates_treemap.html
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

### Phase 8 — Visualization

**Best output:** A `rich` Panel dashboard for immediate terminal consumption + a single
HTML page rendered by Flask that summarises all eight phases in one shareable document.

**Terminal dashboard:**

```python
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich import box

console = Console()

def stat_panel(title, rows):
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim")
    t.add_column(style="bold cyan", justify="right")
    for label, value in rows:
        t.add_row(label, str(value))
    return Panel(t, title=f"[bold]{title}[/bold]", border_style="blue")

scope_panel = stat_panel("Scope", [
    ("Total files",     report["scope"]["total_files"]),
    ("Total fields",    report["scope"]["total_fields"]),
    ("Packages",        report["scope"]["total_packages"]),
    ("Files with data", report["scope"]["files_with_data"]),
    ("Empty files",     report["scope"]["files_empty"]),
])

volume_panel = stat_panel("Volume Tiers", [
    ("Massive (>100K)", report["volume"]["massive_100k_plus"]),
    ("Large (10K–100K)",report["volume"]["large_10k_100k"]),
    ("Medium (1K–10K)", report["volume"]["medium_1k_10k"]),
    ("Small (<1K)",     report["volume"]["small_under_1k"]),
])

topo_panel = stat_panel("Topology", [
    ("Pointer fields",  report["pointer_topology"]["total_pointer_fields"]),
    ("Hub files (≥10)", report["pointer_topology"]["hub_files_10plus_refs"]),
])

variety_panel = stat_panel("Variety", [
    ("SET fields",           report["variety"]["set_fields_total"]),
    ("Unique value sets",    report["variety"]["unique_value_sets"]),
    ("Shared sets (≥5)",     report["variety"]["shared_value_sets_5plus"]),
    ("Label-type conflicts", report["variety"]["label_type_conflicts"]),
    ("Date-as-text fields",  report["variety"]["date_as_free_text"]),
])

norm_panel = stat_panel("Normalization", [
    ("Total candidates", report["normalization_candidates_total"]),
])

console.print()
console.print(Columns([scope_panel, volume_panel, topo_panel,
                       variety_panel, norm_panel], equal=True))

# Top 10 hubs
hub_t = Table(title="Top Hub Files", box=box.SIMPLE, show_header=True)
hub_t.add_column("File #", style="cyan", justify="right")
hub_t.add_column("Label", style="white")
hub_t.add_column("Inbound", style="yellow", justify="right")
with YdbConnection.connect() as conn:
    dd = DataDictionary(conn)
    for h in report["pointer_topology"]["top_hubs"][:10]:
        fd = dd.get_file(h["file"])
        hub_t.add_row(str(h["file"]),
                      fd.label if fd else "?",
                      str(h["inbound_count"]))
console.print(hub_t)
```

**HTML report via Flask** — render `normalization_report.json` as a self-contained
HTML page.  Add a route to `web/app.py`:

```python
# In web/app.py — add this route to the Flask factory
@app.route("/report")
def analysis_report():
    import json
    report_path = (
        Path("~/data/vista-fm-browser/output/normalization_report.json")
        .expanduser()
    )
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    candidates_path = (
        Path("~/data/vista-fm-browser/output/normalization_candidates.json")
        .expanduser()
    )
    candidates = (
        json.loads(candidates_path.read_text())[:50]
        if candidates_path.exists() else []
    )
    return render_template(
        "report.html", report=report, candidates=candidates
    )
```

Then visit `http://localhost:5000/report` from a browser on the host.  The template
(`web/templates/report.html`) needs only basic Jinja2 — `{{ report.scope.total_files }}`
style interpolation.  Flask is already a project dependency.

**What to look for:**
- The dashboard should be readable in under 30 seconds.  If it takes longer to parse,
  the panels are overloaded — break the report into phase-specific pages.
- A `normalization_candidates_total` in the thousands is normal for a full VistA instance;
  filter to `priority ≥ 10` for the actionable short list.
- The ratio `files_with_data / total_files` tells you how much of the defined schema is
  actually in active use.  In VEHU (demo system), expect ~60%.  In production, expect
  >85%.

**Interactive D3 alternative — cross-phase correlogram:**
After all phases complete, `viz_library.py correlogram` renders a scatter matrix of
per-file metrics (field_count, pointer_count, set_count, multiple_count, entry_count).
Off-diagonal cells show scatter plots with Pearson r; diagonals show histograms. Color
by clinical domain. This is the highest-level interactive summary of the full analysis.

```bash
python scripts/viz_library.py correlogram \
    --input  ~/data/vista-fm-browser/output/inventory.json \
    --schema ~/data/vista-fm-browser/output/all_fields.json \
    --volume ~/data/vista-fm-browser/output/file_volume.csv \
    --output ~/data/vista-fm-browser/output/phase8_correlogram.html
```

---

## Analysis Output Reference

| File | Contents | Phase |
|---|---|---|
| `output/inventory.json` | All files, packages, field counts | 1 |
| `output/phase1_scope.png` | Package bar + field type pie | 1 |
| `output/file_volume.json` | Entry count per file | 2 |
| `output/file_volume.csv` | Volume tiers as CSV (pandas) | 2 |
| `output/phase2_volume.png` | Log-scale bar, color by tier | 2 |
| `output/all_fields.json` | Full schema: all fields across all files | 3 |
| `output/pointer_graph.json` | All pointer edges (FK graph) | 3 |
| `output/phase3_pointer_graph.png` | Hub file NetworkX graph | 3 |
| `output/phase3_pointer_graph.dot` | Graphviz DOT for SVG rendering | 3 |
| `output/phase3_pkg_matrix.png` | Package-to-package pointer heatmap | 3 |
| `output/phase4_label_frequency.png` | Top label frequency bar | 4 |
| `output/phase4_label_type_heatmap.png` | Label × type inconsistency heatmap | 4 |
| `output/phase4_set_similarity.png` | SET value set Jaccard similarity | 4 |
| `output/phase5_schema_<N>.png` | Field documentation completeness heatmap | 5 |
| `output/phase6_coverage_<N>.png` | Field population % bar, color by tier | 6 |
| `output/phase6_coverage_multi.csv` | Multi-file coverage comparison | 6 |
| `output/phase7_candidates.png` | Candidates by rule + priority scatter | 7 |
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

---

## Appendix — Visualization Toolkit

Two standalone Python scripts generate interactive browser-based visualizations from the
JSON and CSV files produced at each analysis phase.  Both scripts require only the Python
standard library — no matplotlib, pandas, or extra packages.  D3 v7 is loaded from CDN
at view time, so the generated HTML files require internet access when opened.

```
scripts/to_treemap.py   — 5 modes, all zoomable treemap output
scripts/viz_library.py  — 6 subcommands, each a distinct visualization type
```

### Shared design principles

**Domain color coding** — both tools map VistA package namespaces to 14 clinical
domains and assign a consistent hex color to each domain across all visualizations.
Packages not matched by a known prefix are colored "Other" (slate grey).

| Domain | Color | Key namespaces |
|---|---|---|
| Registration/ADT | steel blue `#4e79a7` | DG, DPT, ADT, MAS, PX |
| Scheduling | sky blue `#76b7d4` | SD, SC, SDAM |
| Laboratory | amber `#f28e2b` | LR, LA, CH, MI |
| Radiology | peach `#ffbe7d` | RA, MAG |
| Pharmacy | forest green `#59a14f` | PS, PSO, PSJ, PSH, PSD, PSRX |
| Nutrition | lime `#8cd17d` | FH, PRSP |
| Orders/CPRS | tomato `#e15759` | OR, OE, GMRC, GMTS, TIU, CPRS |
| Mental Health | mauve `#b07aa1` | YS |
| Nursing | lavender `#d4a6c8` | GMRY, NUR |
| Surgery | rose `#ff9da7` | SR |
| Billing/Finance | gold `#f1ce63` | IB, FB, DRG |
| Kernel/System | walnut `#9c755f` | XU, XQ, XT, XWB, DI, DD |
| Infrastructure | silver `#bab0ac` | HL, XDR, VDEF |
| Other | slate `#79706e` | everything else |

**Field type colors** (used in heatmap and wordcloud):

| Type | Color | Meaning |
|---|---|---|
| F | blue | Free text |
| P | red | Pointer to another file |
| S | green | Set of codes (enum) |
| D | orange | Date/time |
| N | sky blue | Numeric |
| M | purple | Multiple (sub-file) |
| W | brown | Word processing |
| C | gold | Computed |
| K | rose | MUMPS executable |
| V | lime | Variable pointer (polymorphic FK) |

**Self-contained HTML output** — every file is a single `.html` that embeds the data
as an inline JSON object and loads D3 from CDN.  Copy the file anywhere; no server needed.

**CDN dependencies** (internet required at view time):

```
D3 v7:      https://d3js.org/d3.v7.min.js
d3-cloud:   https://cdn.jsdelivr.net/npm/d3-cloud@1.2.7/build/d3.layout.cloud.min.js
d3-sankey:  https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js
```

---

### to_treemap.py — Zoomable Treemap

A click-to-drill D3 treemap.  Each rectangular tile is a node; tile area encodes a
metric (field count, entry count, priority score, etc.).  Click any parent tile to zoom
into its children.  A breadcrumb at the top shows the current drill path; click any
crumb to navigate back up.  Tiles too small to label hide their text automatically.

**Common flags:**

| Flag | Default | Description |
|---|---|---|
| `--mode` | required | One of: `inventory`, `volume`, `schema`, `coverage`, `candidates` |
| `--input` | required | Primary data file (JSON or CSV depending on mode) |
| `--inventory` | none | `inventory.json` — adds package grouping in volume mode |
| `--output` | required | Output `.html` path |

---

#### inventory mode

**Question:** How is the schema organized by package, and which packages are largest?

**Input:** `inventory.json` (from `FileInventory.export_json()`)

**Hierarchy:** clinical domain → package → file

**Tile size:** field count per file

**Color:** clinical domain

**Key interactions:**
- Click a domain tile → zoom into its packages
- Click a package tile → see all its files with field counts
- Breadcrumb → navigate back up any level
- Hover → tooltip shows file number, label, package, field count

**Best used at:** Phase 1 (scope survey) — the first interactive view of the whole schema

```bash
python scripts/to_treemap.py \
    --mode inventory \
    --input ~/data/vista-fm-browser/output/inventory.json \
    --output ~/data/vista-fm-browser/output/treemap_inventory.html
```

---

#### volume mode

**Question:** Which files hold the most data, and where does the empty schema live?

**Input:** `file_volume.json` (entry counts per file, produced in Phase 2)

**Hierarchy:** volume tier (Massive / Large / Medium / Small / Tiny / Empty) → package → file

**Tile size:** entry count (log-scaled so small files remain visible)

**Color:** clinical domain (requires `--inventory`; falls back to tier color if omitted)

**Key interactions:**
- Drill from tier → package → individual file
- Hover → entry count, file number, package name, volume tier
- The Massive tier (red) is visible instantly even at top level

```bash
python scripts/to_treemap.py \
    --mode volume \
    --input     ~/data/vista-fm-browser/output/file_volume.json \
    --inventory ~/data/vista-fm-browser/output/inventory.json \
    --output    ~/data/vista-fm-browser/output/treemap_volume.html
```

---

#### schema mode

**Question:** What is the full field-type composition of every file, grouped by package?

**Input:** `all_fields.json` (flat list of field records from Phase 3 full schema build)

**Hierarchy:** package → file → field-type bucket (F / P / S / D / N / M / W / C / K / V)

**Tile size:** number of fields of each type within the file

**Color:** clinical domain (package level), field-type color (leaf level)

**Key interactions:**
- Drill package → file → see the type breakdown of individual files
- The leaf level color matches the field-type color table above
- Hover → package, file, type code, count

**Best used at:** Phase 4 (variety analysis) — shows where FREE TEXT and POINTER
fields concentrate across the schema

```bash
python scripts/to_treemap.py \
    --mode schema \
    --input ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/treemap_schema.html
```

---

#### coverage mode

**Question:** Which files and fields are actually populated vs. dormant schema?

**Input:** `phase6_coverage_multi.csv` (columns: `file`, `field`, `field_num`, `pct`)
produced by the pandas coverage block in Phase 6

**Hierarchy:** file → coverage tier (High ≥80% / Medium 20–80% / Low <20%) → field

**Tile size:** uniform (1 per field) — area encodes field count by tier, not magnitude

**Color:**
- High ≥ 80% → green `#2ca02c`
- Medium 20–80% → orange `#ff7f0e`
- Low < 20% → red `#d62728`

**Key interactions:**
- Drill file → see what fraction of its fields are well-populated
- Red-heavy files are candidates for schema pruning
- Hover → field label, coverage %, tier

```bash
python scripts/to_treemap.py \
    --mode coverage \
    --input ~/data/vista-fm-browser/output/phase6_coverage_multi.csv \
    --output ~/data/vista-fm-browser/output/treemap_coverage.html
```

---

#### candidates mode

**Question:** Which normalization issues are most urgent, and which packages contain them?

**Input:** `normalization_candidates.json` (from Phase 7 rule application)

**Hierarchy:** rule type → package → candidate field/label

**Tile size:** priority score of each candidate

**Color:** rule type (each rule gets a distinct color):
- `label_type_conflict` → red
- `hub_file_reference` → orange
- `date_as_free_text` → purple
- `pointer_to_empty_file` → blue

**Key interactions:**
- Drill rule → package → see individual candidates with priority score
- Large tiles = high priority; small tiles = low priority
- Hover → label, rule, priority score, detail (type breakdown, inbound count, etc.)

```bash
python scripts/to_treemap.py \
    --mode candidates \
    --input ~/data/vista-fm-browser/output/normalization_candidates.json \
    --output ~/data/vista-fm-browser/output/treemap_candidates.html
```

---

### viz_library.py — Visualization Library

Six D3 visualizations, each answering a different question about the FileMan database.
All subcommands write a single self-contained HTML file.

**Common pattern:**

```bash
python scripts/viz_library.py <subcommand> [flags] --output path/to/out.html
firefox path/to/out.html &
```

---

#### heatmap — package × field-type matrix

**Question:** Which clinical domains rely most heavily on each field type?

**Input:** `all_fields.json`

**Layout:** rows = packages (top N by field count), columns = field type codes
(F P S D N M W C K V DC).  Each cell shows the count of fields of that type in
that package.  Per-column color scaling so rare types (K, V) are still legible.
Row and column totals appear on the margins.

**Interactions:**
- Hover → package name, type code, exact count
- Cell label hidden when the cell is too small (configurable via `--top-n`)

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--input` | required | `all_fields.json` |
| `--output` | required | Output HTML path |
| `--top-n` | 30 | Number of packages to include (sorted by total field count) |

```bash
python scripts/viz_library.py heatmap \
    --input  ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/viz_heatmap.html \
    --top-n  40
```

**What to look for:** A column of high-intensity cells under `P` (Pointer) across
multiple packages identifies the central hub-centric packages.  A package with a
near-empty row but a large `M` (Multiple) cell is heavily sub-file oriented.

---

#### correlogram — file attribute scatter matrix

**Question:** Do files with more fields also have more pointers?  Do large files have
higher multiple counts?  Are there unexpected clusters?

**Input:** `inventory.json` (primary), optionally `all_fields.json` and
`file_volume.json` / `file_volume.csv` to enrich with schema and volume data

**Layout:** 5 × 5 scatter matrix of five per-file numeric variables:
`field_count`, `pointer_count`, `set_count`, `multiple_count`, `entry_count`.
Diagonal cells show histograms.  Off-diagonal cells show scatter plots with
Pearson r in the corner.  Points are colored by clinical domain.

**Interactions:**
- Hover over a point → file label, package, domain, values for both axes
- Points color-coded by domain; legend in corner

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--input` | required | `inventory.json` |
| `--schema` | none | `all_fields.json` — adds pointer/set/multiple counts |
| `--volume` | none | `file_volume.json` or `.csv` — adds entry_count |
| `--output` | required | Output HTML path |

```bash
python scripts/viz_library.py correlogram \
    --input  ~/data/vista-fm-browser/output/inventory.json \
    --schema ~/data/vista-fm-browser/output/all_fields.json \
    --volume ~/data/vista-fm-browser/output/file_volume.csv \
    --output ~/data/vista-fm-browser/output/viz_correlogram.html
```

**What to look for:** A tight positive correlation between `field_count` and
`pointer_count` means the schema is densely relational — normalization is FK-heavy.
Outlier points (high `entry_count`, low `field_count`) are narrow high-volume files —
event logs or audit tables.

---

#### wordcloud — field label frequency cloud

**Question:** What concepts dominate the VistA vocabulary, and what types are they?

**Input:** `all_fields.json`

**Layout:** Standard word cloud where word size encodes the number of fields across
all files that share that label.  Word color encodes the dominant datatype for that
label (using the field-type color table).  Font weight varies with frequency.
Uses `d3-cloud` for collision-free placement.

**Interactions:**
- Hover → label text, total occurrence count, dominant type name, number of distinct
  types the label appears under (type consistency indicator)

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--input` | required | `all_fields.json` |
| `--output` | required | Output HTML path |
| `--top-n` | 200 | Maximum number of labels to render |

```bash
python scripts/viz_library.py wordcloud \
    --input  ~/data/vista-fm-browser/output/all_fields.json \
    --output ~/data/vista-fm-browser/output/viz_wordcloud.html \
    --top-n  300
```

**What to look for:** Labels shown in mixed colors (multiple hues in hover tooltip
saying "mixed (N types)") are label-type conflicts — the same label used with
different datatypes across packages.  Dominant large words reveal the shared vocabulary
candidates for canonical enum or reference table definitions.

---

#### dendrogram — package → file radial tree

**Question:** How many files does each package contain, and how deep is the hierarchy?

**Input:** `inventory.json`

**Layout:** Radial cluster tree (d3.cluster).  The center root fans out to package
nodes at the inner ring, then to individual file nodes at the outer ring.  Node
radius is proportional to sqrt(field_count), so schema-heavy files are immediately
visible.  Package nodes are labeled; file nodes are labeled only if they have
above-average field counts (to reduce clutter).  Zoom and pan enabled.

**Interactions:**
- Scroll → zoom in/out
- Drag → pan around the circle
- Hover package node → package name, domain, file count
- Hover file node → file number, label, package, field count

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--input` | required | `inventory.json` |
| `--output` | required | Output HTML path |
| `--max-files` | 300 | Cap on file nodes rendered (keeps largest by field count) |

```bash
python scripts/viz_library.py dendrogram \
    --input     ~/data/vista-fm-browser/output/inventory.json \
    --output    ~/data/vista-fm-browser/output/viz_dendrogram.html \
    --max-files 400
```

**What to look for:** A package arm with many small outer nodes is a utility package
(lots of small reference files).  A package arm with a few very large outer circles is
a clinical record package (few but heavy files).  Isolated arms that barely extend
outward are near-empty packages (defined but unpopulated in this VistA instance).

---

#### sankey — cross-package pointer flow

**Question:** Which packages are central hubs that everything else points at?  Which
packages are pure consumers with no outbound pointers?

**Input:** `all_fields.json` (required), `inventory.json` (optional, for domain color)

**Layout:** Sankey diagram (d3-sankey).  Nodes = packages.  Links = cross-package
pointer fields (intra-package pointers are excluded — they would be self-loops).
Link width encodes the count of pointer fields flowing from source package to target
package.  Node color by clinical domain.  Nodes are vertically draggable to reduce
visual overlap.

**Interactions:**
- Drag nodes vertically → rearrange layout to untangle crossings
- Hover link → source package, target package, pointer field count
- Hover node → package name, domain, total flow (sum of all pointer fields touching it)

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--input` | required | `all_fields.json` |
| `--inv` | none | `inventory.json` — enriches domain colors |
| `--output` | required | Output HTML path |
| `--min-flow` | 1 | Minimum pointer count to include a link (filter noise) |
| `--top-n-pkgs` | 30 | Cap on number of packages shown |

```bash
python scripts/viz_library.py sankey \
    --input      ~/data/vista-fm-browser/output/all_fields.json \
    --inv        ~/data/vista-fm-browser/output/inventory.json \
    --output     ~/data/vista-fm-browser/output/viz_sankey.html \
    --min-flow   3 \
    --top-n-pkgs 25
```

**What to look for:** Nodes with many thick incoming links are hub packages (Kernel,
Registration, Lab).  Nodes with only outgoing links are domain-specific consumers
(Pharmacy, Surgery).  A link so thick it dwarfs others indicates a tight structural
coupling — those two packages must be migrated together.

---

#### bundle — hierarchical edge bundling

**Question:** Which files share many pointer relationships, and does coupling follow
package boundaries or cross them?

**Input:** `all_fields.json` (required), `inventory.json` (optional)

**Layout:** Files are arranged as leaves around a circle, grouped into package arc
bands at the outer rim.  Pointer relationships between files are drawn as curved
edges routed through the center (Bézier bundle with tension 0.85, via
`d3.curveBundle`).  Intra-package edges hug the circumference; cross-package edges
cut toward the center, making coupling clusters immediately visible.
Zoom and pan enabled.  Labels are shown only for files with ≥ 3 connections.

**Interactions:**
- Click a file node → highlight all edges connected to that file (colored by domain);
  all other edges dim.  Click again to clear.
- Hover file node → file label, package, domain, outgoing and incoming pointer counts
- Hover package arc → package name, domain, file count
- Scroll → zoom; drag → pan

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--input` | required | `all_fields.json` |
| `--inv` | none | `inventory.json` — enriches package grouping |
| `--output` | required | Output HTML path |
| `--max-files` | 150 | Cap on file nodes; keeps highest-degree files to avoid density overload |

```bash
python scripts/viz_library.py bundle \
    --input     ~/data/vista-fm-browser/output/all_fields.json \
    --inv       ~/data/vista-fm-browser/output/inventory.json \
    --output    ~/data/vista-fm-browser/output/viz_bundle.html \
    --max-files 200
```

**What to look for:** A cluster of files on one arc where edges mostly stay near the
rim indicates a self-contained package — safe to extract as an isolated schema unit.
A file node where clicking reveals edges shooting across the circle to many different
package arcs is a cross-cutting concern that cannot be extracted without pulling along
many dependencies.
