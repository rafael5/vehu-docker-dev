"""
Phase 6 — Data Coverage Analysis (Analysis)
============================================
Goal: Determine which defined fields are actually populated in the data
vs. defined-but-unused.

Default: samples File #2 (PATIENT) with 500 entries.
Use --file and --sample to override.

This is analysis-only. Visualization is handled by phase6-viz.py.

Outputs (all in ~/data/vista-fm-browser/phase6/):
    coverage_<file_num>.json     — per-field hit count + pct
    coverage_<file_num>.csv      — same data flat
    coverage_multi.csv           — with --multi, multi-file comparison
    summary.json                 — latest run stats (consumed by viz + report)
    phase6-coverage-report.md    — executive report

Run inside the VEHU container:
    python scripts/analysis/phase6-coverage.py
    python scripts/analysis/phase6-coverage.py --file 200 --sample 200
    python scripts/analysis/phase6-coverage.py --multi
"""

import argparse
import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase6/").expanduser()


def sample_coverage(conn: YdbConnection, file_num: float, sample: int) -> tuple[list[dict], int]:
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    fd = dd.get_file(file_num)
    if fd is None:
        console.print(f"[red]File {file_num} not found[/red]")
        return [], 0

    hits: dict[float, int] = defaultdict(int)
    n = 0
    for entry in reader.iter_entries(file_num, limit=sample):
        n += 1
        for field_num, val in entry.fields.items():
            if val.strip():
                hits[field_num] += 1

    rows: list[dict] = []
    for field_num in sorted(fd.fields.keys()):
        fld = fd.fields[field_num]
        count = hits.get(field_num, 0)
        pct = 100 * count / n if n else 0.0
        rows.append({
            "field": field_num, "label": fld.label,
            "type_code": fld.datatype_code, "type_name": fld.datatype_name,
            "hits": count, "pct": pct,
        })
    return rows, n


def multi_file_comparison(conn: YdbConnection, sample: int = 200) -> list[dict]:
    key_files = [(2, "PATIENT"), (200, "NEW PERSON"), (50, "DRUG"), (44, "HOSP LOC")]
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    rows: list[dict] = []
    for fnum, flabel in key_files:
        fd = dd.get_file(fnum)
        if not fd:
            continue
        hits: dict[float, int] = {}
        n = 0
        for entry in reader.iter_entries(fnum, limit=sample):
            n += 1
            for fn, val in entry.fields.items():
                if val.strip():
                    hits[fn] = hits.get(fn, 0) + 1
        for fn, fld in fd.fields.items():
            rows.append({
                "file": flabel, "file_number": fnum,
                "field_num": fn, "field": fld.label,
                "hits": hits.get(fn, 0), "n": n,
                "pct": (100 * hits.get(fn, 0) / n) if n else 0.0,
            })
    return rows


