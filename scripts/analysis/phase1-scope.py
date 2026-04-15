"""
Phase 1 — Scope Survey (Analysis)
==================================
Goal: Know the total size of the problem in five numbers before touching any field.

This script is analysis-only. It reads live VEHU data and writes structured
data files + an executive report. Visualization is a separate concern handled
by phase1-viz.py which consumes these data files.

Outputs (all in ~/data/vista-fm-browser/phase1/):
    inventory.json          — full inventory (files + packages, nested)
    summary.json            — scope stats (compact, used by viz + report)
    files.csv               — flat file list (one row per file)
    packages.csv            — flat package list with file counts
    type_distribution.csv   — field datatype counts across all files
    phase1-scope-report.md        — executive report with summary statistics

Run inside the VEHU container:
    python scripts/analysis/phase1-scope.py

Requires: source /etc/bashrc (YottaDB environment active, ydb_gbldir set to VEHU).
"""

import collections
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase1/").expanduser()


# ---------------------------------------------------------------------------
# Data-collection sections
# ---------------------------------------------------------------------------


def inspect_file_registry(conn: YdbConnection) -> dict:
    """Inspect File #1 — the FileMan file registry itself."""
    dd = DataDictionary(conn)
    fd1 = dd.get_file(1)
    if fd1 is None:
        console.print("[red]File #1 not found[/red]")
        return {"file_1_label": None, "file_1_fields": 0, "file_1_entries": 0}
    reader = FileReader(conn, dd)
    entries = reader.count_entries(1)
    console.print(
        f"\n[bold]File #1:[/bold] {fd1.label}  global=^DIC  "
        f"fields={fd1.field_count}  entries={entries}"
    )
    return {
        "file_1_label": fd1.label,
        "file_1_fields": fd1.field_count,
        "file_1_entries": entries,
    }


def collect_type_distribution(
    conn: YdbConnection,
) -> tuple[dict[str, int], dict[str, str], int]:
    """Walk ^DD and count field datatypes. Returns (counts, names, total_fields)."""
    dd = DataDictionary(conn)
    type_counts: dict[str, int] = collections.Counter()
    type_names: dict[str, str] = {}
    total_fields = 0
    for file_num, _label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        total_fields += fd.field_count
        for fld in fd.fields.values():
            type_counts[fld.datatype_code] += 1
            type_names.setdefault(fld.datatype_code, fld.datatype_name)
    return dict(type_counts), type_names, total_fields


# ---------------------------------------------------------------------------
# Data-file writers
# ---------------------------------------------------------------------------


def write_files_csv(fi: FileInventory, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["file_number", "label", "global_root", "field_count",
             "package_name", "package_prefix"]
        )
        for fr in fi.list_files():
            w.writerow([
                fr.file_number, fr.label, fr.global_root, fr.field_count,
                fr.package_name or "", fr.package_prefix or "",
            ])


def write_packages_csv(fi: FileInventory, path: Path) -> None:
    grouped = fi.files_by_package()
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["package_name", "prefix", "version", "file_count"])
        for pkg in fi.list_packages():
            w.writerow([
                pkg.name, pkg.prefix, pkg.version,
                len(grouped.get(pkg.name, [])),
            ])


def write_type_distribution_csv(
    counts: dict[str, int], names: dict[str, str], path: Path
) -> None:
    total = sum(counts.values()) or 1
    rows = sorted(counts.items(), key=lambda x: -x[1])
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datatype_code", "datatype_name", "count", "percent"])
        for code, count in rows:
            w.writerow([code, names.get(code, ""), count, f"{100 * count / total:.2f}"])


def write_summary_json(summary: dict, path: Path) -> None:
    path.write_text(json.dumps(summary, indent=2, default=str))


# ---------------------------------------------------------------------------
# Executive report
# ---------------------------------------------------------------------------


