# Phase 2 — Assumptions Audit

_Generated 2026-04-15 (iter 3), updated 2026-04-15 (iter 4 — B3 resolved).
Classification: **VERIFIED** / **UNVERIFIED** / **KNOWN LIMITATION** /
**BUG FOUND** / **RESOLVED**._

---

## B1. Provenance totals sum to `total_files`

**Claim:** The new `provenance_totals` in `summary.json` sum to 2,915
(every phase-1 direct + phase-1.5 attribution + unattributed row).

**Status:** ✅ **VERIFIED**

**Evidence:** 1,232 direct + 1,511 prefix + 32 range_canonical +
1 range_empirical + 139 unattributed = **2,915**.

---

## B2. Unattributed bucket is complete and non-empty

**Claim:** All 139 phase-1-residual files appear in the unattributed
bucket; no file is dropped.

**Status:** ✅ **VERIFIED**

**Evidence:** `unattributed_bucket.file_count = 139` matches phase-1.5
summary. Top-10 bucket volume totals 61,025 entries.

---

## B3. `total_entries_all_files = 717,902` is correct

**Claim:** The sum of per-file `count_entries` values is the true total
entry volume of the corpus.

**Status:** ✅ **RESOLVED (iter 4)** — was `❌ BUG FOUND`

**Resolution (iter 4):** `_strip_root` rewritten to return
`(global_name, subscript_prefix)`; all callers + `_resolve_pointer`
updated. 6 new tests lock the behavior (300 suite pass). Re-run
produces **total_entries_all_files = 14,671,305** (20× the iter-2
figure). Bug was bidirectional: 95 files were inflated to 2,916 each,
but many more files with nested globals were massively *under*-counted
because the walker was pointed at the wrong subtree entirely.

**Historical evidence (iter-2 behavior):**

**Evidence:**

```
>>> _strip_root("^DIC(4,")
'^DIC'
>>> _strip_root("^DIC(4.001,")
'^DIC'
```

`_strip_root` in `src/vista_fm_browser/file_reader.py:161` drops every
subscript after the first `(`. For files whose data global is nested
inside a larger one (e.g. `^DIC(4, ...)` for INSTITUTION), this returns
`^DIC` — so `count_entries` walks the **top level** of `^DIC`, which
contains 2,916 numeric subscripts (the file registry), and returns
2,916 for all of them instead of the actual entry count under
`^DIC(file#, ...)`.

**Affected files:** 95 files with global roots of the form `^DIC(X,...)`
— all report exactly 2,916 entries. Examples: 1 (FILE), 3.1 (TITLE),
3.4 (COMMUNICATIONS PROTOCOL), 4 (INSTITUTION), 4.001, 4.005, 4.009,
4.05, 4.1, 4.11, 9.8, 10, 10.2, 10.3, 11, …

**Over-count estimate:**
- 95 files × 2,916 reported = 277,020 entries inflated
- Actual entry counts for these files are currently unknown
- True corpus total is **< 717,902**, likely by a significant margin
  (e.g. if the 95 files truly average 500 entries each, the actual
  number drops to ~487k)

**Fix plan (iteration 3):**

1. Rewrite `_strip_root` to return `(global_name, subscript_prefix)`
   parsed from the FileMan GL string.
2. Update `count_entries` to walk `conn.subscripts(global_name,
   [*subscript_prefix, ""])` so it enumerates the correct subtree.
3. Do the same fix to every other caller of `_strip_root`
   (`get_entry`, `_read_entry`, iteration helpers).
4. Add a unit test using YdbFake with a multi-level global to lock
   the fix.
5. Re-run phase 2 and update `total_entries_all_files`, `tier_counts`
   (many of the 95 may drop from "large" to smaller tiers), top-N
   lists, per-package totals.

**Affected downstream:** phase-3 topology that weights by volume
would pick up false signal from these 95 over-counted files. Must fix
before phase 3 runs.

---

## B4. Tier classification is correct

**Claim:** Files in each tier (massive ≥100K, large 10K–100K, medium
1K–10K, small 100–1K, tiny 1–99, empty 0) truly belong there.

**Status:** ✅ **RE-VALIDATED (iter 4)**

**Post-fix tier counts:** massive=16, large=36, medium=141, small=318,
tiny=2,298, empty=106. The 95 previously-miscounted files are now
distributed across their correct tiers — ~49 are in fact empty (hence
empty went 57 → 106). Tier classification is now trustworthy.

---

## B5. Top-25 file list is correct

**Claim:** The top-25 files by entry count represent the true
highest-volume files.

**Status:** ✅ **RE-VALIDATED (iter 4)**

**Post-fix top-5:** EXPRESSIONS (2.58M) · RXNORM RELATED CONCEPTS
(1.48M) · DRG PDX EXCLUSION GROUPS (1.13M) · RXNORM SIMPLE CONCEPT AND
ATOM ATTRIBUTES (1.05M) · SEMANTIC MAP (962K). ICD DIAGNOSIS /
PROCEDURE drop from the top into the lower massive tier — they were
always correctly counted, but many nested-global files were
under-counted and their true volumes now outrank ICD.

