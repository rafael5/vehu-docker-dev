# Phase 1 — Assumptions Audit

_Generated 2026-04-15 — audits every assumption made across iterations 1 → 1.6
and classifies each as **VERIFIED**, **UNVERIFIED**, or **KNOWN LIMITATION**._

---

## A1. The canonical file count is 2,915

**Claim:** Total FileMan files in VEHU = 2,915, derived from walking `^DIC`
top-level numeric subscripts and keeping only those with a zero-node.

**Status:** ✅ **VERIFIED**

**Evidence (live probe 2026-04-15):**

| Counter | Value |
|--------|------:|
| `^DIC` top-level numeric subscripts | 2,916 |
| …with zero-node at `^DIC(n,0)` | **2,915** |
| …with GL node at `^DIC(n,0,"GL")` | 2,913 |

The extra `2916 - 2915 = 1` is the literal subscript `"0"` (file #0, the
registry header), correctly skipped by the enumerator. Two files (81.1,
81.3) have a zero-node but no GL node; they are real files without a data
global (abstract types) and are included in the 2,915 count.

**Implication:** no change. The locked denominator stands.

---

## A2. File #1's entry count = total_files (2,915)

**Claim:** File #1 is the FileMan FILE registry; its "entries" are the
registered files themselves, enumerated at the top level of `^DIC`, not
inside a `^DIC(1, ien, ...)` subtree.

**Status:** ✅ **VERIFIED**

**Evidence:** `^DIC(1, ...)` subtree iteration returns 0 entries (generic
`count_entries(1)`). The true registry entries are `^DIC` top-level numeric
subscripts with a zero-node = 2,915. phase1-scope.py reports this as
`file_1.entries=2,915 (source: dic_top_level)` with `file_1.subtree=2916`
shown as a diagnostic.

**Implication:** no change. The file-1 quirk is documented.

---

## A3. `^DD` top-level numeric subscripts ≠ file count

**Claim:** Walking `^DD` at the top level yields more subscripts than
there are FileMan files, because `^DD` also contains subfile definitions
and internal metadata nodes.

**Status:** ✅ **VERIFIED**

**Evidence:**

| Counter | Value |
|--------|------:|
| `^DD` top-level numeric subs | **8,261** |
| `^DIC` top-level numeric (files) | 2,915 |
| Difference (subfiles / other) | 5,346 |

**Implication (resolves Q4 from iter 1.5):** the old `total_fields`
(69,328) summed `_count_fields` across **all 8,261** `^DD` subs, which
includes per-subfile field counts. The new `total_fields` (46,790)
iterates only top-level `fd.fields.values()` for the 2,915 top-level
files. The new number is the correct "total fields on top-level files";
the old was an overcount by including subfile fields.

**Action:** phase 2 volume analysis should use **46,790** as the top-level
field count and separately compute subfile field counts if needed. Update
DOWNSTREAM-RULES.md rule 6.

---

## A4. Package attribution prefix-match is correct

**Claim:** Heuristic C (longest-prefix match from global-root namespace
against package prefixes) correctly attributes files to packages.

**Status:** ✅ **VERIFIED on sample** (not exhaustively verified)

**Evidence:** random sample of 8 high-confidence and 8 medium-confidence
attributions, all plausible:

