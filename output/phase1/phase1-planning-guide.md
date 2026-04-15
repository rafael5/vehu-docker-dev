# Phase 1 — Planning Guide

> **Living document.** Updated every iteration. Earlier findings preserved, new
> sections appended chronologically. Read this guide first before starting a new
> phase 1 pass.

---

## Purpose of phase 1

Produce a trustworthy, complete scope survey of the FileMan corpus in VEHU:
file count, package attribution, field-type distribution, and enough grounding
to let downstream phases (volume, topology, variety, coverage, normalization)
key off a locked denominator.

---

## Canonical denominator (locked 2026-04-15)

All downstream phases (2–8) must use these numbers. **Do not re-derive or
override.** If VEHU data changes, re-run phase 1 + 1.5 and update this section.

| Metric | Value | Source |
|--------|------:|--------|
| **Total files** | 2,915 | `^DIC` top-level numeric walk (phase 1) |
| **Packaged (phase 1)** | 1,232 | `^DIC(9.4)` FILE multiple matches |
| **Attributed (phase 1.5)** | 1,544 | prefix + range heuristics, 91.7% of residual |
| **Effective attributed total** | **2,776 (95.2%)** | phase 1 + phase 1.5 |
| **Residual unattributed** | 139 (4.8%) | orphan namespaces, data-quality limit |

**Rules for downstream phases:**
- Use `total_files = 2,915` as the denominator for all file-level stats.
- When grouping by package, include phase-1.5 attributions (with their
  confidence level) and carry confidence forward.
- The 139 residuals belong to a separate `"(unattributed)"` bucket — do not
  silently drop them from totals.
- If a phase needs a stricter denominator (high-confidence only), it must
  filter explicitly and document the filter in its own report.

---

## Iteration 1 — 2026-04-14 (initial pass)

### Source
- Script: `scripts/analysis/phase1-scope.py`
- Run env: VEHU container (`source /etc/bashrc`, `ydb_gbldir=/home/vehu/g/vehu.gld`)
- Outputs: `output/phase1/` — `inventory.json`, `summary.json`, `files.csv`,
  `packages.csv`, `type_distribution.csv`, `phase1_scope.png`,
  `phase1-scope-report.md`

### Headline numbers
- **2,915** FileMan files
- **470** packages
- **1,232 (42.3%)** files with owning package
- **1,683 (57.7%)** unpackaged files
- **69,328** total fields (avg 23.8 per file)
- File #1 (`ATTRIBUTE`): 25 fields, **0 entries reported**
- Top type: FREE TEXT (27.6%) + SET OF CODES (22.4%) = **50% of all fields**

### Top 15 packages (files)
IFCAP (90), REGISTRATION (89), INTEGRATED BILLING (81), LAB SERVICE (52),
DIETETICS (44), ENGINEERING (36), MEDICINE/CARDIOLOGY (35), KERNEL (33),
FEE BASIS (33), PAID (30), SURGERY (28), ONCOLOGY (27), MENTAL HEALTH (25),
RADIOLOGY/NUCLEAR MEDICINE (24), PROSTHETICS (23).
Top 15 ≈ 58% of packaged files; long tail is real.

---

## Findings from iteration 1

### F1. File #1 reports 0 entries — untrusted registry
The "ATTRIBUTE" file #1 is FileMan's own file registry, but
`FileReader.count_entries(1)` returned 0 while the ^DD walk found 2,915 files.
This is a credibility gap on the headline count. Either the count comes from a
different global than the registry, or `count_entries` is pointing at the wrong
address for file 1.

### F2. Unpackaged files dominate (58%)
1,683 of 2,915 files have no owning package. Every downstream per-package
analysis is biased unless these are attributed or explicitly excluded.

### F3. Type codes are compound, not atomic
Many "type" entries in the distribution are compound codes: `NJ3,0`, `RF`, `FX`,
`P200'`, `RFX`, `DX`, `SX`. Base type + modifiers (R=required, X=crossref,
J=justified, O=output-transform, etc.) should be split so analysis sees true
base-type proportions.

