"""
Phase 8 — Normalization Report
================================
Goal: Produce the final summary report combining all phase outputs into a
single JSON and a rich terminal dashboard.

Prerequisites (run all prior phases first):
    phase1_scope.py    → inventory.json
    phase2_volume.py   → file_volume.json, file_volume.csv
    phase3_topology.py → all_fields.json, pointer_graph.json
    phase4_variety.py  → (builds from all_fields.json)
    phase7_candidates.py → normalization_candidates.json

Outputs:
    ~/data/vista-fm-browser/output/normalization_report.json

Run inside the VEHU container:
    python scripts/analysis/phase8_report.py
"""

import collections
import json
import logging
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()


def load_json(path: Path) -> dict | list | None:
    if path.exists():
        return json.loads(path.read_text())
    console.print(f"[yellow]Missing: {path}[/yellow]  (run the corresponding phase first)")
    return None


def build_report(conn: YdbConnection) -> dict:
    dd = DataDictionary(conn)
    fi = FileInventory(conn)
    fi.load()

    all_files = dd.list_files()

    # Schema stats (from all_fields.json if available)
    schema_path = OUTPUT_DIR / "all_fields.json"
    schema: list[dict] = []
    if schema_path.exists():
        schema = json.loads(schema_path.read_text())
    total_fields = len(schema) if schema else sum(
        (dd.get_file(fn) or type("_", (), {"field_count": 0})()).field_count
        for fn, _ in all_files
    )

    # Type distribution
    type_counts: dict[str, int] = collections.Counter(
        r["datatype_code"] for r in schema
    )

    # Volume stats (from file_volume.json if available)
    volume_data = load_json(OUTPUT_DIR / "file_volume.json") or []
    volume = [(r["entry_count"], r["file_number"]) for r in volume_data]
    files_with_data = len([v for v in volume if v[0] > 0])

    # Pointer topology (from all_fields.json)
    pointer_fields = [r for r in schema if r["datatype_code"] == "P" and r["pointer_file"]]
    inbound: dict[float, set[float]] = {}
    for r in pointer_fields:
        tgt = r["pointer_file"]
        inbound.setdefault(tgt, set()).add(r["file_number"])

    hub_files_10_plus = [
        {"file": tgt, "inbound_count": len(srcs)}
        for tgt, srcs in sorted(inbound.items(), key=lambda x: -len(x[1]))
        if len(srcs) >= 10
    ]

    # SET / variety (from all_fields.json)
    set_fields = [r for r in schema if r["datatype_code"] == "S" and r["set_values"]]

    def canon_set(sv: dict) -> frozenset:
        return frozenset((k.strip().upper(), v.strip().upper()) for k, v in sv.items())

    seen_sets: dict[frozenset, list] = {}
    for r in set_fields:
        key = canon_set(r["set_values"])
        seen_sets.setdefault(key, []).append(r)
    shared_5_plus = [k for k, v in seen_sets.items() if len(v) >= 5]

    # Label-type conflicts
    label_groups: dict[str, list] = {}
    for r in schema:
        label_groups.setdefault(r["field_label"].strip().upper(), []).append(r)
    label_conflicts = sum(
        1
        for rows in label_groups.values()
        if len(rows) >= 5 and len({r["datatype_code"] for r in rows}) > 1
    )

    date_as_text = sum(
        1
        for r in schema
        if "DATE" in r["field_label"].upper() and r["datatype_code"] == "F"
    )

    # Candidates (from normalization_candidates.json)
    candidates_data = load_json(OUTPUT_DIR / "normalization_candidates.json") or []
    total_candidates = len(candidates_data)

    report = {
        "scope": {
            "total_files": len(all_files),
            "total_fields": total_fields,
            "total_packages": len(fi.list_packages()),
            "files_with_data": files_with_data,
            "files_empty": len(all_files) - files_with_data,
        },
        "volume": {
            "massive_100k_plus": len([v for v in volume if v[0] >= 100_000]),
            "large_10k_100k": len([v for v in volume if 10_000 <= v[0] < 100_000]),
            "medium_1k_10k": len([v for v in volume if 1_000 <= v[0] < 10_000]),
            "small_under_1k": len([v for v in volume if 0 < v[0] < 1_000]),
        },
        "type_distribution": dict(type_counts),
        "pointer_topology": {
            "total_pointer_fields": len(pointer_fields),
            "hub_files_10plus_refs": len(hub_files_10_plus),
            "top_hubs": hub_files_10_plus[:20],
        },
        "variety": {
            "set_fields_total": len(set_fields),
            "unique_value_sets": len(seen_sets),
            "shared_value_sets_5plus": len(shared_5_plus),
            "label_type_conflicts": label_conflicts,
            "date_as_free_text": date_as_text,
        },
        "normalization_candidates_total": total_candidates,
    }

    return report