| File | Global | Label | → Package (prefix) | Confidence |
|-----:|:-------|:------|:-------------------|:-----------|
| 403.46 | ^SD( | STANDARD POSITION | SCHEDULING (SD) | high |
| 50.625 | ^PS( | WARNING LABEL-ENGLISH | PHARMACY (PS) | high |
| 53.78 | ^PSB( | BCMA MEDICATION VARIANCE | BAR CODE MED ADMIN (PSB) | high |
| 9.9 | ^XPD( | PATCH MONITOR | KIDS (XPD) | high |
| 2006.5752 | ^MAGD( | DICOM OBJECTS | IMAGING (MAG) | med |
| 64.81 | ^LAB( | LAB NLT/CPT CODES | AUTOMATED LAB (LA) | med |
| 50.68 | ^PSNDF( | VA PRODUCT | NATIONAL DRUG FILE (PSN) | med |

**Known caveat:** medium-confidence attributions may misclassify when a
shorter prefix matches but a longer (correct) one is missing from
`^DIC(9.4)`. The 91.7% attribution rate suggests the prefix tree is
reasonably complete; the residual 139 unattributed are evidence of
incompleteness. Not every high/med attribution is independently verified.

**Action:** no change, but downstream phases should be cautious treating
medium-confidence attributions as authoritative.

---

## A5. Type-code decomposition rules

**Claim:** FileMan type strings follow `[R][*][M]<BASE>[modifiers]` with
prefix flags R/*/M and trailing modifier letters X/O/J/'/I/a/t/…

**Status:** ⚠️ **PARTIALLY VERIFIED**

**Evidence — observed modifier letters in live VEHU data:**

| Modifier | Count | Sample raw types | Meaning (inferred / documented) |
|:--------:|------:|:-----------------|:--------------------------------|
| J | 9,317 | `CJ14`, `NJ3,0`, `CJ8` | Justification (width[,dec]) — well known |
| X | 4,963 | `RFX`, `CJ50X`, `R*P.4'X` | Input-transform present — well known |
| O | 3,180 | `FXOa`, `RNJ19,9O`, `RDXOa` | Output-transform present — well known |
| I | 1,359 | `P10'I`, `P200'I`, `DI` | Identifier / inverse — FileMan-specific |
| a | 694 | `RFXa`, `Sa`, `RDXOa` | **UNVERIFIED** — lowercase modifier |
| t | 120 | `Ft12`, `St11`, `St11II` | **UNVERIFIED** — possibly length? |
| D | 23 | `MRD`, `MRDI`, `CDJ15` | Appears inside compound; also a base type — **PARSER BUG** see below |
| R | 16 | `FR`, `MRD` | Appears as trailing modifier; also a prefix — **PARSER LIMITATION** see below |
| m,p,C,w | <10 each | `Cmp9.6`, `BCJ8`, `Cmw` | **UNVERIFIED** |

**Known parser limitations (documented, not yet fixed):**

1. Compound "M<prefix><base>" (e.g. `MRD` = multiple, required, date)
   is mis-parsed. Current parser strips `M` only when the next char is a
   BASE letter. For `MRD` the next char is `R` (prefix), so M is NOT
   stripped, leading to base=M with `{R, D}` as modifiers. Correct
   interpretation should be base=D, is_multiple=True, required=True.
2. Lowercase modifiers (`a`, `t`, `m`, `p`, `w`) are captured as-is but
   their semantics are **not documented** in this codebase. Likely FileMan
   extension flags; confirm against VA Standards docs before phase 4
   variety analysis keys off them.

**Action:** flag as **open questions Q5 & Q6** in planning guide. Fix M-compound
parsing if phase 4 depends on accurate required/multiple detection. Look up
`a/t/I` semantics against official FileMan Programmer Manual.

---

## A6. Canonical number-range fallback table is accurate

**Claim:** The hardcoded `CANONICAL_RANGES` table in `attribution.py`
correctly maps VistA file numbers to packages.

**Status:** ⚠️ **UNVERIFIED — conservative by design, low impact**

**Evidence:** only 32 files (≈2% of phase-1.5 attributions) matched via
canonical range. The remaining 98% were attributed by prefix or empirical
range. All canonical-matched files are flagged with `confidence=low` and
are easily identifiable via the `method` column.

**Known caveat:** the table was compiled from general VistA knowledge
(FileMan 0.x, MAILMAN 3.x, KERNEL 4.x/9.x, SCHEDULING 40–46, PHARMACY
50–59, LAB 60–69, RADIOLOGY 70–74, PCE 80–81, ORE/RR 100–101, NEW PERSON
200). It omits many real ranges; files in unusual ranges fall through to
"unattributed" rather than being mis-attributed to a curated range.

**Action:** keep as-is. Downstream phases should treat
`confidence=low` + `method=range_canonical` as the weakest signal and
prefer to exclude or separately tag those files.

---

## A7. Phase-3 hub_files.csv is the right target set for phase-7 feed

**Claim:** The top-30 files by inbound-pointer count (phase-3 output)
identify the files whose FREE TEXT fields most warrant normalization.

**Status:** ⚠️ **UNVERIFIED — heuristic choice, not tested**

**Evidence:** hub_files.csv lists 30 files with inbound pointer counts
from 561 (NEW PERSON) to 14 (#30). The cutoff is arbitrary — nothing
indicates that #31 is qualitatively different from #30.

**Implication:** phase 1.6 output reflects one interpretation of "high
leverage." Phase 7 may want to re-run against a broader hub set (top 50,
top 100) or a different definition of "hub" (inbound + outbound,
pagerank, degree centrality).

**Action:** note in phase-1.6 report. Phase 7 should document its own
target-selection criteria.

---

## A8. FREE TEXT scoring rules (label-hint + transform + description)

**Claim:** Label substring hints (`date`, `code`, `id`, `number`, …) plus
presence of input transform and description together identify high-value
normalization candidates.

**Status:** ⚠️ **UNVERIFIED — heuristic, sample-checked only**

**Evidence:** top-ranked candidates on VEHU NEW PERSON file (ACCESS
CODE, VERIFY CODE, SSN, FILE MANAGER ACCESS CODE) are plausible phase-7
targets. But the weighting (+2/+2/+1) is not tuned against any labelled
outcome.

**Known caveats:**
- `STRUCTURED_HINTS` list is incomplete (no `duration`, `year`, `month`,
  `account`, `reference`, …).
- `^DD(f,fld,1)` — the INPUT TRANSFORM node — is empty for every
  FREE TEXT field on every hub file in VEHU (dev instance). Scoring
  collapses to label-hint + description only. Real-VA data should re-run
  phase 1.6 for the full signal.
- Scoring does **not** account for pointer fan-in on the containing file,
  field position (primary key vs. auxiliary), or any data-distribution
  metric. Those would require phase-5-style sampling of actual field
  values.

**Action:** phase 7 should treat the 105 high-score candidates as a
starting point, not a definitive list. Document any scoring refinements
in phase 7's own report.

---

## A9. The 139 residuals are data-quality issues in `^DIC(9.4)`

**Claim:** The unattributable files have namespaces (RC, OCX, GMR, XIP,
…) that do not match any package prefix, and this is because `^DIC(9.4)`
either lacks entries for those packages or has missing/incorrect prefix
fields.

**Status:** ⚠️ **UNVERIFIED at source**

**Evidence:** all 139 residual namespaces were checked against the 452
non-empty package prefixes in the inventory; none matched.

**What we did not verify:**
- Whether a package record exists for "ACCOUNTS RECEIVABLE (RC)" with an
  empty prefix, or is genuinely absent.
- Whether the `^DIC(9.4)` walk in `_read_packages` is complete — it skips
  entries with empty zero-nodes; a malformed entry could be silently
  dropped.

**Action:** if phase 2+ depends on these 139 being truly orphan (vs. a
walk bug), add a probe script that dumps all `^DIC(9.4)` zero-nodes raw
and cross-checks against the parsed package list. Not blocking for
phase 2 as long as the 139 are handled per DOWNSTREAM-RULES rule 3.

---

## A10. `FileInventory.summary().total_packages = 470` is accurate

**Claim:** VEHU has 470 packages.

**Status:** ⚠️ **MINOR DISCREPANCY**

**Evidence:** `^DIC(9.4)` walk shows:

| Counter | Value |
|--------:|------:|
| Numeric-IEN subscripts | 469 |
| …with zero-node | 468 |
| Reported `total_packages` | **470** |

The `_read_packages` function iterates all subscripts (numeric or not)
and keeps those with a zero-node. The reported 470 must include two
non-numeric-IEN zero-node entries (likely header metadata). Worth
verifying whether those should count.

**Action:** low priority. Document; revisit if phase analysis depends on
exact package count.

---

## New open questions raised by this audit

| ID | Question | Status |
|----|----------|--------|
| Q4 | Field-count 69k vs 47k discrepancy | **RESOLVED** by A3 — use 47k (top-level fields) |
| Q5 | Semantics of lowercase type modifiers (a, t, m, p, w)? | OPEN — look up in VA FileMan Programmer Manual |
| Q6 | Parser mis-handles M<prefix><base> compounds (e.g. MRD) | OPEN — fix if phase-4 variety analysis keys on required/multiple |
| Q7 | Are the 139 unattributable really absent from `^DIC(9.4)`, or walk artifacts? | OPEN — add raw-dump probe if phase 2 is sensitive |
| Q8 | `total_packages=470` vs numeric-IEN count of 469 — off-by-two | OPEN — low priority |

---

## Summary

| Assumption | Status |
|------------|--------|
| A1. 2,915 files | ✅ VERIFIED |
| A2. File-1 entries = total_files | ✅ VERIFIED |
| A3. ^DD subs ≠ file count; 47k is right field total | ✅ VERIFIED (Q4 closed) |
| A4. Prefix attribution correct | ✅ VERIFIED on sample |
| A5. Type-code rules | ⚠️ PARTIALLY (Q5, Q6 raised) |
| A6. Canonical range table | ⚠️ UNVERIFIED, low impact |
| A7. Phase-3 hubs as phase-7 targets | ⚠️ UNVERIFIED, heuristic |
| A8. FREE TEXT scoring | ⚠️ UNVERIFIED, heuristic |
| A9. 139 residuals = data quality | ⚠️ UNVERIFIED at source (Q7) |
| A10. 470 packages | ⚠️ MINOR DISCREPANCY (Q8) |

Five verified, five partial/unverified. None block phase 2, but the open
questions should be resolved or explicitly deferred before phases 4
(variety) and 7 (normalization) which depend on accurate type decomposition.
