"""
Phase 2 — Volume Survey (Analysis)
===================================
Goal: Find out where the actual data lives. Separate heavyweight clinical
files from small configuration files by entry count.

This is analysis-only. Visualization is handled by phase2-viz.py.

Prerequisite: phase1-scope.py (inventory is needed to resolve package/label
for each file — loaded internally if its outputs are absent).

Outputs (all in ~/data/vista-fm-browser/phase2/):
    file_volume.json           — [{"file_number", "label", "entry_count", "tier", "package"}]
    file_volume.csv            — same data flat
    summary.json               — tier counts + top-N files (used by viz + report)
    phase2-volume-report.md    — executive report

Run inside the VEHU container:
    python scripts/analysis/phase2-volume.py
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase2/").expanduser()

TIER_BOUNDS = [
    ("massive",  100_000, None),       # ≥ 100K
    ("large",     10_000, 100_000),    # 10K–100K
    ("medium",     1_000, 10_000),     # 1K–10K
    ("small",        100, 1_000),      # 100–1K
    ("tiny",           1, 100),        # 1–99
    ("empty",          0, 1),          # 0
]


def tier_for(count: int) -> str:
    for name, lo, hi in TIER_BOUNDS:
        if hi is None and count >= lo:
            return name
        if hi is not None and lo <= count < hi:
            return name
    return "empty"


def collect_volume(conn: YdbConnection) -> tuple[list[dict], FileInventory]:
    """Count entries for every file. Returns (rows, inventory)."""
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    fi = FileInventory(conn)
    fi.load()
    files = fi.list_files()

    console.print(
        f"\n[bold]Counting entries for {len(files)} files...[/bold] "
        "(this takes a few minutes)"
    )
    rows: list[dict] = []
    for fr in files:
        count = reader.count_entries(fr.file_number)
        rows.append({
            "file_number": fr.file_number,
            "label": fr.label,
            "entry_count": count,
            "tier": tier_for(count),
            "package": fr.package_name or "",
            "global_root": fr.global_root,
        })
    rows.sort(key=lambda r: -r["entry_count"])
    return rows, fi


def write_volume_json(rows: list[dict], path: Path) -> None:
    path.write_text(json.dumps(rows, indent=2, default=str))


def write_volume_csv(rows: list[dict], path: Path) -> None:
    fields = ["file_number", "label", "entry_count", "tier", "package", "global_root"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_summary(rows: list[dict]) -> dict:
    tier_counts: dict[str, int] = {name: 0 for name, _, _ in TIER_BOUNDS}
    for r in rows:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1

    with_data = sum(1 for r in rows if r["entry_count"] > 0)
    total_entries = sum(r["entry_count"] for r in rows)

    top50 = [
        {
            "file_number": r["file_number"],
            "label": r["label"],
            "entry_count": r["entry_count"],
            "tier": r["tier"],
            "package": r["package"],
        }
        for r in rows[:50]
    ]

    return {
        "total_files": len(rows),
        "files_with_data": with_data,
        "files_empty": len(rows) - with_data,
        "total_entries_all_files": total_entries,
        "tier_counts": tier_counts,
        "tier_bounds": {
            "massive":  ">= 100,000",
            "large":    "10,000 – 99,999",
            "medium":   "1,000 – 9,999",
            "small":    "100 – 999",
            "tiny":     "1 – 99",
            "empty":    "0",
        },
        "top_50_files": top50,
    }


def write_summary_json(summary: dict, path: Path) -> None:
    path.write_text(json.dumps(summary, indent=2, default=str))


def write_report(summary: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tc = summary["tier_counts"]

    lines: list[str] = []
    lines += [
        "# Phase 2 — Volume Survey",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Total files scanned:** {summary['total_files']:,}",
        f"- **Files with data:** {summary['files_with_data']:,} "
        f"({100 * summary['files_with_data'] / max(summary['total_files'], 1):.1f}%)",
        f"- **Empty files:** {summary['files_empty']:,}",
        f"- **Total entries across all files:** "
        f"{summary['total_entries_all_files']:,}",
        "",
        "## Volume Tiers",
        "",
        "| Tier | Range | Files |",
        "|:-----|:------|------:|",
    ]
    bounds = summary["tier_bounds"]
    for name in ["massive", "large", "medium", "small", "tiny", "empty"]:
        lines.append(f"| {name} | {bounds[name]} | {tc.get(name, 0):,} |")

    lines += [
        "",
        "## Top 25 Files by Entry Count",
        "",
        "| Rank | File # | Label | Entries | Tier | Package |",
        "|-----:|-------:|:------|--------:|:-----|:--------|",
    ]
    for i, r in enumerate(summary["top_50_files"][:25], 1):
        # .10g keeps decimals like 80.1 but avoids scientific notation for 9000010
        lines.append(
            f"| {i} | {r['file_number']:.10g} | {r['label']} | "
            f"{r['entry_count']:,} | {r['tier']} | {r['package'] or '—'} |"
        )

    lines += [
        "",
        "## Output Files",
        "",
        "- `file_volume.json` — full per-file volume data",
        "- `file_volume.csv` — same data flat",
        "- `summary.json` — tier counts and top-50 (consumed by report + viz)",
        "- `phase2_volume.png` — visualization (generated by phase2-viz.py)",
        "",
    ]
    path.write_text("\n".join(lines))


def render_tier_panel(summary: dict) -> None:
    console.print("\n[bold]Volume tiers:[/bold]")
    bounds = summary["tier_bounds"]
    for name in ["massive", "large", "medium", "small", "tiny", "empty"]:
        console.print(f"  {name:8s} ({bounds[name]:>18s}): {summary['tier_counts'].get(name, 0):,} files")
    console.print(f"\n[bold]Top 20 by entry count:[/bold]")
    for r in summary["top_50_files"][:20]:
        pkg = r["package"] or "?"
        console.print(
            f"  {r['file_number']:8.2f}  {r['label'][:40]:40s}  "
            f"{r['entry_count']:>12,}  [{pkg}]"
        )


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 2 — Volume Survey (Analysis)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        rows, _fi = collect_volume(conn)

    summary = build_summary(rows)
    render_tier_panel(summary)

    write_volume_json(rows, OUTPUT_DIR / "file_volume.json")
    write_volume_csv(rows, OUTPUT_DIR / "file_volume.csv")
    write_summary_json(summary, OUTPUT_DIR / "summary.json")
    write_report(summary, OUTPUT_DIR / "phase2-volume-report.md")

    console.print()
    for name in [
        "file_volume.json", "file_volume.csv", "summary.json",
        "phase2-volume-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 2 analysis complete")
    console.print(
        "\nNext: run [bold]phase2-viz.py[/bold] to generate PNG visualizations."
    )


if __name__ == "__main__":
    main()