---

## B6. Attribution merge correctness

**Claim:** Every file's `package` + `package_provenance` +
`package_confidence` correctly reflects the phase-1 direct attribution
or the phase-1.5 heuristic result.

**Status:** ✅ **VERIFIED**

**Evidence:**
- Files with `fr.package_name` non-empty in `FileInventory` → marked
  `provenance=direct`, `confidence=high`.
- Files without direct attribution → looked up in
  `attribution_candidates.csv`; `provenance` takes the method string.
- Files missing from both → `package="(unattributed)"`, `provenance=unattributed`.
- Row counts per provenance match the expected totals (B1 passes).

---

## B7. Empty-files distribution

**Claim (Q2.2 from planning guide):** 57 empty files are real and
distributed plausibly across packages.

**Status:** ✅ **VERIFIED (no red flag)**

**Evidence:**
- 57 empty files observed
- By provenance: prefix=29, range_canonical=19, direct=9
- Top packages: VA FILEMAN (33), VENDOR – DOCUMENT STORAGE (7),
  MENTAL HEALTH (5), REGISTRATION (3)
- No tier-misclassified empties (all are correctly `tier=empty`)
- VA FILEMAN dominance is expected — FileMan ships many
  configuration/template files that may be legitimately empty in a
  clean VEHU install.

---

## B8. File 4 triple-listing (Q2.1)

**Status:** ✅ **RESOLVED as display artifact, not data issue**

File 4.0 (INSTITUTION), 4.001 (MASTER FILE PARAMETERS), 4.005 (MD5
Signature) are three distinct files with distinct global roots. The
rich-console table format truncated them all to "4.00" in terminal
display but the underlying CSV holds distinct rows.

However — B3 applies: all three of these files report 2,916 entries
because of the `_strip_root` bug, so their true volumes are unknown.

---

## B9. Tier bounds (`massive`/`large`/`medium`/etc.) are appropriate

**Claim:** The `TIER_BOUNDS` (≥100K, 10K–100K, 1K–10K, 100–1K, 1–99, 0)
reasonably partition the corpus.

**Status:** ⚠️ **UNVERIFIED — heuristic choice**

**Evidence:** 0 files are "massive" (≥100K) and 57 are empty, which is
plausible for a VEHU dev instance. Whether the 10K and 1K cutoffs are
meaningful vs. arbitrary hasn't been validated against any VistA domain
knowledge. Defensible for relative ranking; do not treat bin labels as
semantically authoritative.

---

## B10. Overall correctness of phase-2 findings given B3

**Claim:** The iteration-4 findings are correct and trustworthy for
phase-3 input.

**Status:** ✅ **RESOLVED (iter 4)** — was `⚠️ USE WITH CAVEAT`

**All previously tainted claims now hold:**
- Total entry count: 14,671,305 (iter 4)
- Tier counts: massive 16 / large 36 / medium 141 / small 318 /
  tiny 2,298 / empty 106
- Top-N rankings dominated by clinical terminology packages
  (CLINICAL LEXICON UTILITY, ENTERPRISE TERMINOLOGY SERVICE)
- Per-package entry totals corrected across all packages

---

## New open questions

| ID | Question | Status |
|----|----------|--------|
| Q2.1 | File 4 triple-listing | ✅ RESOLVED (display only) |
| Q2.2 | Empty-file distribution | ✅ RESOLVED (B7) |
| Q2.3 | Why 95 files all report 2,916 entries | ✅ RESOLVED → **BUG B3** |
| Q2.4 | `_strip_root` fix scope and testing | ✅ RESOLVED (iter 4) |
| Q2.5 | Exact over-count: what's the real corpus total after B3 fix? | ✅ RESOLVED — 14,671,305 (20× the iter-2 figure; bug was bidirectional, with under-counts dominating) |

---

## Summary

| Assumption | Status |
|------------|--------|
| B1. Provenance sums to 2,915 | ✅ VERIFIED |
| B2. Unattributed bucket complete | ✅ VERIFIED |
| B3. total_entries (14,671,305 iter 4) | ✅ RESOLVED (was BUG — fixed iter 4) |
| B4. Tier classification | ✅ RE-VALIDATED (iter 4) |
| B5. Top-25 list | ✅ RE-VALIDATED (iter 4) |
| B6. Attribution merge | ✅ VERIFIED |
| B7. Empty-file distribution | ✅ VERIFIED (count now 106 post-fix) |
| B8. File 4 triple-listing | ✅ RESOLVED (display only) |
| B9. Tier bounds | ⚠️ UNVERIFIED heuristic |
| B10. Overall usefulness | ✅ RESOLVED (iter 4) |

**Bottom line (iter 4):** ten claims, nine resolved/verified, one
(B9 tier-bounds) left as defensible heuristic. Phase 3 is
unblocked — `summary.json` is now trustworthy input for
volume-weighted topology.
