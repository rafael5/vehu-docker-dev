"""
Phase 5 — Schema Deep Dive
==========================
Goal: After the big picture is clear, drill into specific files to get the
full field-level schema including storage layout, validation logic, help text,
and last-edit dates.

By default analyses File #2 (PATIENT). Pass --file <number> to analyse
a different file.

Prerequisites:
    phase1_scope.py — inventory.json

Outputs:
    ~/data/vista-fm-browser/output/phase5_schema_<file_num>.png
    ~/data/vista-fm-browser/output/packages/<package_name>.json  (batch export)

Run inside the VEHU container:
    python scripts/analysis/phase5_deep_dive.py
    python scripts/analysis/phase5_deep_dive.py --file 200
"""

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()


def section_51_full_field_attrs(conn: YdbConnection, file_num: float) -> list[dict]:
    """5.1 — Full field attributes for one file."""
    dd = DataDictionary(conn)
    fd = dd.get_file(file_num)
    if fd is None:
        console.print(f"[red]File {file_num} not found in data dictionary[/red]")
        return []

    console.print(f"\n[bold]File {file_num}: {fd.label}  ({fd.field_count} fields)[/bold]")

    extended = []
    for field_num in sorted(fd.fields.keys()):
        fa = dd.get_field_attributes(file_num, field_num)
        if fa is None:
            continue
        extended.append(
            {
                "field": fa.field_number,
                "label": fa.label,
                "type": fa.datatype_name,
                "storage": fa.global_subscript,
                "pointer_file": fa.pointer_file,
                "set_values": fa.set_values,
                "help_prompt": (fa.help_prompt or "")[:60],
                "has_description": bool(fa.description),
                "input_transform": bool(fa.input_transform),
                "last_edited": fa.last_edited,
            }
        )
        console.print(
            f"  {fa.field_number:8.4f}  {fa.label:30s}  {fa.datatype_name:15s}  "
            f"loc={fa.global_subscript:8s}"
        )

    return extended


def section_52_storage_layout(extended: list[dict], label: str) -> dict[str, list[str]]:
    """5.2 — Storage layout: zero-node density."""
    node_map: dict[str, list[str]] = defaultdict(list)
    for row in extended:
        loc = row["storage"]
        if loc and ";" in loc:
            node, _piece = loc.split(";", 1)
            node_map[node].append(f"{row['field']:.4f} {row['label']}")

    t = Table(title=f"Storage Nodes — {label}", show_lines=True)
    t.add_column("Node", style="cyan", justify="center", width=8)
    t.add_column("Fields", style="yellow", justify="right", width=6)
    t.add_column("Field list", style="white")
    for node in sorted(node_map.keys(), key=lambda x: (len(x), x)):
        fields_str = ", ".join(node_map[node][:6])
        if len(node_map[node]) > 6:
            fields_str += f" … +{len(node_map[node]) - 6} more"
        t.add_row(node, str(len(node_map[node])), fields_str)
    console.print(t)

    return node_map


def section_53_cross_refs(conn: YdbConnection, file_num: float) -> None:
    """5.3 — Cross-reference inventory."""
    dd = DataDictionary(conn)
    fd = dd.get_file(file_num)
    if fd is None:
        return
    refs = dd.list_cross_refs(file_num)
    console.print(f"\n[bold]Cross-references for {fd.label}:[/bold]")
    for ref in refs:
        console.print(f"  '{ref.name}' ({ref.xref_type})  {ref.description[:60]}")


def section_54_batch_export(conn: YdbConnection) -> None:
    """5.4 — Per-package schema batch export."""
    fi = FileInventory(conn)
    fi.load()
    dd = DataDictionary(conn)

    out_dir = OUTPUT_DIR / "packages"
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print("\n[bold]Exporting per-package schemas...[/bold]")
    for pkg_name, files in fi.files_by_package().items():
        pkg_schema = []
        for fr in files:
            fd = dd.get_file(fr.file_number)
            if not fd:
                continue
            for field_num, fld in fd.fields.items():
                pkg_schema.append(
                    {
                        "file_number": fr.file_number,
                        "file_label": fr.label,
                        "field_number": field_num,
                        "field_label": fld.label,
                        "type_code": fld.datatype_code,
                        "type_name": fld.datatype_name,
                        "pointer_file": fld.pointer_file,
                    }
                )
        safe = pkg_name.replace("/", "_").replace(" ", "_").lower()[:40]
        (out_dir / f"{safe}.json").write_text(
            json.dumps(pkg_schema, indent=2, default=str)
        )

    console.print(f"Package schemas written to [green]{out_dir}[/green]")


def visualize(extended: list[dict], fd_label: str, file_num: float) -> None:
    """Attribute completeness heatmap."""
    if not extended:
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def has_val(row: dict, key: str) -> float:
        v = row.get(key)
        if v is None or v == "" or v is False:
            return 0.0
        return 1.0

    def has_set(row: dict) -> float:
        sv = row.get("set_values") or {}
        return 1.0 if sv else 0.0

    mat = np.array(
        [
            [
                has_val(r, "has_description"),
                has_val(r, "input_transform"),
                has_set(r),
                1.0 if r.get("last_edited") else 0.0,
                1.0 if r.get("help_prompt") else 0.0,
            ]
            for r in extended
        ],
        dtype=float,
    )

    attr_labels = ["Description", "Input Transform", "Set Values", "Last Edited", "Help Prompt"]
    field_names = [f"{r['field']:.4f} {r['label'][:30]}" for r in extended]

    fig, ax = plt.subplots(figsize=(10, max(6, len(field_names) * 0.22)))
    im = ax.imshow(mat, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(attr_labels)))
    ax.set_yticks(range(len(field_names)))
    ax.set_xticklabels(attr_labels, fontsize=9)
    ax.set_yticklabels(field_names, fontsize=6)
    plt.colorbar(im, ax=ax, label="Present (1) / Absent (0)", shrink=0.4)
    ax.set_title(
        f"Field Documentation Completeness — {fd_label} (File #{file_num})\n"
        "Green = attribute present, Red = missing"
    )
    plt.tight_layout()
    out_path = OUTPUT_DIR / f"phase5_schema_{int(file_num)}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Schema heatmap saved to [green]{out_path}[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 — Schema Deep Dive")
    parser.add_argument(
        "--file",
        type=float,
        default=2.0,
        help="FileMan file number to analyse (default: 2 = PATIENT)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Also run per-package batch export (slow)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    console.rule(f"[bold blue]Phase 5 — Schema Deep Dive (File #{args.file})")

    with YdbConnection.connect() as conn:
        dd = DataDictionary(conn)
        fd = dd.get_file(args.file)
        fd_label = fd.label if fd else f"File #{args.file}"

        extended = section_51_full_field_attrs(conn, args.file)
        if extended:
            section_52_storage_layout(extended, fd_label)
        section_53_cross_refs(conn, args.file)

        if args.batch:
            section_54_batch_export(conn)

    visualize(extended, fd_label, args.file)

    console.rule("[bold green]Phase 5 complete")


if __name__ == "__main__":
    main()
