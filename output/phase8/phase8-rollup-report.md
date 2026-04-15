# Phase 8 — Normalization Rollup

_Generated 2026-04-14 22:44 UTC_

_Combined summary of phases 1–7. See each phase's own report for details._

## Scope (Phase 1)

- **Files:** 2,915  /  **Packages:** 470  /  **Fields:** 69,328
- **Files with data:** 2,858  /  **Empty:** 57  /  **Total entries:** 717,892

## Volume Tiers (Phase 2)

| Tier | Count |
|:-----|------:|
| massive | 0 |
| large | 7 |
| medium | 117 |
| small | 259 |
| tiny | 2,475 |
| empty | 57 |

## Topology (Phase 3)

- **Pointer edges:** 6,632
- **Hub files (≥10 inbound):** 58
- **Variable-pointer fields:** 99
- **MULTIPLE (sub-file) fields:** 1,582

### Top 10 Hubs

| File # | Label | Inbound |
|-------:|:------|--------:|
| 200 | NEW PERSON | 561 |
| 2 | PATIENT | 314 |
| 4 | INSTITUTION | 209 |
| 44 | HOSPITAL LOCATION | 115 |
| 5 | STATE | 81 |
| 40.8 | MEDICAL CENTER DIVISION | 53 |
| 3.5 | DEVICE | 49 |
| 3.8 | MAIL GROUP | 43 |
| 9000010 | VISIT | 41 |
| 1 | FILE | 40 |

## Variety (Phase 4)

- **Unique labels:** 32,107
- **SET fields with values:** 9,391
- **Shared value sets (≥5 fields):** 121
- **Label-type inconsistencies:** 416

## Normalization Candidates (Phase 7)

- **Total:** 752
- **Priority range:** median=6, max=1055

### By Rule

| Rule | Count |
|:-----|------:|
| label_type_conflict | 416 |
| date_as_free_text | 227 |
| hub_file_reference | 58 |
| pointer_to_empty_file | 51 |

## Next Steps

- Open output files in `~/data/vista-fm-browser/`
- Filter `phase7/normalization_candidates.json` by `priority >= 10` for the short list
- Start Flask UI: `fm-browser serve` → http://localhost:5000
