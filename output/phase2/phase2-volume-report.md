# Phase 2 — Volume Survey

_Generated 2026-04-15 19:10 UTC_

## Summary

- **Total files scanned:** 2,915
- **Files with data:** 2,809 (96.4%)
- **Empty files:** 106
- **Total entries across all files:** 14,671,305

## Volume Tiers

| Tier | Range | Files |
|:-----|:------|------:|
| massive | >= 100,000 | 16 |
| large | 10,000 – 99,999 | 36 |
| medium | 1,000 – 9,999 | 141 |
| small | 100 – 999 | 318 |
| tiny | 1 – 99 | 2,298 |
| empty | 0 | 106 |

## Attribution Provenance (DOWNSTREAM-RULES rule 2)

| Provenance | File count |
|:-----------|-----------:|
| direct | 1,232 |
| prefix | 1,511 |
| range_empirical | 1 |
| range_canonical | 32 |
| unattributed | 139 |

## Top 25 Files by Entry Count

| Rank | File # | Label | Entries | Tier | Package | Provenance | Confidence |
|-----:|-------:|:------|--------:|:-----|:--------|:-----------|:-----------|
| 1 | 757.01 | EXPRESSIONS | 2,576,425 | massive | CLINICAL LEXICON UTILITY | direct | high |
| 2 | 129.22 | RXNORM RELATED CONCEPTS | 1,481,633 | massive | ENTERPRISE TERMINOLOGY SERVICE | prefix | med |
| 3 | 83.51 | DRG PDX EXCLUSION GROUPS | 1,134,568 | massive | DRG GROUPER | prefix | med |
| 4 | 129.21 | RXNORM SIMPLE CONCEPT AND ATOM ATTRIBUTES | 1,047,267 | massive | ENTERPRISE TERMINOLOGY SERVICE | prefix | med |
| 5 | 757.1 | SEMANTIC MAP | 961,805 | massive | CLINICAL LEXICON UTILITY | direct | high |
| 6 | 757.001 | CONCEPT USAGE | 905,351 | massive | LEXICON UTILITY | prefix | high |
| 7 | 757 | MAJOR CONCEPT MAP | 905,271 | massive | CLINICAL LEXICON UTILITY | direct | high |
| 8 | 757.02 | CODES | 855,566 | massive | CLINICAL LEXICON UTILITY | direct | high |
| 9 | 757.21 | SUBSETS | 604,524 | massive | CLINICAL LEXICON UTILITY | direct | high |
| 10 | 129.2 | RXNORM CONCEPT NAMES AND SOURCES | 565,254 | massive | ENTERPRISE TERMINOLOGY SERVICE | prefix | med |
| 11 | 363.2 | CHARGE ITEM | 435,241 | massive | INTEGRATED BILLING | prefix | med |
| 12 | 129.23 | RXNORM SEMANTIC TYPES | 425,575 | massive | ENTERPRISE TERMINOLOGY SERVICE | prefix | med |
| 13 | 50.67 | NDC/UPN | 329,259 | massive | NATIONAL DRUG FILE | prefix | med |
| 14 | 757.033 | CHARACTER POSITIONS | 220,926 | massive | LEXICON UTILITY | prefix | high |
| 15 | 601.751 | MH CHOICETYPES | 108,956 | massive | PSYCHODIAGNOSTICS | prefix | med |
| 16 | 95.3 | LAB LOINC | 104,671 | massive | AUTOMATED LAB INSTRUMENTS | prefix | med |
| 17 | 5.11 | ZIP CODE | 93,026 | large | ONCOLOGY | direct | high |
| 18 | 80 | ICD DIAGNOSIS | 91,279 | large | DRG GROUPER | direct | high |
| 19 | 80.1 | ICD OPERATION/PROCEDURE | 86,813 | large | DRG GROUPER | direct | high |
| 20 | 712.5 | GMT THRESHOLDS | 81,445 | large | ENROLLMENT APPLICATION SYSTEM | prefix | high |
| 21 | 129.1 | LOINC | 76,265 | large | ENTERPRISE TERMINOLOGY SERVICE | prefix | med |
| 22 | 83.5 | DRG DIAGNOSIS | 67,975 | large | DRG GROUPER | prefix | med |
| 23 | 357.3 | SELECTION | 66,036 | large | INTEGRATED BILLING | direct | high |
| 24 | 83.6 | DRG PROCEDURE | 61,902 | large | DRG GROUPER | prefix | med |
| 25 | 95.31 | LAB LOINC COMPONENT | 59,948 | large | AUTOMATED LAB INSTRUMENTS | prefix | med |

## Top 15 Packages by Total Entries

| Rank | Package | Total Entries | Files | Provenance mix |
|-----:|:--------|--------------:|------:|:---------------|
| 1 | CLINICAL LEXICON UTILITY | 5,904,415 | 15 | direct=15 |
| 2 | ENTERPRISE TERMINOLOGY SERVICE | 3,640,172 | 10 | prefix=10 |
| 3 | DRG GROUPER | 1,454,633 | 25 | prefix=22, direct=3 |
| 4 | LEXICON UTILITY | 1,188,735 | 14 | prefix=14 |
| 5 | INTEGRATED BILLING | 544,292 | 240 | prefix=159, direct=81 |
| 6 | NATIONAL DRUG FILE | 389,508 | 12 | prefix=3, direct=9 |
| 7 | PSYCHODIAGNOSTICS | 203,701 | 30 | prefix=30 |
| 8 | AUTOMATED LAB INSTRUMENTS | 175,555 | 30 | prefix=25, direct=5 |
| 9 | ENROLLMENT APPLICATION SYSTEM | 131,639 | 10 | prefix=10 |
| 10 | (unattributed) | 126,680 | 139 | unattributed=139 |
| 11 | ONCOLOGY | 108,130 | 67 | direct=27, prefix=40 |
| 12 | ORDER ENTRY/RESULTS REPORTING | 80,660 | 47 | direct=16, prefix=31 |
| 13 | FEE BASIS | 73,559 | 51 | prefix=18, direct=33 |
| 14 | LAB SERVICE | 68,069 | 56 | direct=52, prefix=4 |
| 15 | NURSING FIXES | 56,619 | 1 | direct=1 |

## Unattributed bucket (DOWNSTREAM-RULES rule 3)

- **Files:** 139
- **Total entries:** 126,680

Top 10 unattributed by volume:

| File # | Label | Entries | Global |
|-------:|:------|--------:|:-------|
| 5.12 | POSTAL CODE | 56,622 | `^XIP(5.12,` |
| 409.68 | OUTPATIENT ENCOUNTER | 14,352 | `^SCE(` |
| 9000010 | VISIT | 14,125 | `^AUPNVSIT(` |
| 9000010.18 | V CPT | 7,299 | `^AUPNVCPT(` |
| 9000010.06 | V PROVIDER | 6,283 | `^AUPNVPRV(` |
| 9999999.64 | HEALTH FACTORS | 5,936 | `^AUTTHF(` |
| 9999999.06 | LOCATION | 5,033 | `^AUTTLOC(` |
| 5.13 | COUNTY CODE | 3,328 | `^XIP(5.13,` |
| 9000001 | PATIENT/IHS | 1,756 | `^AUPNPAT(` |
| 509850.1 | A&SP DIAGNOSTIC CONDITION | 1,228 | `^ACK(509850.1,` |

## Output Files

- `file_volume.json` — full per-file volume data (with provenance)
- `file_volume.csv` — same data flat
- `summary.json` — tier counts, top files, per-package totals, provenance
- `phase2_volume.png` — visualization (generated by phase2-viz.py)