### F4. Free text is the single biggest surface
11,962 FREE TEXT fields — the most likely reservoir of hidden structure
(dates-as-strings, coded values in text, embedded pointers). Phase 7
normalization should target high-volume FREE TEXT on hub files first.

### F5. Top-15 concentration is moderate
Top-15 packages hold ~58% of *packaged* files. The long tail of small packages
is substantial; tooling decisions should not optimize only for the big packages.

---

## Recommendations — sequenced

Ordered by priority and dependency. Critical path first, then parallelizable
items, then deferred.

| # | Task | Type | Depends on | Status |
|--:|------|------|------------|--------|
| **1** | Verify file enumeration source (resolve F1) | Investigation + code | — | **DONE** (iter 1.2) |
| **2** | Split compound type codes (resolve F3) | Code (TDD) | — | **DONE** (iter 1.2, needs container run) |
| **3** | Attribute unpackaged files (resolve F2) | Code (new phase 1.5) | 1 | **DONE** (iter 1.3) |
| **4** | Lock the package denominator | Documentation | 3 | **DONE** (iter 1.3) |
| **5** | Apply long-tail caveat downstream (F5) | Narrative rule | 4 | **DONE** (iter 1.6) — see DOWNSTREAM-RULES.md |
| **6** | Free-text audit feed for phase 7 (F4) | Code, needs phase 3 hubs | phase 3 hub_files.csv (exists) | **DONE** (iter 1.6) |

**Critical path:** 1 → 3 → 4.
**Parallel-safe:** 2 runs alongside 1.
**Deferred:** 5 (operating rule after 4), 6 (after critical path).

---

## Planned execution — tasks 1 & 2 (in progress)

### Task 1: Verify enumeration source
- Trace `FileInventory.load()` and `DataDictionary.list_files()` in source.
- Determine which global the 2,915-count comes from (^DD top-level subscripts, or
  a registry walk).
- If ^DD: the count is trustworthy; `count_entries(1)` bug is separate — likely
  reads `^DIC(1)` which is empty in VEHU by design.
- If `^DIC(1)` walk: rewrite enumeration to walk `^DD` top-level subscripts.
- Add a cross-check to phase1-scope.py that reports the delta between ^DD-count
  and ^DIC-count and flags discrepancies in the report.

### Task 2: Compound type decomposition
- New module: `src/vista_fm_browser/type_codes.py`.
- Function: `decompose(code) -> TypeSpec(base, modifiers, numeric_spec)`.
- TDD fixtures (known codes): `F`, `N`, `NJ3,0`, `RF`, `FX`, `P200'`, `RFX`,
  `DX`, `K`, `W`, `S`, `SX`, `D`, `MF`, `RD`, `WL`, `NJ8,2`, `FO`, `FXO`.
- Modifier letters observed: `R` (required), `X` (crossref or input transform),
  `J` (right-justify with width), `O` (output transform), `L` (?), `F`
  (required in context?) — verify empirically against DD documentation.
- Phase 1 output additions:
  - `type_distribution_base.csv` — counts by base type only
  - `type_modifiers.csv` — modifier frequency
  - Report gains a "Base types (collapsed)" table alongside existing compound
    table.

### Task 3: Unpackaged file attribution (after 1)
- New script: `scripts/analysis/phase1_5-package-attribution.py`.
- Heuristic A (number-range): build per-package file-number ranges from
  attributed files; attribute unowned files falling inside a range to that
  package with confidence derived from range density.
- Heuristic B (routine namespace): skipped unless `^ROU` or equivalent is
  available in VEHU — TBD during task 1 investigation.
- Heuristic C: inspect `^DIC(9.4)` (PACKAGE file) for explicit file-package
  linkage that the current enumerator may be missing.
- Outputs: `output/phase1_5/attribution_candidates.csv`,
  `confidence_breakdown.csv`, `phase1_5-attribution-report.md`.

