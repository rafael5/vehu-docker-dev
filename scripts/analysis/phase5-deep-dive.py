"""
Phase 5 — Schema Deep Dive (Analysis)
======================================
Goal: Drill into a specific file for full field-level schema including
storage layout, validation logic, help text, and last-edit dates.

By default analyses File #2 (PATIENT). Pass --file <number> for another.

This is analysis-only. Visualization is handled by phase5-viz.py.

Outputs (all in ~/data/vista-fm-browser/phase5/):
    schema_<file_num>.json         — per-field extended attributes
    schema_<file_num>.csv          — same data flat
    storage_<file_num>.json        — zero-node layout grouping
    cross_refs_<file_num>.json     — cross-reference inventory
    summary_<file_num>.json        — completeness stats + top issues
    phase5-deep-dive-report.md     — report for last-analysed file (overwritten each run)
    packages/<pkg>.json            — per-package schema (with --batch)

Run inside the VEHU container:
    python scripts/analysis/phase5-deep-dive.py              # PATIENT
    python scripts/analysis/phase5-deep-dive.py --file 200   # NEW PERSON
    python scripts/analysis/phase5-deep-dive.py --batch      # also per-pkg export
"""

import argparse
import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase5/").expanduser()


def collect_field_attributes(conn: YdbConnection, file_num: float) -> list[dict]:
    dd = DataDictionary(conn)
    fd = dd.get_file(file_num)
    if fd is None:
        console.print(f"[red]File {file_num} not found[/red]")
        return []
    console.print(f"\n[bold]File {file_num}: {fd.label}  ({fd.field_count} fields)[/bold]")

    rows: list[dict] = []
    for field_num in sorted(fd.fields.keys()):
        fa = dd.get_field_attributes(file_num, field_num)
        if fa is None:
            continue
        rows.append({
            "field": fa.field_number,
            "label": fa.label,
            "type_code": fa.datatype_code,
            "type_name": fa.datatype_name,
            "storage": fa.global_subscript,
            "pointer_file": fa.pointer_file,
            "set_values": fa.set_values,
            "help_prompt": fa.help_prompt or "",
            "description": " ".join(fa.description) if fa.description else "",
            "has_description": bool(fa.description),
            "input_transform": fa.input_transform or "",
            "has_input_transform": bool(fa.input_transform),
            "last_edited": fa.last_edited,
        })
    return rows


def build_storage_layout(fields: list[dict]) -> dict[str, list[dict]]:
    node_map: dict[str, list[dict]] = defaultdict(list)
    for r in fields:
        loc = r["storage"]
        if loc and ";" in loc:
            node = loc.split(";", 1)[0]
            node_map[node].append({"field": r["field"], "label": r["label"]})
    return dict(node_map)


def collect_cross_refs(conn: YdbConnection, file_num: float) -> list[dict]:
    dd = DataDictionary(conn)
    return [
        {
            "ien": ref.ien, "file_number": ref.file_number,
            "name": ref.name, "xref_type": ref.xref_type,
            "description": ref.description,
        }
        for ref in dd.list_cross_refs(file_num)
    ]


def build_summary(file_num: float, file_label: str, fields: list[dict],
                  storage: dict, xrefs: list[dict]) -> dict:
    total = len(fields)
    if total == 0:
        return {"file_number": file_num, "file_label": file_label, "total_fields": 0}
    return {
        "file_number": file_num, "file_label": file_label,
        "total_fields": total,
        "fields_with_description": sum(1 for r in fields if r["has_description"]),
        "fields_with_input_transform": sum(1 for r in fields if r["has_input_transform"]),
        "fields_with_set_values": sum(1 for r in fields if r["set_values"]),
        "fields_with_help_prompt": sum(1 for r in fields if r["help_prompt"]),
        "fields_with_last_edited": sum(1 for r in fields if r["last_edited"]),
        "storage_node_count": len(storage),
        "largest_storage_node": (
            max(storage.items(), key=lambda kv: len(kv[1]))[0] if storage else None
        ),
        "largest_storage_node_size": (
            max(len(v) for v in storage.values()) if storage else 0
        ),
        "cross_ref_count": len(xrefs),
        "fields_preview": [
            {"field": r["field"], "label": r["label"], "type": r["type_name"],
             "storage": r["storage"]}
            for r in fields[:20]
        ],
    }


