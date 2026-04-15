"""
Phase 8 — Normalization Rollup (Analysis)
===========================================
Goal: Aggregate all prior-phase outputs into a single combined report.
No new data collection — this phase purely consumes phase1–7 outputs.

This is analysis-only. Visualization is handled by phase8-viz.py.

Prerequisites (run all prior phases first):
    phase1-scope.py       → phase1/inventory.json, summary.json
    phase2-volume.py      → phase2/file_volume.json
    phase3-topology.py    → phase3/all_fields.json, summary.json
    phase4-variety.py     → phase4/summary.json
    phase7-candidates.py  → phase7/normalization_candidates.json

Outputs (all in ~/data/vista-fm-browser/phase8/):
    normalization_report.json  — combined rollup of all phase stats
    summary.json               — same data, consumed by viz
    phase8-rollup-report.md    — executive rollup report

Run (no DB needed):
    python scripts/analysis/phase8-rollup.py
"""

import collections
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

log = logging.getLogger(__name__)
console = Console()

DATA_ROOT = Path("~/data/vista-fm-browser/").expanduser()
OUTPUT_DIR = DATA_ROOT / "phase8"


def load(path: Path) -> dict | list | None:
    if path.exists():
        return json.loads(path.read_text())
    console.print(f"[yellow]Missing: {path.relative_to(DATA_ROOT)}[/yellow]  "
                  "(run the corresponding phase first)")
    return None


def build_rollup() -> dict:
    phase1 = load(DATA_ROOT / "phase1/summary.json") or {}
    phase2 = load(DATA_ROOT / "phase2/summary.json") or {}
    phase3 = load(DATA_ROOT / "phase3/summary.json") or {}
    phase4 = load(DATA_ROOT / "phase4/summary.json") or {}
    phase7 = load(DATA_ROOT / "phase7/summary.json") or {}
    candidates = load(DATA_ROOT / "phase7/normalization_candidates.json") or []

    # Fall back to reading all_fields.json for type distribution if phase1 didn't capture
    schema = load(DATA_ROOT / "phase3/all_fields.json") or []
    type_counts = collections.Counter(r["datatype_code"] for r in schema)

    rollup = {
        "scope": {
            "total_files": phase1.get("total_files", 0),
            "total_packages": phase1.get("total_packages", 0),
            "total_fields": phase1.get("total_fields", len(schema)),
            "unpackaged_files": phase1.get("unpackaged_files", 0),
            "avg_fields_per_file": phase1.get("avg_fields_per_file", 0),
            "files_with_data": phase2.get("files_with_data", 0),
            "files_empty": phase2.get("files_empty", 0),
            "total_entries": phase2.get("total_entries_all_files", 0),
        },
        "volume": {
            "tier_counts": phase2.get("tier_counts", {}),
            "top_5_files": phase2.get("top_50_files", [])[:5],
        },
        "type_distribution": {
            "from_phase1": phase1.get("type_distribution", [])[:15],
            "top_codes": dict(type_counts.most_common(15)) if type_counts else {},
        },
        "topology": {
            "total_pointer_edges": phase3.get("total_pointer_edges", 0),
            "hub_files_10plus": phase3.get("hub_files_10plus", 0),
            "variable_pointer_fields": phase3.get("variable_pointer_fields", 0),
            "multiple_fields": phase3.get("multiple_fields", 0),
            "top_hubs": phase3.get("top_hubs", [])[:10],
        },
        "variety": {
            "unique_labels": phase4.get("unique_labels", 0),
            "set_fields_with_values": phase4.get("set_fields_with_values", 0),
            "shared_sets_count": phase4.get("shared_sets_count", 0),
            "label_type_inconsistencies": phase4.get("label_type_inconsistencies", 0),
        },
        "normalization": {
            "total_candidates": phase7.get("total_candidates", len(candidates)),
            "by_rule": phase7.get("by_rule", {}),
            "priority_max": phase7.get("priority_max", 0),
            "priority_median": phase7.get("priority_median", 0),
            "top_25_candidates": phase7.get("top_25", candidates[:25]),
        },
    }
    return rollup


