# Phase 2 — Planning Guide

> **Living document.** Updated every iteration. Read first before a phase 2 pass.
> Mirrors the structure of `output/phase1/phase1-planning-guide.md`.

---

## Purpose of phase 2

Survey *where the data lives* across the 2,915 FileMan files in VEHU.
Produce a per-file entry-count inventory, classify files into volume tiers,
and identify the small set of files that hold the bulk of operational
data. This feeds phase 3 (topology) by distinguishing hub-by-references
from hub-by-volume.

---

## Inputs (from phase 1, per DOWNSTREAM-RULES.md)

- **Canonical denominator:** 2,915 total files
- **Attribution source:** `output/phase1_5/attribution_candidates.csv`
  (1,544 attributed + 139 residual) — must be merged with per-file rows.
- **Provenance values:** `direct` (phase 1), `prefix` / `range_empirical` /
  `range_canonical` (phase 1.5), `unattributed` (residual).
- Total fields = 46,790 (top-level files) — not used directly in phase 2.

---

## Iteration 1 — 2026-04-14 (baseline, stale)

Ran from original `phase2-volume.py` before the phase-1 work landed.

### Headline numbers

- 2,915 files scanned
- **2,858 (98.0%) have ≥ 1 entry; 57 empty**
- **717,892 total entries** across all files
- 0 files in "massive" tier (>100K)
- **7 files in "large" tier (10K–100K)** — these carry operational signal
- 2,475 files in "tiny" tier (1–99 entries) — the long tail

### Top files by volume

| Rank | File # | Label | Entries | Package (phase-1-direct) |
|-----:|-------:|:------|--------:|:-------------------------|
| 1 | 80 | ICD DIAGNOSIS | 91,279 | DRG GROUPER |
| 2 | 80.1 | ICD OPERATION/PROCEDURE | 86,813 | DRG GROUPER |
| 3 | 996.2 | EXTENSIBLE EDITOR SPELLCHECKER | 37,324 | — |
| 4 | 64 | WKLD CODE | 25,227 | LAB SERVICE |
| 5 | 409.68 | OUTPATIENT ENCOUNTER | 14,352 | — |
| 6 | 9000010 | VISIT | 14,125 | — |
| 7 | 112 | FOOD NUTRIENTS | 12,398 | DIETETICS |
| 8 | 9000010.18 | V CPT | 7,299 | — |

### Initial findings (to validate / revisit)

- **F1.** 98% data-populated — VEHU is more than a skeleton; volume analysis
  is meaningful.
- **F2.** The "large" tier is only 7 files (0.24%). Everything above ICD
  DIAGNOSIS's 91K falls short of 100K. Either VEHU is light on patient
  data (plausible, dev instance), or volume is truly long-tailed.
- **F3.** Many top-volume files show no package — rows 3, 5, 6, 8, 11, 12
  in the top 15 — **violates DOWNSTREAM-RULES rule 3** (139 residuals must
  appear, with provenance). Phase 1.5 can fix most of these.
- **F4.** File 9000010 "VISIT" (14,125 entries) and kin (9000010.18 V CPT,
  9000010.06 V PROVIDER) are high-volume PCE/visit files without package
  attribution. Phase 1.5 should attribute these; if not, they're in the
  139 residuals.
- **F5.** No massive tier — caps at 91K. Confirms phase-3 hub analysis
  should weigh by inbound-pointer count, not entry volume.

---

## Tasks — sequenced

Ordered by priority. Mirror of phase-1 critical-path approach.

| # | Task | Type | Depends on | Status |
|--:|------|------|------------|--------|
| **1** | Fix OUTPUT_DIR to `output/phase2/` per convention | Code (trivial) | — | **DONE** (iter 2) |
| **2** | Merge phase-1.5 attribution + carry provenance/confidence | Code | 1 | **DONE** (iter 2) |
| **3** | Surface 139 residuals as `"(unattributed)"` bucket per rule 3 | Code | 2 | **DONE** (iter 2) |
| **4** | Add per-package volume totals (uses merged attribution) | Code | 2 | **DONE** (iter 2) |
| **5** | Regenerate phase-2 outputs and re-render report | Container run | 1-4 | **DONE** (iter 2) |
| **6** | Assumptions audit for phase 2 | Documentation | 5 | TODO |

### Task 1 — trivial OUTPUT_DIR fix
Same fix as phase 1 iter 1.5. Use `Path(__file__).resolve().parents[2] / "output" / "phase2"`.

