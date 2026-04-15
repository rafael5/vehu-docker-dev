# Phase 1.6 — Free-Text Normalization Targets

_Generated 2026-04-15 16:14 UTC_

Feeder report for phase 7. Ranks FREE TEXT fields on phase-3 hub
files by a composite score (label hints + input transform + description).

## Summary

- Hub files analyzed: **30** (from `output/phase3/hub_files.csv`)
- FREE TEXT fields on hubs: **590**
- Scored ≥3 (high-interest): **105**
- With input transform: **0**
- With description: **282**

## Top 30 candidates

| Rank | File | Field | Score | Reasons |
|-----:|:-----|:------|------:|:--------|
| 1 | NEW PERSON (200.0) | ACCESS CODE (2.0) | 3 | label contains 'code'; has description |
| 2 | NEW PERSON (200.0) | Want to edit ACCESS CODE (Y/N) (2.1) | 3 | label contains 'code'; has description |
| 3 | NEW PERSON (200.0) | FILE MANAGER ACCESS CODE (3.0) | 3 | label contains 'code'; has description |
| 4 | NEW PERSON (200.0) | SSN (9.0) | 3 | label contains 'ssn'; has description |
| 5 | NEW PERSON (200.0) | VERIFY CODE (11.0) | 3 | label contains 'code'; has description |
| 6 | NEW PERSON (200.0) | Want to edit VERIFY CODE (Y/N) (11.1) | 3 | label contains 'code'; has description |
| 7 | NEW PERSON (200.0) | DATE VERIFY CODE LAST CHANGED (11.2) | 3 | label contains 'date'; has description |
| 8 | NEW PERSON (200.0) | HINQ EMPLOYEE NUMBER (14.9) | 3 | label contains 'number'; has description |
| 9 | NEW PERSON (200.0) | PROHIBITED TIMES FOR SIGN-ON (15.0) | 3 | label contains 'time'; has description |
| 10 | NEW PERSON (200.0) | DATE E-SIG LAST CHANGED (20.1) | 3 | label contains 'date'; has description |
| 11 | NEW PERSON (200.0) | ELECTRONIC SIGNATURE CODE (20.4) | 3 | label contains 'code'; has description |
| 12 | NEW PERSON (200.0) | MAIL CODE (28.0) | 3 | label contains 'code'; has description |
| 13 | NEW PERSON (200.0) | DETOX/MAINTENANCE ID NUMBER (53.11) | 3 | label contains 'number'; has description |
| 14 | NEW PERSON (200.0) | TAX ID (53.92) | 3 | label contains 'id'; has description |
| 15 | NEW PERSON (200.0) | TIMESTAMP (203.1) | 3 | label contains 'time'; has description |
| 16 | NEW PERSON (200.0) | SECID (205.1) | 3 | label contains 'id'; has description |
| 17 | NEW PERSON (200.0) | SUBJECT ORGANIZATION ID (205.3) | 3 | label contains 'id'; has description |
| 18 | NEW PERSON (200.0) | UNIQUE USER ID (205.4) | 3 | label contains 'id'; has description |
| 19 | NEW PERSON (200.0) | VPID (9000.0) | 3 | label contains 'id'; has description |
| 20 | PATIENT (2.0) | TEMPORARY ID NUMBER (991.08) | 3 | label contains 'number'; has description |
| 21 | PATIENT (2.0) | FOREIGN ID NUMBER (991.09) | 3 | label contains 'number'; has description |
| 22 | PATIENT (2.0) | NETWORK IDENTIFIER (537025.0) | 3 | label contains 'id'; has description |
| 23 | INSTITUTION (4.0) | ZIP (1.04) | 3 | label contains 'zip'; has description |
| 24 | INSTITUTION (4.0) | ZIP (MAILING) (4.05) | 3 | label contains 'zip'; has description |
| 25 | INSTITUTION (4.0) | ACOS HOSPITAL ID (51.0) | 3 | label contains 'id'; has description |
| 26 | INSTITUTION (4.0) | FACILITY DEA NUMBER (52.0) | 3 | label contains 'number'; has description |
| 27 | INSTITUTION (4.0) | STATION NUMBER (99.0) | 3 | label contains 'number'; has description |
| 28 | HOSPITAL LOCATION (44.0) | TELEPHONE (99.0) | 3 | label contains 'phone'; has description |
| 29 | HOSPITAL LOCATION (44.0) | TELEPHONE EXTENSION (99.1) | 3 | label contains 'phone'; has description |
| 30 | HOSPITAL LOCATION (44.0) | EAS TRACKING NUMBER (100.0) | 3 | label contains 'number'; has description |

## Scoring rules

- Label hint match (date/time/code/id/number/...): +2 (once)
- Has input transform: +2 (VEHU instance has none populated — all scores reflect label+description only)
- Has description: +1

## VEHU data-quality note

`^DD(file, field, 1)` — the INPUT TRANSFORM node — is empty for every FREE TEXT field on every hub file in this VEHU instance. This is expected for a dev/test VistA; production instances carry M-code input validators here that would dramatically sharpen scoring. When phase 7 runs against real VA data, re-run this script to pick up the transform signal.

## Next step (phase 7)

Phase 7 should use the CSV as its primary target list, sorted by `score` DESC then `hub_inbound_count` DESC. Per `DOWNSTREAM-RULES.md` rule 2, carry hub package + confidence context forward when reporting candidates.
