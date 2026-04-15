# vista-fm-browser — archived proof-of-concept

**Status:** this repo is a proof-of-concept for FileMan analysis via
direct YottaDB global reads. It was the ancestor of the
[**fm-web**](https://github.com/rafael5/fm-web) project (clean-sheet
rewrite, RPC-only, portable across IRIS/YDB, no KIDS build) — which
supersedes it for active work.

Retained here as-is for reference:

- Phases 1–8 analysis outputs under `output/phaseN/` — the corpus-wide
  survey of 2,915 FileMan files / 46,790 fields in VEHU, culminating in
  the 14.67M-entry total discovered in phase-2 iteration 4.
- Source code (`src/vista_fm_browser/`) demonstrating the FileMan
  global-walker approach, with all its edge-case fixes.
- Planning guides and assumption audits documenting the iterative
  process.

The lessons learned here live on in
[`fm-web/docs/LESSONS-LEARNED.md`](https://github.com/rafael5/fm-web/blob/main/docs/LESSONS-LEARNED.md)
— 30 numbered lessons that informed every architectural choice in the
successor project.

**Do not extend** this repo. New analysis work should either consume
fm-web's API surface, or land in fm-web itself.
