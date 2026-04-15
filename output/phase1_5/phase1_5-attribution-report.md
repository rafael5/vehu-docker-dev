# Phase 1.5 — Package Attribution Report

_Generated 2026-04-15 15:48 UTC_

## Summary

- Input files analyzed: **1,683** (phase-1 unpackaged)
- Attributed: **1,544** (91.7%)
- Still unattributed: **139**

## Attribution by method

| Method | Count |
|:-------|------:|
| range_canonical | 32 |
| prefix | 1,511 |
| (none) | 139 |
| range_empirical | 1 |

## Attribution by confidence

| Confidence | Count |
|:-----------|------:|
| low | 32 |
| med | 874 |
| high | 638 |
| (none) | 139 |

## Top 20 newly-attributed packages

| Rank | Package | New files |
|-----:|:--------|----------:|
| 1 | IMAGING | 165 |
| 2 | INTEGRATED BILLING | 159 |
| 3 | VA FILEMAN | 69 |
| 4 | REGISTRATION | 64 |
| 5 | SCHEDULING | 57 |
| 6 | PHARMACY | 54 |
| 7 | E CLAIMS MGMT ENGINE | 44 |
| 8 | CLINICAL PROCEDURES | 43 |
| 9 | ONCOLOGY | 40 |
| 10 | DSS EXTRACTS | 37 |
| 11 | TEXT INTEGRATION UTILITIES | 34 |
| 12 | ASISTS | 32 |
| 13 | ORDER ENTRY/RESULTS REPORTING | 31 |
| 14 | IFCAP | 31 |
| 15 | PSYCHODIAGNOSTICS | 30 |
| 16 | CLINICAL REMINDERS | 29 |
| 17 | RELEASE OF INFORMATION - DSSI | 28 |
| 18 | AUTOMATED LAB INSTRUMENTS | 25 |
| 19 | WOMEN'S HEALTH | 25 |
| 20 | DRG GROUPER | 22 |

## Method priority

1. **prefix** — global-root namespace matches a package prefix (longest wins). `high` confidence on exact match, `med` on longer-namespace longest-prefix.
2. **range_empirical** — file number falls inside exactly one package's observed min/max range from phase 1. `med` if ≥3 anchors, else `low`.
3. **range_canonical** — file number falls in a curated VistA canonical range table (PHARMACY 50–59.999, LAB 60–69.999, etc.). Always `low`.

## Known limitations

- The canonical range table is conservative — only well-documented VA ranges are encoded. Unattributed files in unusual ranges stay unattributed.
- Range-empirical treats overlapping ranges as ambiguous and skips.
- FileMan-internal files (`^DD`, `^DIC(.2,` etc.) attribute to VA FILEMAN / KERNEL via prefix and canonical rules.

## Output files

- `attribution_candidates.csv` — one row per analyzed file
- `attribution_summary.json` — structured summary for downstream phases
