# Phase 3 — Structural Topology

_Generated 2026-04-14 22:44 UTC_

## Summary

- **Pointer edges:** 6,632
- **Unique source files:** 1,587
- **Unique target files:** 1,175
- **Hub files (≥10 inbound):** 58
- **Variable pointer fields (V-type):** 99
- **MULTIPLE fields (sub-files, M-type):** 1,582

## Top 20 Hub Files (most referenced)

| Rank | File # | Label | Package | Inbound |
|-----:|-------:|:------|:--------|--------:|
| 1 | 200 | NEW PERSON | SOCIAL WORK | 561 |
| 2 | 2 | PATIENT | PATIENT FILE | 314 |
| 3 | 4 | INSTITUTION | KERNEL | 209 |
| 4 | 44 | HOSPITAL LOCATION | SCHEDULING | 115 |
| 5 | 5 | STATE | PATIENT FILE | 81 |
| 6 | 40.8 | MEDICAL CENTER DIVISION | REGISTRATION | 53 |
| 7 | 3.5 | DEVICE | KERNEL | 49 |
| 8 | 3.8 | MAIL GROUP | MAILMAN | 43 |
| 9 | 9000010 | VISIT | (unpackaged) | 41 |
| 10 | 1 | FILE | (unpackaged) | 40 |
| 11 | 100 | ORDER | ORDER ENTRY/RESULTS REPORTING | 38 |
| 12 | 49 | SERVICE/SECTION | INTERIM MANAGEMENT SUPPORT | 37 |
| 13 | 80 | ICD DIAGNOSIS | DRG GROUPER | 35 |
| 14 | 81 | CPT | REGISTRATION | 35 |
| 15 | 9.4 | PACKAGE | KERNEL | 33 |
| 16 | 405 | PATIENT MOVEMENT | REGISTRATION | 32 |
| 17 | 50 | DRUG | CONTROLLED SUBSTANCES | 30 |
| 18 | 4.2 | DOMAIN | MAILMAN | 27 |
| 19 | 36 | INSURANCE COMPANY | REGISTRATION | 24 |
| 20 | 42 | WARD LOCATION | REGISTRATION | 24 |

## Top 15 Outbound-Dense Files (most FK-rich)

| Rank | File # | Label | Package | Outbound |
|-----:|-------:|:------|:--------|---------:|
| 1 | 165.5 | ONCOLOGY PRIMARY | ONCOLOGY | 43 |
| 2 | 2 | PATIENT | PATIENT FILE | 36 |
| 3 | 356.22 | HCS REVIEW TRANSMISSION | (unpackaged) | 32 |
| 4 | 130 | SURGERY | SURGERY | 27 |
| 5 | 2260 | ASISTS ACCIDENT REPORTING | (unpackaged) | 27 |
| 6 | 399 | BILL/CLAIMS | UB-82 BILLING | 24 |
| 7 | 442 | PROCUREMENT & ACCOUNTING TRANSACTIONS | IFCAP | 22 |
| 8 | 6914 | EQUIPMENT INV. | ENGINEERING | 22 |
| 9 | 2005 | IMAGE | (unpackaged) | 19 |
| 10 | 162.5 | FEE BASIS INVOICE | FEE BASIS | 18 |
| 11 | 200 | NEW PERSON | SOCIAL WORK | 18 |
| 12 | 405 | PATIENT MOVEMENT | REGISTRATION | 18 |
| 13 | 2005.1 | IMAGE AUDIT | (unpackaged) | 18 |
| 14 | 660 | RECORD OF PROS APPLIANCE/REPAIR | PROSTHETICS | 17 |
| 15 | 9000010.11 | V IMMUNIZATION | (unpackaged) | 17 |

## Output Files

- `all_fields.json` — full schema cache (for phases 4, 7, 8)
- `pointer_graph.json` / `.csv` — edge list
- `hub_files.csv` — files with ≥10 inbound pointers
- `summary.json` — topology stats (consumed by viz + report)
- `phase3_pointer_graph.png` / `.dot` — graph visualizations
- `phase3_pkg_matrix.png` — cross-package dependency heatmap