def write_report(rollup: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    s = rollup["scope"]
    v = rollup["volume"]
    t = rollup["topology"]
    va = rollup["variety"]
    n = rollup["normalization"]

    lines = [
        "# Phase 8 — Normalization Rollup",
        "",
        f"_Generated {ts}_",
        "",
        "_Combined summary of phases 1–7. See each phase's own report for details._",
        "",
        "## Scope (Phase 1)",
        "",
        f"- **Files:** {s['total_files']:,}  /  **Packages:** {s['total_packages']:,}  /  **Fields:** {s['total_fields']:,}",
        f"- **Files with data:** {s['files_with_data']:,}  /  **Empty:** {s['files_empty']:,}  /  **Total entries:** {s['total_entries']:,}",
        "",
        "## Volume Tiers (Phase 2)",
        "",
        "| Tier | Count |",
        "|:-----|------:|",
    ]
    for tier in ["massive", "large", "medium", "small", "tiny", "empty"]:
        lines.append(f"| {tier} | {v['tier_counts'].get(tier, 0):,} |")

    lines += [
        "",
        "## Topology (Phase 3)",
        "",
        f"- **Pointer edges:** {t['total_pointer_edges']:,}",
        f"- **Hub files (≥10 inbound):** {t['hub_files_10plus']:,}",
        f"- **Variable-pointer fields:** {t['variable_pointer_fields']:,}",
        f"- **MULTIPLE (sub-file) fields:** {t['multiple_fields']:,}",
        "",
        "### Top 10 Hubs",
        "",
        "| File # | Label | Inbound |",
        "|-------:|:------|--------:|",
    ]
    for h in t["top_hubs"]:
        lines.append(f"| {h.get('file_number', '?'):.10g} | {h.get('label', '?')} | {h.get('inbound_count', 0)} |")

    lines += [
        "",
        "## Variety (Phase 4)",
        "",
        f"- **Unique labels:** {va['unique_labels']:,}",
        f"- **SET fields with values:** {va['set_fields_with_values']:,}",
        f"- **Shared value sets (≥5 fields):** {va['shared_sets_count']:,}",
        f"- **Label-type inconsistencies:** {va['label_type_inconsistencies']:,}",
        "",
        "## Normalization Candidates (Phase 7)",
        "",
        f"- **Total:** {n['total_candidates']:,}",
        f"- **Priority range:** median={n['priority_median']}, max={n['priority_max']}",
        "",
        "### By Rule",
        "",
        "| Rule | Count |",
        "|:-----|------:|",
    ]
    for rule, count in sorted(n["by_rule"].items(), key=lambda x: -x[1]):
        lines.append(f"| {rule} | {count:,} |")

    lines += [
        "",
        "## Next Steps",
        "",
        "- Open output files in `~/data/vista-fm-browser/`",
        "- Filter `phase7/normalization_candidates.json` by `priority >= 10` for the short list",
        "- Start Flask UI: `fm-browser serve` → http://localhost:5000",
        "",
    ]
    path.write_text("\n".join(lines))


def print_dashboard(rollup: dict) -> None:
    def panel(title: str, rows: list[tuple[str, object]]) -> Panel:
        t = Table.grid(padding=(0, 2))
        t.add_column(style="dim")
        t.add_column(style="bold cyan", justify="right")
        for label, value in rows:
            t.add_row(label, str(value))
        return Panel(t, title=f"[bold]{title}[/bold]", border_style="blue")

    s = rollup["scope"]
    v = rollup["volume"]["tier_counts"]
    t = rollup["topology"]
    va = rollup["variety"]
    n = rollup["normalization"]

    console.print()
    console.print(Columns([
        panel("Scope", [
            ("Files", f"{s['total_files']:,}"),
            ("Fields", f"{s['total_fields']:,}"),
            ("Packages", f"{s['total_packages']:,}"),
            ("With data", f"{s['files_with_data']:,}"),
            ("Entries", f"{s['total_entries']:,}"),
        ]),
        panel("Volume", [
            ("Massive", v.get("massive", 0)),
            ("Large", v.get("large", 0)),
            ("Medium", v.get("medium", 0)),
            ("Small", v.get("small", 0)),
            ("Tiny", v.get("tiny", 0)),
        ]),
        panel("Topology", [
            ("Edges", f"{t['total_pointer_edges']:,}"),
            ("Hubs ≥10", t["hub_files_10plus"]),
            ("VP fields", t["variable_pointer_fields"]),
            ("MULTIPLE", t["multiple_fields"]),
        ]),
        panel("Variety", [
            ("Labels", f"{va['unique_labels']:,}"),
            ("SET w/ vals", va["set_fields_with_values"]),
            ("Shared sets", va["shared_sets_count"]),
            ("L-T conflicts", va["label_type_inconsistencies"]),
        ]),
        panel("Norm.", [
            ("Candidates", f"{n['total_candidates']:,}"),
            ("Priority max", n["priority_max"]),
            ("Priority med", n["priority_median"]),
        ]),
    ], equal=True))

    if t["top_hubs"]:
        hub_t = Table(title="Top Hubs", box=box.SIMPLE)
        hub_t.add_column("File #", style="cyan", justify="right")
        hub_t.add_column("Label", style="white")
        hub_t.add_column("Inbound", style="yellow", justify="right")
        for h in t["top_hubs"][:10]:
            hub_t.add_row(f"{h.get('file_number', 0):.10g}",
                          h.get("label", "?"), str(h.get("inbound_count", 0)))
        console.print(hub_t)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 8 — Rollup")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rollup = build_rollup()
    print_dashboard(rollup)

    (OUTPUT_DIR / "normalization_report.json").write_text(
        json.dumps(rollup, indent=2, default=str)
    )
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(rollup, indent=2, default=str))
    write_report(rollup, OUTPUT_DIR / "phase8-rollup-report.md")

    console.print()
    for name in ["normalization_report.json", "summary.json", "phase8-rollup-report.md"]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 8 rollup complete — analysis finished")
    console.print("\nNext: run [bold]phase8-viz.py[/bold] to generate the summary dashboard PNG.")


if __name__ == "__main__":
    main()
