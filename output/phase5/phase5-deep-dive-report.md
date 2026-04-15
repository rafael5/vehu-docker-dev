# Phase 5 — Schema Deep Dive: File #2 (PATIENT)

_Generated 2026-04-14 22:39 UTC_

## Summary

- **Total fields:** 594
- **With description:** 569 (95.8%)
- **With input transform:** 558 (93.9%)
- **With SET values:** 116 (19.5%)
- **With help prompt:** 514 (86.5%)
- **Storage nodes:** 122
- **Largest node:** `.141` with 22 fields
- **Cross-references:** 111

## Storage Nodes

| Node | Fields |
|:----:|------:|
|   | 7 |
| 0 | 19 |
| 1 | 1 |
| 2 | 9 |
| 3 | 1 |
| 4 | 1 |
| 5 | 1 |
| E | 1 |
| S | 1 |
| .1 | 1 |
| .3 | 14 |
| 57 | 3 |
| DE | 1 |
| LR | 1 |
| PC | 2 |
| PH | 1 |
| PI | 1 |
| .01 | 1 |
| .02 | 1 |
| .06 | 1 |
| .11 | 18 |
| .13 | 19 |
| .14 | 1 |
| .15 | 2 |
| .16 | 1 |
| .17 | 1 |
| .18 | 1 |
| .21 | 15 |
| .22 | 7 |
| .24 | 7 |
| .25 | 11 |
| .29 | 13 |
| .31 | 4 |
| .32 | 19 |
| .33 | 15 |
| .34 | 15 |
| .35 | 7 |
| .36 | 9 |
| .37 | 1 |
| .38 | 3 |
| .39 | 9 |
| .52 | 11 |
| .53 | 4 |
| .54 | 4 |
| .55 | 2 |
| .56 | 1 |
| .57 | 6 |
| 2.1 | 1 |
| 2.2 | 1 |
| 2.3 | 1 |
| DAC | 2 |
| DIS | 1 |
| ENR | 4 |
| FFP | 6 |
| HBP | 1 |
| INE | 7 |
| INS | 1 |
| LRT | 1 |
| MPI | 11 |
| NHC | 1 |
| ODS | 3 |
| SSN | 2 |
| VET | 1 |
| .025 | 1 |
| .101 | 1 |
| .102 | 1 |
| .103 | 1 |
| .104 | 1 |
| .105 | 1 |
| .106 | 1 |
| .107 | 1 |
| .108 | 1 |
| .109 | 1 |
| .115 | 16 |
| .121 | 17 |
| .122 | 3 |
| .132 | 14 |
| .141 | 22 |
| .207 | 1 |
| .211 | 15 |
| .212 | 2 |
| .241 | 2 |
| .291 | 10 |
| .311 | 11 |
| .312 | 1 |
| .321 | 17 |
| .322 | 21 |
| .331 | 14 |
| .332 | 3 |
| .361 | 8 |
| .362 | 18 |
| .372 | 1 |
| .373 | 1 |
| .385 | 11 |
| .396 | 1 |
| .397 | 1 |
| .398 | 1 |
| .399 | 1 |
| .401 | 1 |
| 3000 | 1 |
| ARCH | 1 |
| DENT | 2 |
| HBP1 | 1 |
| KATR | 1 |
| NAME | 9 |
| TYPE | 1 |
| .1041 | 1 |
| .2406 | 1 |
| .3215 | 1 |
| .3216 | 1 |
| .3217 | 4 |
| .3291 | 3 |
| MPIMB | 1 |
| .32171 | 1 |
| 500001 | 1 |
| 537025 | 1 |
| CERNER | 1 |
| 1010.15 | 14 |
| 1010.16 | 4 |
| MPICMOR | 1 |
| MPIFHIS | 1 |
| MPIFICNHIS | 1 |

## Field Preview (first 20)

| Field # | Label | Type | Storage |
|--------:|:------|:-----|:--------|
| 0.0100 | NAME | FREE TEXT | 0;1 |
| 0.0200 | SEX | SET OF CODES | 0;2 |
| 0.0240 | SELF IDENTIFIED GENDER | SET OF CODES | .24;4 |
| 0.0250 | SEXUAL ORIENTATION | POINTER | .025;0 |
| 0.0251 | SEXUAL ORIENTATION FREE TEXT | FREE TEXT | .241;1 |
| 0.0300 | DATE OF BIRTH | DATE/TIME | 0;3 |
| 0.0330 | AGE | COMPUTED |  ;  |
| 0.0500 | MARITAL STATUS | POINTER | 0;5 |
| 0.0600 | RACE | POINTER | 0;6 |
| 0.0700 | OCCUPATION | FREE TEXT | 0;7 |
| 0.0800 | RELIGIOUS PREFERENCE | POINTER | 0;8 |
| 0.0810 | DUPLICATE STATUS | SET OF CODES | 0;18 |
| 0.0820 | PATIENT MERGED TO | POINTER | 0;19 |
| 0.0830 | CHECK FOR DUPLICATE | SET OF CODES | 0;20 |
| 0.0900 | SOCIAL SECURITY NUMBER | FREE TEXT | 0;9 |
| 0.0901 | TERMINAL DIGIT OF SSN | COMPUTED |  ;  |
| 0.0905 | 1U4N | COMPUTED |  ;  |
| 0.0906 | PSEUDO SSN REASON | SET OF CODES | SSN;1 |
| 0.0907 | SSN VERIFICATION STATUS | SET OF CODES | SSN;2 |
| 0.0910 | REMARKS | FREE TEXT | 0;10 |

## Output Files

- `schema_2.json` / `.csv` — per-field extended attributes
- `storage_2.json` — storage-node layout
- `cross_refs_2.json` — cross-reference inventory
- `summary_2.json` — stats (consumed by viz + report)
- `phase5_schema_2.png` — completeness heatmap (phase5-viz.py)