### Task 4: Denominator lock (after 3)
- Decide: report on (a) all-files (n≈2,915), (b) packaged subset, or
  (c) attributed subset (packaged + phase1.5 attributed).
- Document choice in new section of `phase1-scope-report.md` and propagate via
  `summary.json` field `canonical_denominator`.
- All downstream phases must consume this field.

---

## Iteration 1.2 — 2026-04-15

### Task 1: Verify enumeration source — RESOLVED

- **Source:** `FileInventory._read_files` (src/vista_fm_browser/inventory.py:268)
  walks `^DIC` top-level numeric subscripts. This IS the canonical file
  registry. The 2,915 count is **trustworthy**.
- **File #1 "0 entries" explained:** File #1 is a special case — its entries
  are stored as the top-level subscripts of `^DIC` itself, not under a
  `^DIC(1, ien, ...)` subtree. `FileReader.count_entries(1)` walks that
  subtree and returns 0 by design. The semantically correct entry count for
  file #1 is `total_files`.
- **Fix applied:** `phase1-scope.py::inspect_file_registry` now takes
  `total_files` and reports it as file #1's entry count, with the subtree
  count shown alongside for transparency. New summary.json fields:
  `file_1_entries` (= total_files), `file_1_entries_source` = "dic_top_level",
  `file_1_subtree_entries` (from ^DIC(1,...), expected 0).
- **Downstream impact:** next phase-1 run will show file #1 with 2,915
  entries, consistent with the registry walk.

### Task 2: Compound type decomposition — RESOLVED (code-complete)

- **New module:** `src/vista_fm_browser/type_codes.py` with `decompose(raw) ->
  TypeSpec`. Fully tested (tests/test_type_codes.py, 30+ cases), all passing
  under host-python smoke test. Needs `make test` run in container to
  confirm against the real fixtures.
- **Retrofit:** `_extract_type_code` in `data_dictionary.py` is now a thin
  wrapper around `decompose`; legacy (base, pointer_file) tuple semantics
  preserved and smoke-tested.
- **FieldDef extension:** added `raw_type: str` so callers can re-decompose
  without touching the DB.
- **Phase1 output additions:**
  - `summary.json` gains `modifier_distribution` (list) and
    `flag_distribution` (required/audited/multiple totals).
  - New CSV: `type_modifiers.csv` — modifier letters + flag totals.
  - Report gains a "Type Modifiers & Flags" table.
- **Pending:** run `phase1-scope.py` inside VEHU container to regenerate
  output. Will be deferred until after Task 3 so we regenerate once at
  critical-path end.

## Iteration 1.3 — 2026-04-15

### Task 3: Unpackaged file attribution — DONE

- **New module:** `src/vista_fm_browser/attribution.py` — pure-Python
  attribution with three heuristics (prefix, empirical range, canonical
  range). 23 tests in `tests/test_attribution.py`, all passing.
- **New script:** `scripts/analysis/phase1_5-package-attribution.py`. No YDB
  needed — operates on `output/phase1/inventory.json`. Host-safe.
- **New outputs:** `output/phase1_5/attribution_candidates.csv`,
  `attribution_summary.json`, `phase1_5-attribution-report.md`.

### Attribution results (first run)

- **Input:** 1,683 unpackaged files (phase-1 residual)
- **Attributed:** 1,544 (**91.7%**)
- **By method:** prefix=1,511 · range_canonical=32 · range_empirical=1 · none=139
- **By confidence:** high=638 · med=874 · low=32 · none=139

### Residual 139 unattributed — root cause

Namespaces with no matching package prefix in `^DIC(9.4)`: OCX, RC, SC, GMR,
GMT, DSI, AXA, AWC, XLM, XIP, ACK, SCTM, SCPT, RCY, RCRP, RCSTAT, RCXV...
These are legitimate VistA namespaces (e.g. RC=Accounts Receivable kids,
GMR=Consults, XIP=Kernel IP subsystem), but the corresponding PACKAGE entries
either don't exist or have incorrect/missing prefix fields. This is a data
quality issue in the live VEHU PACKAGE file, not a heuristic limitation.
Resolving these requires VA domain knowledge or a curated namespace→package
override table — out of scope for automated attribution.