### Task 2 — attribution merge
Load `output/phase1_5/attribution_candidates.csv`. Build a
`{file_number: (package_name, provenance, confidence)}` map. In
`collect_volume`, emit `package`, `package_provenance`, `package_confidence`
for each row. Provenance values: `direct` (when `fr.package_name` non-empty
from `FileInventory`), or one of the phase-1.5 method strings (prefix /
range_empirical / range_canonical), or `unattributed`.

### Task 3 — residuals bucket
`build_summary` currently collapses by `r["package"]` silently; upgrade to
produce a `by_package_provenance` breakdown. Top-N by volume should always
include residuals if any are in the top N.

### Task 4 — per-package volume
Add to `summary.json`: `top_packages_by_entries` (list of
`{package, provenance, entry_total, file_count}`). This is what phase 3
topology will key off.

### Task 5 — regenerate
Container run. Validate residual coverage, top-files attribution, and that
the large-tier files now all have provenance.

### Task 6 — audit
Same template as phase 1. Audit claims: total entries, tier bounds, top
file choices, provenance merge correctness, residual handling.

---

## Iteration 2 — 2026-04-15 (tasks 1-5 complete)

### What changed in the script

- OUTPUT_DIR fixed to `<repo>/output/phase2/`.
- Loads `output/phase1_5/attribution_candidates.csv` and merges per-file
  attribution into rows with new columns `package_provenance` and
  `package_confidence`.
- Unattributed files bucket under `"(unattributed)"` (not empty string).
- Summary gains `provenance_totals`, `top_packages_by_entries` (with
  provenance mix per package), and `unattributed_bucket` (count, entry
  total, top-10 by volume).
- Report template updated with provenance table, enriched top-25 table
  (now shows provenance + confidence), top-15 packages by entries, and a
  dedicated unattributed bucket section.

### Findings (validated against live VEHU)

- **Provenance totals** (must sum to 2,915):
  direct=1,232 · prefix=1,511 · range_canonical=32 · range_empirical=1 ·
  unattributed=139. ✅ sums correctly.
- **Total entries corpus-wide:** 717,902 (10 more than iter-1 stale run —
  VEHU mutates over time).
- **Unattributed bucket carries real weight:** 139 files / **61,025
  entries (8.5% of all entries)**. Dropping them silently — as the
  pre-DOWNSTREAM-RULES script did — would have understated the corpus.
- **Top 5 unattributed files by volume are PCE / IHS:**
  OUTPATIENT ENCOUNTER (14,352), VISIT 9000010 (14,125),
  V CPT 9000010.18 (7,299), V PROVIDER 9000010.06 (6,283),
  HEALTH FACTORS 9999999.64 (5,936). PCE as a VistA package exists but
  its `^DIC(9.4)` record appears to lack the prefix field in VEHU — this
  is the same data-quality issue flagged in phase-1 Q7.
- **Top package by entries:** DRG GROUPER (181,162 entries across 25
  files) — ICD DIAGNOSIS + PROCEDURE dominate.
- **INTEGRATED BILLING expands 3× via attribution:** 81 direct + 159
  attributed = 240 files; total 21,127 entries.
- **New modifier signal:** `VA FILEMAN` package now covers 69 files via
  mostly-prefix attribution, carries 52,842 entries. Phase 1 showed these
  as "unpackaged"; they're actually FileMan-internal.

### New open questions

- **Q2.1** File 4 appears three times in the top-25 list with different
  labels (INSTITUTION, MASTER FILE PARAMETERS, MD5 Signature), each with
  2,916 entries. Looks like multiple file-registry pointers count the
  same ^DIC walk. Phase-3 topology may surface whether this is a parser
  artifact or a real duplicate-in-`^DIC(1,...)` situation.
- **Q2.2** Empty files: 57 files report 0 entries. Distribution by
  package / provenance / tier not yet analyzed — empty "large" files
  would be a red flag. Defer to task 6 audit.

## Open questions

---

## Iteration log

| Date | Iteration | Summary |
|------|-----------|---------|
| 2026-04-14 | 1 | Initial phase-2 run with pre-phase-1-fixes script. Baseline captured. |
| 2026-04-15 | 1.1 (planning) | Planning guide created. Tasks 1-6 sequenced. |
| 2026-04-15 | 2 (tasks 1-5) | Script updated (OUTPUT_DIR, attribution merge, unattributed bucket, per-package totals). Ran in container. 717,902 total entries. Provenance sums to 2,915. Unattributed = 139 files / 61,025 entries / 8.5%. |
