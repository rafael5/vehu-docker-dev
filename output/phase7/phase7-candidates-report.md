# Phase 7 — Normalization Candidates

_Generated 2026-04-14 22:44 UTC_

## Summary

- **Total candidates:** 752
- **Max priority:** 1055
- **Median priority:** 6

### By Rule

| Rule | Count |
|:-----|------:|
| label_type_conflict | 416 |
| date_as_free_text | 227 |
| hub_file_reference | 58 |
| pointer_to_empty_file | 51 |

## Top 25 Candidates

| Rank | Priority | Rule | Target | Detail |
|-----:|---------:|:-----|:-------|:-------|
| 1 | 1055 | label_type_conflict | NAME | F:921, P:93, :20, X:3, C:1, N:7, V:7, S:3 |
| 2 | 561 | hub_file_reference | File #200.0 NEW PERSON | 561 refs |
| 3 | 374 | label_type_conflict | DESCRIPTION | M:148, F:216, A:4, D:5, P:1 |
| 4 | 314 | hub_file_reference | File #2.0 PATIENT | 314 refs |
| 5 | 311 | label_type_conflict | CODE | F:249, N:51, P:5, A:4, S:1, M:1 |
| 6 | 246 | label_type_conflict | STATUS | S:180, F:17, D:3, P:40, C:4, N:2 |
| 7 | 214 | label_type_conflict | NUMBER | N:204, F:9, P:1 |
| 8 | 214 | label_type_conflict | PATIENT | C:3, P:204, F:6, V:1 |
| 9 | 209 | hub_file_reference | File #4.0 INSTITUTION | 209 refs |
| 10 | 177 | label_type_conflict | TYPE | S:131, P:19, F:25, A:2 |
| 11 | 115 | hub_file_reference | File #44.0 HOSPITAL LOCATION | 115 refs |
| 12 | 111 | label_type_conflict | ABBREVIATION | F:110, M:1 |
| 13 | 99 | label_type_conflict | PLACEHOLDER | F:92, P:4, N:2, S:1 |
| 14 | 90 | label_type_conflict | DIVISION | C:1, P:80, A:1, F:8 |
| 15 | 90 | label_type_conflict | SYNONYM | F:33, M:44, A:12, N:1 |
| 16 | 83 | label_type_conflict | USER | P:80, F:3 |
| 17 | 81 | hub_file_reference | File #5.0 STATE | 81 refs |
| 18 | 77 | label_type_conflict | COMMENTS | M:41, F:33, D:2, A:1 |
| 19 | 71 | label_type_conflict | DATE | D:69, C:1, F:1 |
| 20 | 71 | label_type_conflict | STATE | P:51, C:4, F:16 |
| 21 | 69 | label_type_conflict | INACTIVE | S:64, D:4, C:1 |
| 22 | 68 | label_type_conflict | PATIENT NAME | P:52, F:14, V:2 |
| 23 | 60 | label_type_conflict | ACTIVE | S:59, C:1 |
| 24 | 57 | label_type_conflict | LOCATION | C:2, F:22, V:1, P:32 |
| 25 | 55 | label_type_conflict | CITY | F:53, C:2 |

## Output Files

- `normalization_candidates.json` / `.csv` — full ranked list
- `summary.json` — counts by rule (consumed by viz + report)
- `phase7_candidates.png` — bar + scatter visualization (phase7-viz.py)
