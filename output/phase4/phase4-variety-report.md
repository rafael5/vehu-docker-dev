# Phase 4 — Data Variety and Naming Analysis

_Generated 2026-04-14 22:44 UTC_

## Summary

- **Unique field labels:** 32,107
- **SET-OF-CODES fields with values:** 9,391
- **Shared value sets (reused ≥5 fields):** 121
- **Label-type inconsistencies (≥5 fields, ≥2 types):** 416
- **Boolean pattern variants:** 4

## Top 20 Most-Common Field Labels

| Label | Count |
|:------|------:|
| NAME | 1,055 |
| DESCRIPTION | 374 |
| CODE | 311 |
| STATUS | 246 |
| NUMBER | 214 |
| PATIENT | 214 |
| TYPE | 177 |
| INACTIVE? | 112 |
| ABBREVIATION | 111 |
| PLACEHOLDER | 99 |
| DIVISION | 90 |
| SYNONYM | 90 |
| USER | 83 |
| COMMENTS | 77 |
| DATE | 71 |
| STATE | 71 |
| INACTIVE | 69 |
| PATIENT NAME | 68 |
| ACTIVE | 60 |
| LOCATION | 57 |

## Top 15 Label-Type Inconsistencies

| Label | Occurrences | Files | Types |
|:------|------------:|------:|:------|
| NAME | 1055 | 1055 | F:921, P:93, :20, X:3, C:1, N:7, V:7, S:3 |
| DESCRIPTION | 374 | 374 | M:148, F:216, A:4, D:5, P:1 |
| CODE | 311 | 311 | F:249, N:51, P:5, A:4, S:1, M:1 |
| STATUS | 246 | 246 | S:180, F:17, D:3, P:40, C:4, N:2 |
| NUMBER | 214 | 214 | N:204, F:9, P:1 |
| PATIENT | 214 | 214 | C:3, P:204, F:6, V:1 |
| TYPE | 177 | 177 | S:131, P:19, F:25, A:2 |
| ABBREVIATION | 111 | 111 | F:110, M:1 |
| PLACEHOLDER | 99 | 16 | F:92, P:4, N:2, S:1 |
| DIVISION | 90 | 90 | C:1, P:80, A:1, F:8 |
| SYNONYM | 90 | 90 | F:33, M:44, A:12, N:1 |
| USER | 83 | 83 | P:80, F:3 |
| COMMENTS | 77 | 76 | M:41, F:33, D:2, A:1 |
| DATE | 71 | 70 | D:69, C:1, F:1 |
| STATE | 71 | 71 | P:51, C:4, F:16 |

## Boolean-Equivalent Patterns

| Codes | Fields | Files |
|:------|-------:|------:|
| `{'Y': 'YES', 'N': 'NO'}` | 1156 | 246 |
| `{'0': 'NO', '1': 'YES'}` | 2081 | 629 |
| `{'A': 'ACTIVE', 'I': 'INACTIVE'}` | 29 | 28 |
| `{'1': 'ACTIVE', '0': 'INACTIVE'}` | 44 | 43 |

## Output Files

- `label_frequency.csv` — every label with count
- `label_type_inconsistency.csv` — same-label/different-type conflicts
- `shared_sets.json` — reused SET value sets
- `canonical_positions.json` — standard-position field analysis
- `summary.json` — top-N slices (consumed by viz + report)
- `phase4_*.png` — visualizations (from phase4-viz.py)
