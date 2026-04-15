"""
Phase 2 — Volume Survey (Analysis)
===================================
Goal: Find out where the actual data lives. Separate heavyweight clinical
files from small configuration files by entry count.

This is analysis-only. Visualization is handled by phase2-viz.py.

Prerequisite: phase1-scope.py (inventory is needed to resolve package/label
for each file — loaded internally if its outputs are absent).

Outputs (all in <repo>/output/phase2/):
    file_volume.json           — per-file volume rows with attribution provenance
    file_volume.csv            — same data flat
    summary.json               — tier counts, top files, per-package totals
    phase2-volume-report.md    — executive report

Per `output/phase1/DOWNSTREAM-RULES.md`:
    - Uses 2,915 as the denominator.
    - Merges phase-1.5 attribution so every file carries a package name
      with provenance (direct / prefix / range_empirical / range_canonical /
      unattributed) and confidence.
    - The 139 unattributable files appear under `"(unattributed)"` as their
      own bucket — never silently dropped.

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

# Per project convention, phase outputs live inside the repo.
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "output" / "phase2"
PHASE1_5_ATTRIB = REPO_ROOT / "output" / "phase1_5" / "attribution_candidates.csv"

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


UNATTRIBUTED = "(unattributed)"


def load_phase1_5_attribution() -> dict[float, tuple[str, str, str]]:
    """Load the phase-1.5 attribution map.

    Returns {file_number: (package_name, method, confidence)}. Missing file
    or empty candidate rows are treated as unattributed. Silent if the
    phase-1.5 file is absent — phase 2 still runs, but rows will all be
    marked provenance="direct" or "unattributed".
    """
    attrib: dict[float, tuple[str, str, str]] = {}
    if not PHASE1_5_ATTRIB.exists():
        log.warning("Phase-1.5 attribution not found: %s", PHASE1_5_ATTRIB)
        return attrib
    with PHASE1_5_ATTRIB.open() as f:
        for row in csv.DictReader(f):
            if not row.get("candidate_package"):
                continue
            try:
                fn = float(row["file_number"])
            except (TypeError, ValueError):
                continue
            attrib[fn] = (
                row["candidate_package"],
                row.get("method", ""),
                row.get("confidence", ""),
            )
    return attrib


def collect_volume(conn: YdbConnection) -> tuple[list[dict], FileInventory]:
    """Count entries for every file and merge attribution metadata."""
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    fi = FileInventory(conn)
    fi.load()
    files = fi.list_files()
    phase1_5 = load_phase1_5_attribution()

    console.print(
        f"\n[bold]Counting entries for {len(files)} files...[/bold] "
        "(this takes a few minutes)"
    )
    rows: list[dict] = []
    for fr in files:
        count = reader.count_entries(fr.file_number)
        # Attribution: direct from phase 1, else phase-1.5, else unattributed.
        if fr.package_name:
            pkg = fr.package_name
            provenance = "direct"
            confidence = "high"
        else:
            attr = phase1_5.get(fr.file_number)
            if attr is None:
                pkg = UNATTRIBUTED
                provenance = "unattributed"
                confidence = ""
            else:
                pkg, provenance, confidence = attr
        rows.append({
            "file_number": fr.file_number,
            "label": fr.label,
            "entry_count": count,
            "tier": tier_for(count),
            "package": pkg,
            "package_provenance": provenance,
            "package_confidence": confidence,
            "global_root": fr.global_root,
        })
    rows.sort(key=lambda r: -r["entry_count"])
    return rows, fi


def write_volume_json(rows: list[dict], path: Path) -> None:
    path.write_text(json.dumps(rows, indent=2, default=str))


def write_volume_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "file_number", "label", "entry_count", "tier",
        "package", "package_provenance", "package_confidence",
        "global_root",
    ]
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
            "package_provenance": r["package_provenance"],
            "package_confidence": r["package_confidence"],
        }
        for r in rows[:50]
    ]

    # Per-package totals with provenance breakdown.
    pkg_entries: dict[str, int] = {}
    pkg_files: dict[str, int] = {}
    pkg_provenance_counts: dict[str, dict[str, int]] = {}
    for r in rows:
        p = r["package"]
        pkg_entries[p] = pkg_entries.get(p, 0) + r["entry_count"]
        pkg_files[p] = pkg_files.get(p, 0) + 1
        pkg_provenance_counts.setdefault(p, {})
        prov = r["package_provenance"] or "direct"
        pkg_provenance_counts[p][prov] = pkg_provenance_counts[p].get(prov, 0) + 1

    top_pkg_by_entries = sorted(
        [
            {
                "package": p,
                "entry_total": pkg_entries[p],
                "file_count": pkg_files[p],
                "provenance": pkg_provenance_counts[p],
            }
            for p in pkg_entries
        ],
        key=lambda x: -x["entry_total"],
    )[:30]

    # Provenance roll-up for the whole corpus.
    provenance_totals: dict[str, int] = {}
    for r in rows:
        key = r["package_provenance"] or "direct"
        provenance_totals[key] = provenance_totals.get(key, 0) + 1

    # Unattributed-bucket detail (per DOWNSTREAM-RULES rule 3).
    unattr_rows = [r for r in rows if r["package"] == UNATTRIBUTED]
    unattr_summary = {
        "file_count": len(unattr_rows),
        "entry_total": sum(r["entry_count"] for r in unattr_rows),
        "top_10_by_entries": [
            {
                "file_number": r["file_number"],
                "label": r["label"],
                "entry_count": r["entry_count"],
                "global_root": r["global_root"],
            }
            for r in sorted(unattr_rows, key=lambda x: -x["entry_count"])[:10]
        ],
    }

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
        "provenance_totals": provenance_totals,
        "top_50_files": top50,
        "top_packages_by_entries": top_pkg_by_entries,
        "unattributed_bucket": unattr_summary,
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

    # Provenance roll-up (DOWNSTREAM-RULES rule 2).
    prov = summary.get("provenance_totals") or {}
    if prov:
        lines += [
            "",
            "## Attribution Provenance (DOWNSTREAM-RULES rule 2)",
            "",
            "| Provenance | File count |",
            "|:-----------|-----------:|",
        ]
        for key in ["direct", "prefix", "range_empirical",
                    "range_canonical", "unattributed"]:
            if key in prov:
                lines.append(f"| {key} | {prov[key]:,} |")

    lines += [
        "",
        "## Top 25 Files by Entry Count",
        "",
        "| Rank | File # | Label | Entries | Tier | Package | Provenance | Confidence |",
        "|-----:|-------:|:------|--------:|:-----|:--------|:-----------|:-----------|",
    ]
    for i, r in enumerate(summary["top_50_files"][:25], 1):
        # .10g keeps decimals like 80.1 but avoids scientific notation for 9000010
        lines.append(
            f"| {i} | {r['file_number']:.10g} | {r['label']} | "
            f"{r['entry_count']:,} | {r['tier']} | {r['package'] or '—'} | "
            f"{r.get('package_provenance') or '—'} | "
            f"{r.get('package_confidence') or '—'} |"
        )

    # Top packages by total entries.
    top_pkg = summary.get("top_packages_by_entries") or []
    if top_pkg:
        lines += [
            "",
            "## Top 15 Packages by Total Entries",
            "",
            "| Rank | Package | Total Entries | Files | Provenance mix |",
            "|-----:|:--------|--------------:|------:|:---------------|",
        ]
        for i, p in enumerate(top_pkg[:15], 1):
            prov_mix = ", ".join(f"{k}={v}" for k, v in p["provenance"].items())
            lines.append(
                f"| {i} | {p['package']} | {p['entry_total']:,} | "
                f"{p['file_count']} | {prov_mix} |"
            )

    # Residual (unattributed) bucket — rule 3.
    unattr = summary.get("unattributed_bucket") or {}
    if unattr.get("file_count"):
        lines += [
            "",
            "## Unattributed bucket (DOWNSTREAM-RULES rule 3)",
            "",
            f"- **Files:** {unattr['file_count']:,}",
            f"- **Total entries:** {unattr['entry_total']:,}",
            "",
            "Top 10 unattributed by volume:",
            "",
            "| File # | Label | Entries | Global |",
            "|-------:|:------|--------:|:-------|",
        ]
        for r in unattr["top_10_by_entries"]:
            lines.append(
                f"| {r['file_number']:.10g} | {r['label']} | "
                f"{r['entry_count']:,} | `{r['global_root']}` |"
            )

    lines += [
        "",
        "## Output Files",
        "",
        "- `file_volume.json` — full per-file volume data (with provenance)",
        "- `file_volume.csv` — same data flat",
        "- `summary.json` — tier counts, top files, per-package totals, provenance",
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