def export_report(report: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "normalization_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    console.print(f"Normalization report written to [green]{out}[/green]")


def print_dashboard(report: dict, conn: YdbConnection) -> None:
    def stat_panel(title: str, rows: list[tuple[str, object]]) -> Panel:
        t = Table.grid(padding=(0, 2))
        t.add_column(style="dim")
        t.add_column(style="bold cyan", justify="right")
        for label, value in rows:
            t.add_row(label, str(value))
        return Panel(t, title=f"[bold]{title}[/bold]", border_style="blue")

    scope_panel = stat_panel(
        "Scope",
        [
            ("Total files", report["scope"]["total_files"]),
            ("Total fields", report["scope"]["total_fields"]),
            ("Packages", report["scope"]["total_packages"]),
            ("Files with data", report["scope"]["files_with_data"]),
            ("Empty files", report["scope"]["files_empty"]),
        ],
    )

    volume_panel = stat_panel(
        "Volume Tiers",
        [
            ("Massive (>100K)", report["volume"]["massive_100k_plus"]),
            ("Large (10K–100K)", report["volume"]["large_10k_100k"]),
            ("Medium (1K–10K)", report["volume"]["medium_1k_10k"]),
            ("Small (<1K)", report["volume"]["small_under_1k"]),
        ],
    )

    topo_panel = stat_panel(
        "Topology",
        [
            ("Pointer fields", report["pointer_topology"]["total_pointer_fields"]),
            ("Hub files (≥10)", report["pointer_topology"]["hub_files_10plus_refs"]),
        ],
    )

    variety_panel = stat_panel(
        "Variety",
        [
            ("SET fields", report["variety"]["set_fields_total"]),
            ("Unique value sets", report["variety"]["unique_value_sets"]),
            ("Shared sets (≥5)", report["variety"]["shared_value_sets_5plus"]),
            ("Label-type conflicts", report["variety"]["label_type_conflicts"]),
            ("Date-as-text fields", report["variety"]["date_as_free_text"]),
        ],
    )

    norm_panel = stat_panel(
        "Normalization",
        [("Total candidates", report["normalization_candidates_total"])],
    )

    console.print()
    console.print(
        Columns(
            [scope_panel, volume_panel, topo_panel, variety_panel, norm_panel],
            equal=True,
        )
    )

    # Top 10 hub files table
    hub_t = Table(title="Top Hub Files", box=box.SIMPLE, show_header=True)
    hub_t.add_column("File #", style="cyan", justify="right")
    hub_t.add_column("Label", style="white")
    hub_t.add_column("Inbound", style="yellow", justify="right")

    dd = DataDictionary(conn)
    for h in report["pointer_topology"]["top_hubs"][:10]:
        fd = dd.get_file(float(h["file"]))
        hub_t.add_row(
            str(h["file"]),
            fd.label if fd else "?",
            str(h["inbound_count"]),
        )
    console.print(hub_t)

    # Type distribution summary
    type_t = Table(title="Field Type Distribution", box=box.SIMPLE)
    type_t.add_column("Code", style="cyan")
    type_t.add_column("Count", style="yellow", justify="right")
    type_t.add_column("%", style="green", justify="right")
    total_types = sum(report["type_distribution"].values())
    for code, count in sorted(
        report["type_distribution"].items(), key=lambda x: -x[1]
    ):
        pct = 100 * count / total_types if total_types else 0
        type_t.add_row(code, f"{count:,}", f"{pct:.1f}%")
    console.print(type_t)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 8 — Normalization Report")

    with YdbConnection.connect() as conn:
        report = build_report(conn)
        export_report(report)
        print_dashboard(report, conn)

    console.rule("[bold green]Phase 8 complete — analysis finished")
    console.print(
        "\nNext steps:\n"
        "  • Open output files in ~/data/vista-fm-browser/output/\n"
        "  • Generate interactive visualizations with scripts/to_treemap.py and scripts/viz_library.py\n"
        "  • Review normalization_candidates.json (filter priority ≥ 10 for the short list)\n"
        "  • Start Flask UI: fm-browser serve → http://localhost:5000"
    )


if __name__ == "__main__":
    main()
