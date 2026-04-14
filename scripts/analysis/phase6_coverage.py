"""
Phase 6 — Data Coverage Analysis
=================================
Goal: Determine which defined fields are actually populated in the data
vs. defined-but-unused.

By default samples File #2 (PATIENT) with 500 entries.
Use --file and --sample to override.

Outputs:
    ~/data/vista-fm-browser/output/phase6_coverage_<file_num>.png
    ~/data/vista-fm-browser/output/phase6_coverage_multi.csv

Run inside the VEHU container:
    python scripts/analysis/phase6_coverage.py
    python scripts/analysis/phase6_coverage.py --file 200 --sample 200
"""

import argparse
import logging
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()


def coverage_for_file(
    conn: YdbConnection, file_num: float, sample: int = 500
) -> tuple[dict, int]:
    """
    Sample `sample` entries from file_num and count field hits.
    Returns (field_hits dict, actual count sampled).
    """
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)

    field_hits: dict[float, int] = defaultdict(int)
    count = 0
    for entry in reader.iter_entries(file_num, limit=sample):
        count += 1
        for field_num, val in entry.fields.items():
            if val.strip():
                field_hits[field_num] += 1

    return field_hits, count


def print_coverage_table(
    conn: YdbConnection, file_num: float, field_hits: dict, count: int
) -> None:
    dd = DataDictionary(conn)
    fd = dd.get_file(file_num)
    if fd is None:
        console.print(f"[red]File {file_num} not found[/red]")
        return

    console.print(f"\n[bold]Coverage for {fd.label} (n={count}):[/bold]")
    console.print(f"{'Field':8s}  {'Label':30s}  {'%Pop':>6s}  {'Type':15s}")
    console.print("-" * 65)
    for field_num in sorted(fd.fields.keys()):
        fld = fd.fields[field_num]
        hits = field_hits.get(field_num, 0)
        pct = 100 * hits / count if count else 0
        bar = "▓" * int(pct / 10)
        console.print(
            f"  {field_num:6.4f}  {fld.label:30s}  {pct:5.1f}%  "
            f"{fld.datatype_name:15s}  {bar}"
        )


def visualize_coverage(
    conn: YdbConnection, file_num: float, field_hits: dict, count: int
) -> None:
    dd = DataDictionary(conn)
    fd = dd.get_file(file_num)
    if fd is None:
        return

    def cov_color(pct: float) -> str:
        if pct >= 80:
            return "#2ca02c"
        if pct >= 20:
            return "#ff7f0e"
        return "#d62728"

    rows_cov = []
    for field_num in sorted(fd.fields.keys()):
        fld = fd.fields[field_num]
        hits = field_hits.get(field_num, 0)
        pct = 100 * hits / count if count else 0
        rows_cov.append((pct, field_num, fld.label, fld.datatype_name))

    rows_cov.sort(key=lambda x: x[0])

    labels_cov = [
        f"{num:.4f} {lbl[:28]} ({dtype[:3]})" for _, num, lbl, dtype in rows_cov
    ]
    pcts = [p for p, *_ in rows_cov]
    bar_colors = [cov_color(p) for p in pcts]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, max(8, len(labels_cov) * 0.22)))
    ax.barh(labels_cov, pcts, color=bar_colors)
    ax.set_xlim(0, 105)
    ax.set_xlabel("% of sampled entries where field is populated")
    ax.set_title(
        f"Field Coverage — {fd.label} (File #{file_num})\n"
        f"n={count} sampled entries  |  "
        "Green ≥80%, Orange 20–80%, Red <20%"
    )
    ax.tick_params(axis="y", labelsize=7)
    ax.axvline(x=80, color="green", linestyle="--", alpha=0.4, linewidth=0.8)
    ax.axvline(x=20, color="orange", linestyle="--", alpha=0.4, linewidth=0.8)
    plt.tight_layout()
    out_path = OUTPUT_DIR / f"phase6_coverage_{int(file_num)}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Coverage chart saved to [green]{out_path}[/green]")


def multi_file_comparison(conn: YdbConnection) -> None:
    """Compare coverage for PATIENT, NEW PERSON, DRUG, HOSPITAL LOCATION."""
    key_files = [
        (2, "PATIENT"),
        (200, "NEW PERSON"),
        (50, "DRUG"),
        (44, "HOSP LOC"),
    ]
    summary_rows = []
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)

    for fnum, flabel in key_files:
        fd = dd.get_file(fnum)
        if not fd:
            continue
        hits2: dict[float, int] = {}
        n2 = 0
        for entry in reader.iter_entries(fnum, limit=200):
            n2 += 1
            for fn, val in entry.fields.items():
                if val.strip():
                    hits2[fn] = hits2.get(fn, 0) + 1
        for fn, fld in fd.fields.items():
            pct = 100 * hits2.get(fn, 0) / n2 if n2 else 0
            summary_rows.append(
                {
                    "file": flabel,
                    "field": fld.label,
                    "field_num": fn,
                    "pct": pct,
                }
            )

    df_cov = pd.DataFrame(summary_rows)
    primary_field = df_cov[df_cov["field_num"] == 0.01]
    if not primary_field.empty:
        console.print("\n[bold].01 NAME field coverage by file:[/bold]")
        console.print(primary_field[["file", "pct"]].to_string(index=False))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "phase6_coverage_multi.csv"
    df_cov.to_csv(out, index=False)
    console.print(f"Multi-file coverage CSV saved to [green]{out}[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 — Data Coverage Analysis")
    parser.add_argument(
        "--file",
        type=float,
        default=2.0,
        help="FileMan file number to analyse (default: 2 = PATIENT)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=500,
        help="Number of entries to sample (default: 500)",
    )
    parser.add_argument(
        "--multi",
        action="store_true",
        help="Also run multi-file comparison (PATIENT, NEW PERSON, DRUG, HOSP LOC)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    console.rule(
        f"[bold blue]Phase 6 — Data Coverage Analysis (File #{args.file}, n={args.sample})"
    )

    with YdbConnection.connect() as conn:
        field_hits, count = coverage_for_file(conn, args.file, args.sample)
        print_coverage_table(conn, args.file, field_hits, count)
        visualize_coverage(conn, args.file, field_hits, count)

        if args.multi:
            multi_file_comparison(conn)

    console.rule("[bold green]Phase 6 complete")


if __name__ == "__main__":
    main()
