# Phase 6 — Data Coverage: File #2 (PATIENT)

_Generated 2026-04-14 22:19 UTC_

## Summary

- **Sample size:** 500 entries
- **Total fields:** 594
- **Well-populated (≥80%):** 5
- **Partially populated (20–80%):** 5
- **Sparse (0–20%):** 3
- **Zero coverage:** 581

## Top 20 Best-Populated Fields

| Field | Label | Type | Coverage |
|------:|:------|:-----|---------:|
| 0.0100 | NAME | FREE TEXT | 99.8% |
| 0.0300 | DATE OF BIRTH | DATE/TIME | 99.8% |
| 0.0900 | SOCIAL SECURITY NUMBER | FREE TEXT | 99.8% |
| 0.1600 | MISSING OR INELIGIBLE | ADDRESS | 95.0% |
| 0.0200 | SEX | SET OF CODES | 89.2% |
| 0.0500 | MARITAL STATUS | POINTER | 52.4% |
| 0.0800 | RELIGIOUS PREFERENCE | POINTER | 47.2% |
| 0.1400 | CURRENT MEANS TEST STATUS | POINTER | 38.6% |
| 0.0700 | OCCUPATION | FREE TEXT | 33.0% |
| 0.0600 | RACE | POINTER | 24.8% |
| 0.1200 | ADDRESS CHANGE SITE | POINTER | 14.4% |
| 0.1000 | WARD LOCATION | FREE TEXT | 6.4% |
| 0.1900 | DIVISION | COMPUTED | 0.2% |
| 0.0240 | SELF IDENTIFIED GENDER | SET OF CODES | 0.0% |
| 0.0250 | SEXUAL ORIENTATION | POINTER | 0.0% |
| 0.0251 | SEXUAL ORIENTATION FREE TEXT | FREE TEXT | 0.0% |
| 0.0330 | AGE | COMPUTED | 0.0% |
| 0.0810 | DUPLICATE STATUS | SET OF CODES | 0.0% |
| 0.0820 | PATIENT MERGED TO | POINTER | 0.0% |
| 0.0830 | CHECK FOR DUPLICATE | SET OF CODES | 0.0% |

## Top 20 Zero-Coverage Fields (candidates for retirement)

| Field | Label | Type |
|------:|:------|:-----|
| 0.0240 | SELF IDENTIFIED GENDER | SET OF CODES |
| 0.0250 | SEXUAL ORIENTATION | POINTER |
| 0.0251 | SEXUAL ORIENTATION FREE TEXT | FREE TEXT |
| 0.0330 | AGE | COMPUTED |
| 0.0810 | DUPLICATE STATUS | SET OF CODES |
| 0.0820 | PATIENT MERGED TO | POINTER |
| 0.0830 | CHECK FOR DUPLICATE | SET OF CODES |
| 0.0901 | TERMINAL DIGIT OF SSN | COMPUTED |
| 0.0905 | 1U4N | COMPUTED |
| 0.0906 | PSEUDO SSN REASON | SET OF CODES |
| 0.0907 | SSN VERIFICATION STATUS | SET OF CODES |
| 0.0910 | REMARKS | FREE TEXT |
| 0.0920 | PLACE OF BIRTH [CITY] | FREE TEXT |
| 0.0930 | PLACE OF BIRTH [STATE] | POINTER |
| 0.0931 | PLACE OF BIRTH COUNTRY | POINTER |
| 0.0932 | PLACE OF BIRTH PROVINCE | FREE TEXT |
| 0.0960 | WHO ENTERED PATIENT | POINTER |
| 0.0970 | DATE ENTERED INTO FILE | DATE/TIME |
| 0.0980 | HOW WAS PATIENT ENTERED? | SET OF CODES |
| 0.1010 | ROOM-BED | FREE TEXT |

## Output Files

- `coverage_2.json` / `.csv` — full per-field coverage
- `summary.json` — stats (consumed by viz + report)
- `phase6_coverage_2.png` — bar chart (phase6-viz.py)