### Updated denominator picture (post-attribution)

- Phase-1 reported: 1,232 packaged / 1,683 unpackaged
- Phase 1.5 attribution: +1,544 newly attributed
- **Effective packaged total: 2,776 (95.2% of 2,915)**
- **Residual unattributed: 139 (4.8%)**

This is what Task 4 will lock in as the canonical denominator.

## Open questions

- **Q1.** Is `^ROU` (or a routine namespace global) populated in VEHU? If not,
  Heuristic B in Task 3 is off the table.
- **Q2.** Does `^DIC(9.4)` contain explicit file→package mappings not yet picked
  up by `FileInventory`? (Check during Task 1.)
- **Q3.** Are the `P200'` / `P2'` trailing apostrophe codes pointer-to-file-200
  with a modifier, or a parse artifact? Verify during Task 2. — RESOLVED in
  iter 1.2: `'` is a trailing required-in-context flag; `decompose` sets
  `required=True` and strips it from the pointer target.
- **Q4.** Field-count discrepancy: old 69,328 vs new 46,790. New value comes
  from iterating `fd.fields.values()` which holds entries parsed from
  `^DD(file, field, 0)`; old value from raw `^DD` subscript count includes
  subfile markers. Need to verify which is the correct denominator for
  "total fields" — resolve at start of phase 2 before volume analysis.

---

## Iteration log

| Date | Iteration | Summary |
|------|-----------|---------|
| 2026-04-14 | 1 | Initial pass — generated all phase 1 artifacts, baseline numbers captured. |
| 2026-04-15 | 1.1 (planning) | Recommendations derived, critical path sequenced, this guide created. Execution not yet started. |
| 2026-04-15 | 1.2 (tasks 1+2 partial) | Task 1 resolved (see below). Task 2 discovered already partially done — source-code parser collapses types; phase1 output is stale. Phase1-scope.py patched for file-1 entries. |
| 2026-04-15 | 1.2b (task 2 complete) | `type_codes.decompose` TDD-written, `_extract_type_code` retrofit, phase1 output extended with modifier/flag stats (not yet regenerated). |
| 2026-04-15 | 1.3 (task 3 complete) | Phase 1.5 attribution built + run: 1,544/1,683 attributed (91.7%). 139 residuals are orphan namespaces with missing PACKAGE records. |
| 2026-04-15 | 1.4 (task 4 done) | Canonical denominator locked: 2,915 total / 2,776 attributed / 139 residual. Rules documented for downstream phases. |
| 2026-04-15 | 1.5 (validation) | Container run: 58/58 tests pass. phase1-scope.py regenerated outputs into `output/phase1/` (fixed OUTPUT_DIR). Phase 1.5 re-ran, same attribution 91.7%. Field count changed 69,328→46,790 (old code counted subfile subscripts; new code via TypeSpec counts proper fields only — will investigate in phase 2). |
| 2026-04-15 | 1.6 (task 5+6 done) | Task 5: DOWNSTREAM-RULES.md published (6 rules for phases 2–8). Task 6: phase 1.6 freetext-targets script ran on VEHU — 590 FREE TEXT fields across 30 hubs, 105 high-score candidates for phase 7. VEHU has empty `^DD(f,fld,1)` everywhere (dev instance). |

---

## How to update this guide

When you complete (or partially advance) a pass:

1. Add a new `## Iteration N — YYYY-MM-DD` section above the log table.
2. Record: findings that changed, findings that were resolved, new gaps
   discovered, any headline-number revisions.
3. Update the recommendations table (status column, dependency changes).
4. Add a row to the iteration log.
5. Do **not** delete prior iteration content — this is an append-only history.