def write_schema_csv(fields: list[dict], path: Path) -> None:
    cols = ["field", "label", "type_code", "type_name", "storage", "pointer_file",
            "has_description", "has_input_transform", "last_edited", "help_prompt"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in fields:
            row = {k: r.get(k, "") for k in cols}
            row["help_prompt"] = row["help_prompt"][:120]
            w.writerow(row)


def batch_export(conn: YdbConnection) -> None:
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
                pkg_schema.append({
                    "file_number": fr.file_number, "file_label": fr.label,
                    "field_number": field_num, "field_label": fld.label,
                    "type_code": fld.datatype_code, "type_name": fld.datatype_name,
                    "pointer_file": fld.pointer_file,
                })
        safe = pkg_name.replace("/", "_").replace(" ", "_").lower()[:40]
        (out_dir / f"{safe}.json").write_text(json.dumps(pkg_schema, indent=2, default=str))
    console.print(f"  [green]wrote[/green] {out_dir}/")


def render_terminal(summary: dict, storage: dict, xrefs: list[dict]) -> None:
    if summary.get("total_fields", 0) == 0:
        return
    t = Table(title=f"Storage Nodes — {summary['file_label']}")
    t.add_column("Node", style="cyan", justify="center")
    t.add_column("Fields", style="yellow", justify="right")
    t.add_column("Sample", style="white")
    for node in sorted(storage.keys(), key=lambda x: (len(x), x)):
        fields = storage[node]
        sample = ", ".join(f"{f['field']:.4f} {f['label']}" for f in fields[:4])
        if len(fields) > 4:
            sample += f" … +{len(fields) - 4}"
        t.add_row(node, str(len(fields)), sample)
    console.print(t)

    console.print(f"\n[bold]Cross-references: {len(xrefs)}[/bold]")
    for r in xrefs[:10]:
        console.print(f"  '{r['name']}' ({r['xref_type']}) {r['description'][:60]}")


def write_report(summary: dict, storage: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fn = summary.get("file_number", "?")
    fl = summary.get("file_label", "?")
    total = summary.get("total_fields", 0)
    if total == 0:
        path.write_text(f"# Phase 5 — No fields found for File #{fn}\n")
        return
    pct = lambda k: 100 * summary.get(k, 0) / total

    lines = [
        f"# Phase 5 — Schema Deep Dive: File #{fn:.10g} ({fl})",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Total fields:** {total:,}",
        f"- **With description:** {summary['fields_with_description']:,} ({pct('fields_with_description'):.1f}%)",
        f"- **With input transform:** {summary['fields_with_input_transform']:,} ({pct('fields_with_input_transform'):.1f}%)",
        f"- **With SET values:** {summary['fields_with_set_values']:,} ({pct('fields_with_set_values'):.1f}%)",
        f"- **With help prompt:** {summary['fields_with_help_prompt']:,} ({pct('fields_with_help_prompt'):.1f}%)",
        f"- **Storage nodes:** {summary['storage_node_count']}",
        f"- **Largest node:** `{summary['largest_storage_node']}` with {summary['largest_storage_node_size']} fields",
        f"- **Cross-references:** {summary['cross_ref_count']}",
        "",
        "## Storage Nodes",
        "",
        "| Node | Fields |",
        "|:----:|------:|",
    ]
    for node in sorted(storage.keys(), key=lambda x: (len(x), x)):
        lines.append(f"| {node} | {len(storage[node])} |")

    lines += [
        "",
        "## Field Preview (first 20)",
        "",
        "| Field # | Label | Type | Storage |",
        "|--------:|:------|:-----|:--------|",
    ]
    for r in summary["fields_preview"]:
        lines.append(f"| {r['field']:.4f} | {r['label']} | {r['type']} | {r['storage']} |")

    lines += [
        "",
        "## Output Files",
        "",
        f"- `schema_{int(fn)}.json` / `.csv` — per-field extended attributes",
        f"- `storage_{int(fn)}.json` — storage-node layout",
        f"- `cross_refs_{int(fn)}.json` — cross-reference inventory",
        f"- `summary_{int(fn)}.json` — stats (consumed by viz + report)",
        f"- `phase5_schema_{int(fn)}.png` — completeness heatmap (phase5-viz.py)",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 — Schema Deep Dive")
    parser.add_argument("--file", type=float, default=2.0,
                        help="FileMan file number (default: 2 = PATIENT)")
    parser.add_argument("--batch", action="store_true",
                        help="Also run per-package batch export (slow)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    console.rule(f"[bold blue]Phase 5 — Schema Deep Dive (File #{args.file})")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        dd = DataDictionary(conn)
        fd = dd.get_file(args.file)
        fl = fd.label if fd else f"File #{args.file}"

        fields = collect_field_attributes(conn, args.file)
        storage = build_storage_layout(fields)
        xrefs = collect_cross_refs(conn, args.file)

        if args.batch:
            batch_export(conn)

    summary = build_summary(args.file, fl, fields, storage, xrefs)
    render_terminal(summary, storage, xrefs)

    tag = f"{int(args.file)}" if args.file == int(args.file) else f"{args.file:.4g}"
    (OUTPUT_DIR / f"schema_{tag}.json").write_text(json.dumps(fields, indent=2, default=str))
    write_schema_csv(fields, OUTPUT_DIR / f"schema_{tag}.csv")
    (OUTPUT_DIR / f"storage_{tag}.json").write_text(json.dumps(storage, indent=2, default=str))
    (OUTPUT_DIR / f"cross_refs_{tag}.json").write_text(json.dumps(xrefs, indent=2, default=str))
    (OUTPUT_DIR / f"summary_{tag}.json").write_text(json.dumps(summary, indent=2, default=str))
    # summary.json is the "latest" — viz picks this up
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(
        {**summary, "fields": fields, "storage": storage}, indent=2, default=str
    ))
    write_report(summary, storage, OUTPUT_DIR / "phase5-deep-dive-report.md")

    console.print()
    for name in [
        f"schema_{tag}.json", f"schema_{tag}.csv",
        f"storage_{tag}.json", f"cross_refs_{tag}.json", f"summary_{tag}.json",
        "summary.json", "phase5-deep-dive-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 5 analysis complete")
    console.print("\nNext: run [bold]phase5-viz.py[/bold] to generate PNG visualizations.")


if __name__ == "__main__":
    main()