def write_report(summary: dict, path: Path) -> None:
    """Write phase1-scope-report.md — a compact executive report."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    top = summary["top_packages_by_file_count"][:15]
    types = summary["type_distribution"][:10]
    total_types = sum(t["count"] for t in summary["type_distribution"]) or 1

    lines: list[str] = []
    lines += [
        "# Phase 1 — Scope Survey",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Total FileMan files:** {summary['total_files']:,}",
        f"- **Total packages:** {summary['total_packages']:,}",
        f"- **Files with owning package:** "
        f"{summary['total_files'] - summary['unpackaged_files']:,} "
        f"({100 * (summary['total_files'] - summary['unpackaged_files']) / max(summary['total_files'], 1):.1f}%)",
        f"- **Unpackaged files:** {summary['unpackaged_files']:,}",
        f"- **Total fields across all files:** {summary['total_fields']:,}",
        f"- **Average fields per file:** {summary['avg_fields_per_file']:.1f}",
        "",
        "## File #1 — FileMan File Registry",
        "",
        f"- Label: `{summary['file_1']['file_1_label']}`",
        f"- Field count: {summary['file_1']['file_1_fields']}",
        f"- Entries (registered files): {summary['file_1']['file_1_entries']:,}",
        "",
        "## Top 15 Packages by File Count",
        "",
        "| Rank | Package | Files |",
        "|-----:|:--------|------:|",
    ]
    for i, row in enumerate(top, 1):
        lines.append(f"| {i} | {row['name']} | {row['file_count']:,} |")

    lines += [
        "",
        "## Field Type Distribution (top 10)",
        "",
        "| Code | Type | Count | % |",
        "|:----:|:-----|------:|--:|",
    ]
    for row in types:
        pct = 100 * row["count"] / total_types
        lines.append(
            f"| {row['code']} | {row['name']} | {row['count']:,} | {pct:.1f}% |"
        )

    lines += [
        "",
        "## Output Files",
        "",
        "- `inventory.json` — full nested inventory",
        "- `summary.json` — key stats (consumed by report + viz)",
        "- `files.csv` — flat file list",
        "- `packages.csv` — package list with file counts",
        "- `type_distribution.csv` — datatype frequency",
        "- `phase1_scope.png` — visualization (generated by phase1-viz.py)",
        "",
    ]
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Terminal display helpers
# ---------------------------------------------------------------------------


def render_type_table(counts: dict[str, int], names: dict[str, str]) -> None:
    t = Table(title="Field Type Distribution")
    t.add_column("Code", style="cyan", justify="center")
    t.add_column("Name", style="white")
    t.add_column("Count", style="yellow", justify="right")
    t.add_column("%", style="green", justify="right")
    total = sum(counts.values()) or 1
    for code, count in sorted(counts.items(), key=lambda x: -x[1]):
        t.add_row(code, names.get(code, ""), f"{count:,}", f"{100 * count / total:.1f}%")
    console.print(t)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 1 — Scope Survey (Analysis)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        file_1_info = inspect_file_registry(conn)

        fi = FileInventory(conn)
        fi.load()
        inv_summary = fi.summary()

        type_counts, type_names, total_fields = collect_type_distribution(conn)
        render_type_table(type_counts, type_names)

    # Combined summary used by report + viz
    summary = {
        "total_files": inv_summary["total_files"],
        "total_packages": inv_summary["total_packages"],
        "unpackaged_files": inv_summary["unpackaged_files"],
        "total_fields": total_fields,
        "avg_fields_per_file": total_fields / max(inv_summary["total_files"], 1),
        "file_1": file_1_info,
        "top_packages_by_file_count": inv_summary["top_packages_by_file_count"],
        # Top 30 only in summary; full distribution is in type_distribution.csv
        "type_distribution": [
            {"code": c, "name": type_names.get(c, ""), "count": n}
            for c, n in sorted(type_counts.items(), key=lambda x: -x[1])[:30]
        ],
    }

    # Data files
    fi.export_json(OUTPUT_DIR)  # inventory.json
    write_summary_json(summary, OUTPUT_DIR / "summary.json")
    write_files_csv(fi, OUTPUT_DIR / "files.csv")
    write_packages_csv(fi, OUTPUT_DIR / "packages.csv")
    write_type_distribution_csv(type_counts, type_names, OUTPUT_DIR / "type_distribution.csv")

    # Executive report
    write_report(summary, OUTPUT_DIR / "phase1-scope-report.md")

    console.print()
    for name in [
        "inventory.json", "summary.json", "files.csv", "packages.csv",
        "type_distribution.csv", "phase1-scope-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 1 analysis complete")
    console.print(
        "\nNext: run [bold]phase1-viz.py[/bold] to generate PNG visualizations."
    )


if __name__ == "__main__":
    main()
