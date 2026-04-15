"""
Phase 1.5 — Package Attribution for Unpackaged Files
====================================================
Goal: close the gap left by phase 1 — attribute the ~58% of files that have
no owning package via three heuristics, in priority order:

    C)  Namespace-prefix match against known package prefixes
    A1) Empirical file-number range per package (from attributed files)
    A2) Canonical VistA number-range fallback (well-known ranges only)

Inputs:
    output/phase1/inventory.json  (produced by phase1-scope.py)

Outputs (into output/phase1_5/):
    attribution_candidates.csv
    attribution_summary.json
    phase1_5-attribution-report.md

No YottaDB connection required — operates entirely on the phase-1 inventory.
Safe to run on host without the container.
"""

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Make the src/ importable when run directly from project root.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from vista_fm_browser.attribution import (  # noqa: E402
    attribute_all,
    build_empirical_ranges,
)

INVENTORY = REPO / "output" / "phase1" / "inventory.json"
OUTPUT_DIR = REPO / "output" / "phase1_5"


def load_inventory() -> dict:
    if not INVENTORY.exists():
        raise SystemExit(
            f"Phase-1 inventory not found: {INVENTORY}\n"
            "Run phase1-scope.py first (in the VEHU container)."
        )
    return json.loads(INVENTORY.read_text())


def write_candidates_csv(attributions: list, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "file_number", "label", "global_root",
            "candidate_package", "candidate_prefix",
            "method", "confidence", "notes",
        ])
        for a in attributions:
            w.writerow([
                a.file_number, a.label, a.global_root,
                a.candidate_package or "", a.candidate_prefix or "",
                a.method, a.confidence, a.notes,
            ])


def write_report(summary: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_method = summary["by_method"]
    by_conf = summary["by_confidence"]
    top_pkg = summary["top_attributed_packages"]

    lines = [
        "# Phase 1.5 — Package Attribution Report",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- Input files analyzed: **{summary['input_total']:,}** (phase-1 unpackaged)",
        f"- Attributed: **{summary['attributed']:,}** "
        f"({summary['attributed_pct']:.1f}%)",
        f"- Still unattributed: **{summary['unattributed']:,}**",
        "",
        "## Attribution by method",
        "",
        "| Method | Count |",
        "|:-------|------:|",
    ]
    for method, count in by_method.items():
        lines.append(f"| {method or '(none)'} | {count:,} |")

    lines += [
        "",
        "## Attribution by confidence",
        "",
        "| Confidence | Count |",
        "|:-----------|------:|",
    ]
    for conf, count in by_conf.items():
        lines.append(f"| {conf or '(none)'} | {count:,} |")

    lines += [
        "",
        "## Top 20 newly-attributed packages",
        "",
        "| Rank | Package | New files |",
        "|-----:|:--------|----------:|",
    ]
    for i, (pkg, count) in enumerate(top_pkg, 1):
        lines.append(f"| {i} | {pkg} | {count:,} |")

    lines += [
        "",
        "## Method priority",
        "",
        "1. **prefix** — global-root namespace matches a package prefix "
        "(longest wins). `high` confidence on exact match, `med` on "
        "longer-namespace longest-prefix.",
        "2. **range_empirical** — file number falls inside exactly one "
        "package's observed min/max range from phase 1. `med` if ≥3 anchors, "
        "else `low`.",
        "3. **range_canonical** — file number falls in a curated VistA "
        "canonical range table (PHARMACY 50–59.999, LAB 60–69.999, etc.). "
        "Always `low`.",
        "",
        "## Known limitations",
        "",
        "- The canonical range table is conservative — only well-documented "
        "VA ranges are encoded. Unattributed files in unusual ranges stay "
        "unattributed.",
        "- Range-empirical treats overlapping ranges as ambiguous and skips.",
        "- FileMan-internal files (`^DD`, `^DIC(.2,` etc.) attribute to "
        "VA FILEMAN / KERNEL via prefix and canonical rules.",
        "",
        "## Output files",
        "",
        "- `attribution_candidates.csv` — one row per analyzed file",
        "- `attribution_summary.json` — structured summary for downstream phases",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    inv = load_inventory()
    all_files = inv["files"]
    packages = inv["packages"]

    # Build the prefix lookup from all packages (name, prefix).
    package_prefixes = [
        (p["prefix"], p["name"]) for p in packages if p.get("prefix")
    ]

    # Empirical ranges computed from already-attributed files only.
    attributed_files = [f for f in all_files if f.get("package_name")]
    unpackaged_files = [f for f in all_files if not f.get("package_name")]
    ranges = build_empirical_ranges(attributed_files)

    attributions = attribute_all(unpackaged_files, package_prefixes, ranges)

    # Summary stats
    by_method: Counter[str] = Counter(a.method for a in attributions)
    by_conf: Counter[str] = Counter(a.confidence for a in attributions)
    attributed = sum(1 for a in attributions if a.candidate_package)
    pkg_count: Counter[str] = Counter(
        a.candidate_package for a in attributions if a.candidate_package
    )
    top_pkg = pkg_count.most_common(20)

    summary = {
        "input_total": len(unpackaged_files),
        "attributed": attributed,
        "unattributed": len(unpackaged_files) - attributed,
        "attributed_pct": (
            100.0 * attributed / len(unpackaged_files)
            if unpackaged_files else 0.0
        ),
        "by_method": dict(by_method),
        "by_confidence": dict(by_conf),
        "top_attributed_packages": top_pkg,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_candidates_csv(attributions, OUTPUT_DIR / "attribution_candidates.csv")
    (OUTPUT_DIR / "attribution_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    write_report(summary, OUTPUT_DIR / "phase1_5-attribution-report.md")

    print(f"Analyzed {len(unpackaged_files):,} unpackaged files")
    print(f"Attributed: {attributed:,} ({summary['attributed_pct']:.1f}%)")
    print(f"By method: {dict(by_method)}")
    print(f"By confidence: {dict(by_conf)}")
    print(f"\nOutputs written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