def build_summary(file_num: float, file_label: str, rows: list[dict], n: int) -> dict:
    if not rows or n == 0:
        return {"file_number": file_num, "file_label": file_label,
                "sample_size": n, "fields": []}
    full = sum(1 for r in rows if r["pct"] >= 80)
    some = sum(1 for r in rows if 20 <= r["pct"] < 80)
    sparse = sum(1 for r in rows if 0 < r["pct"] < 20)
    zero = sum(1 for r in rows if r["pct"] == 0)
    return {
        "file_number": file_num, "file_label": file_label,
        "sample_size": n, "total_fields": len(rows),
        "fields_full_80plus": full,
        "fields_partial_20_80": some,
        "fields_sparse_under_20": sparse,
        "fields_zero": zero,
        "fields": rows,
    }


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("")
        return
    cols = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def write_report(summary: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fn = summary.get("file_number", "?")
    fl = summary.get("file_label", "?")
    n = summary.get("sample_size", 0)
    if n == 0:
        path.write_text(f"# Phase 6 — No data sampled for File #{fn}\n")
        return

    lines = [
        f"# Phase 6 — Data Coverage: File #{fn:.10g} ({fl})",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Sample size:** {n:,} entries",
        f"- **Total fields:** {summary['total_fields']:,}",
        f"- **Well-populated (≥80%):** {summary['fields_full_80plus']}",
        f"- **Partially populated (20–80%):** {summary['fields_partial_20_80']}",
        f"- **Sparse (0–20%):** {summary['fields_sparse_under_20']}",
        f"- **Zero coverage:** {summary['fields_zero']}",
        "",
        "## Top 20 Best-Populated Fields",
        "",
        "| Field | Label | Type | Coverage |",
        "|------:|:------|:-----|---------:|",
    ]
    sorted_rows = sorted(summary["fields"], key=lambda r: -r["pct"])
    for r in sorted_rows[:20]:
        lines.append(f"| {r['field']:.4f} | {r['label']} | {r['type_name']} | {r['pct']:.1f}% |")

    lines += [
        "",
        "## Top 20 Zero-Coverage Fields (candidates for retirement)",
        "",
        "| Field | Label | Type |",
        "|------:|:------|:-----|",
    ]
    for r in [x for x in summary["fields"] if x["pct"] == 0][:20]:
        lines.append(f"| {r['field']:.4f} | {r['label']} | {r['type_name']} |")

    lines += [
        "",
        "## Output Files",
        "",
        f"- `coverage_{int(fn)}.json` / `.csv` — full per-field coverage",
        "- `summary.json` — stats (consumed by viz + report)",
        f"- `phase6_coverage_{int(fn)}.png` — bar chart (phase6-viz.py)",
        "",
    ]
    path.write_text("\n".join(lines))


def render_terminal(summary: dict) -> None:
    if summary.get("sample_size", 0) == 0:
        return
    console.print(
        f"\n[bold]Coverage for {summary['file_label']} "
        f"(n={summary['sample_size']}, {summary['total_fields']} fields):[/bold]"
    )
    console.print(
        f"  ≥80%: [green]{summary['fields_full_80plus']}[/green]  "
        f"20–80%: [yellow]{summary['fields_partial_20_80']}[/yellow]  "
        f"<20%: [red]{summary['fields_sparse_under_20']}[/red]  "
        f"zero: [dim]{summary['fields_zero']}[/dim]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 — Data Coverage Analysis")
    parser.add_argument("--file", type=float, default=2.0,
                        help="FileMan file number (default: 2 = PATIENT)")
    parser.add_argument("--sample", type=int, default=500,
                        help="Entries to sample (default: 500)")
    parser.add_argument("--multi", action="store_true",
                        help="Also run multi-file comparison (PATIENT, NEW PERSON, DRUG, HOSP LOC)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    console.rule(f"[bold blue]Phase 6 — Coverage (File #{args.file}, n={args.sample})")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        dd = DataDictionary(conn)
        fd = dd.get_file(args.file)
        fl = fd.label if fd else f"File #{args.file}"

        rows, n = sample_coverage(conn, args.file, args.sample)

        if args.multi:
            multi_rows = multi_file_comparison(conn)
            df = pd.DataFrame(multi_rows)
            df.to_csv(OUTPUT_DIR / "coverage_multi.csv", index=False)
            console.print(f"  [green]wrote[/green] {OUTPUT_DIR / 'coverage_multi.csv'}")

    summary = build_summary(args.file, fl, rows, n)
    render_terminal(summary)

    tag = f"{int(args.file)}" if args.file == int(args.file) else f"{args.file:.4g}"
    (OUTPUT_DIR / f"coverage_{tag}.json").write_text(json.dumps(rows, indent=2, default=str))
    write_csv(rows, OUTPUT_DIR / f"coverage_{tag}.csv")
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(summary, OUTPUT_DIR / "phase6-coverage-report.md")

    console.print()
    for name in [
        f"coverage_{tag}.json", f"coverage_{tag}.csv",
        "summary.json", "phase6-coverage-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 6 analysis complete")
    console.print("\nNext: run [bold]phase6-viz.py[/bold] to generate PNG visualizations.")


if __name__ == "__main__":
    main()
