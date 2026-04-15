# Downstream Operating Rules — Phases 2–8

> Consumed by every phase after phase 1. If you are working on phase 2+, read
> this first. Updated when phase 1 re-runs invalidate prior assumptions.

Last updated: 2026-04-15 (iteration 1.5)

---

## Rule 1 — Use the locked canonical denominator

All file-level statistics use these numbers:

| Metric | Value |
|--------|------:|
| Total files | **2,915** |
| Packaged (phase 1 direct) | 1,232 |
| Attributed (phase 1.5 heuristics) | 1,544 |
| **Effective attributed** | **2,776 (95.2%)** |
| Residual unattributed | 139 (4.8%) |

Do not recompute these from a fresh walk unless phase 1 has been re-run and
the planning guide updated. If you need a different denominator for a
specific analysis, document the filter explicitly in that phase's report.

---

## Rule 2 — Carry attribution confidence forward

Phase 1.5 produces one `Attribution` per formerly-unpackaged file, with a
`confidence` of `high`, `med`, `low`, or `""` (unattributed).

When a downstream phase groups by package, it **must** carry confidence
forward so a later consumer can filter. Never silently merge an attributed
file into the same bucket as a directly-packaged file without recording
provenance.

Preferred shape in downstream outputs:

```
package, confidence, count, ...
PHARMACY, direct, 33, ...
PHARMACY, high, 12, ...
PHARMACY, med, 8, ...
```

or: add a `provenance` column with values `{direct, prefix, range_empirical, range_canonical, unattributed}`.

---

## Rule 3 — Do not drop the 139 residuals

Files with no attribution must appear in a separate bucket — typically
`"(unattributed)"` — with their own row. They are 4.8% of the corpus and
may concentrate in specific namespaces (RC, OCX, GMR, XIP, ...). Dropping
them silently will distort every relative-volume comparison.

If a specific analysis cannot meaningfully include them, exclude them
explicitly with a filter expression in the report.

---

## Rule 4 — Long-tail is real; do not optimize only for the top 15

Top 15 packages hold ~58% of directly-packaged files. Phases that produce
per-package rankings, heatmaps, or network graphs must either:

- Show the long tail explicitly (e.g. histogram with log-scale x-axis), or
- State a threshold and summarize what was cut (e.g. "packages with <3
  files collapsed into 'other' (n=287 packages, 412 files)").

Avoid `head -15` semantics that silently truncate without noting the rest.

---

## Rule 5 — Prefer collapsed base type codes

Phase 1 emits both the compound-code distribution (legacy) and the
collapsed base-type distribution (via `vista_fm_browser.type_codes`).
Phases 4/5/7 should key off the **base code** for type-class comparisons
(is this a FREE TEXT field? a POINTER?) and only use compound strings when
diagnosing edge cases.

Use `decompose(raw_type).base` to extract the canonical base.

---

## Rule 6 — Field-count caveat (open)

As of iteration 1.5 there is an **open question** on `total_fields`:

- Old code: 69,328 (raw `^DD` numeric-subscript count, includes subfile refs)
- New code: 46,790 (count of parseable field-level 0-nodes)

The right denominator depends on whether sub-file structure nodes count as
"fields." Phase 2 (volume) must resolve this before using field-count as
an axis; until then, quote both numbers or defer field-count analysis.

---

## Change log

| Date | Change |
|------|--------|
| 2026-04-15 | Initial rule set (Tasks 4 + 5 of phase-1 planning guide) |
