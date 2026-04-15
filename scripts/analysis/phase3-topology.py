"""
Phase 3 — Structural Topology (Analysis)
=========================================
Goal: Map the pointer graph — how files reference each other.
Identify hub files (most-referenced) and outbound-dense files.

This is analysis-only. Visualization is handled by phase3-viz.py.

Outputs (all in ~/data/vista-fm-browser/phase3/):
    all_fields.json           — full schema cache (consumed by phases 4, 7, 8)
    pointer_graph.json        — edge list with src/tgt file, package, field info
    pointer_graph.csv         — same edges flat
    hub_files.csv             — files with ≥10 inbound pointers
    summary.json              — hub + topology stats (consumed by viz + report)
    phase3-topology-report.md — executive report

Run inside the VEHU container:
    python scripts/analysis/phase3-topology.py
"""

import collections
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase3/").expanduser()


def build_schema(conn: YdbConnection) -> list[dict]:
    """Build full schema list (all fields across all files). Cached to all_fields.json."""
    cache = OUTPUT_DIR / "all_fields.json"
    if cache.exists():
        console.print(f"[dim]Loading cached schema from {cache}[/dim]")
        return json.loads(cache.read_text())

    console.print("\n[bold]Building full schema (reading all ^DD entries)...[/bold]")
    dd = DataDictionary(conn)
    fi = FileInventory(conn)
    fi.load()

    pkg_by_file: dict[float, str] = {
        fr.file_number: (fr.package_name or "(unpackaged)") for fr in fi.list_files()
    }
    label_by_file: dict[float, str] = {
        fr.file_number: fr.label for fr in fi.list_files()
    }

    schema: list[dict] = []
    for file_num, file_label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for field_num, fld in fd.fields.items():
            schema.append({
                "file_number": file_num,
                "file_label": label_by_file.get(file_num, file_label),
                "package": pkg_by_file.get(file_num, "(unpackaged)"),
                "field_number": field_num,
                "field_label": fld.label,
                "datatype_code": fld.datatype_code,
                "datatype_name": fld.datatype_name,
                "pointer_file": fld.pointer_file,
                "set_values": fld.set_values,
            })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(schema, indent=2, default=str))
    console.print(
        f"Schema: [bold]{len(schema):,}[/bold] fields across "
        f"{len(dd.list_files()):,} files\n"
        f"Written to [green]{cache}[/green]"
    )
    return schema


def collect_pointer_edges(schema: list[dict]) -> list[dict]:
    """Extract pointer (P-type) fields as edge dicts with source + target info."""
    label_by_file = {r["file_number"]: r["file_label"] for r in schema}
    pkg_by_file = {r["file_number"]: r["package"] for r in schema}

    edges: list[dict] = []
    for r in schema:
        if r["datatype_code"] != "P" or not r["pointer_file"]:
            continue
        tgt = r["pointer_file"]
        edges.append({
            "from_file": r["file_number"],
            "from_label": r["file_label"],
            "from_pkg": r["package"],
            "field_num": r["field_number"],
            "field_label": r["field_label"],
            "to_file": tgt,
            "to_label": label_by_file.get(tgt, ""),
            "to_pkg": pkg_by_file.get(tgt, "(unpackaged)"),
        })
    return edges


def compute_topology_stats(edges: list[dict]) -> dict:
    """Compute inbound/outbound counts + hub list."""
    inbound: dict[float, set] = {}
    outbound: dict[float, set] = {}
    for e in edges:
        inbound.setdefault(e["to_file"], set()).add(e["from_file"])
        outbound.setdefault(e["from_file"], set()).add(e["to_file"])

    label_by_file: dict[float, str] = {}
    pkg_by_file: dict[float, str] = {}
    for e in edges:
        label_by_file[e["from_file"]] = e["from_label"]
        label_by_file[e["to_file"]] = e["to_label"]
        pkg_by_file[e["from_file"]] = e["from_pkg"]
        pkg_by_file[e["to_file"]] = e["to_pkg"]

    hubs = sorted(
        (
            {
                "file_number": tgt,
                "label": label_by_file.get(tgt, ""),
                "package": pkg_by_file.get(tgt, ""),
                "inbound_count": len(srcs),
            }
            for tgt, srcs in inbound.items()
            if len(srcs) >= 10
        ),
        key=lambda x: -x["inbound_count"],
    )

    outbound_top = sorted(
        (
            {
                "file_number": src,
                "label": label_by_file.get(src, ""),
                "package": pkg_by_file.get(src, ""),
                "outbound_count": len(tgts),
            }
            for src, tgts in outbound.items()
        ),
        key=lambda x: -x["outbound_count"],
    )[:30]

    return {
        "total_pointer_edges": len(edges),
        "unique_source_files": len(outbound),
        "unique_target_files": len(inbound),
        "hub_files_10plus": len(hubs),
        "top_hubs": hubs[:30],
        "top_outbound": outbound_top,
    }


def compute_variety_stats(schema: list[dict]) -> dict:
    """Variable pointer (V) + MULTIPLE (M) field distributions."""
    vps = [r for r in schema if r["datatype_code"] == "V"]
    multiples = [r for r in schema if r["datatype_code"] == "M"]
    label_by_file = {r["file_number"]: r["file_label"] for r in schema}

    vp_top = [
        {"file_number": fn, "label": label_by_file.get(fn, ""), "count": c}
        for fn, c in collections.Counter(r["file_number"] for r in vps).most_common(15)
    ]
    m_top = [
        {"file_number": fn, "label": label_by_file.get(fn, ""), "count": c}
        for fn, c in collections.Counter(r["file_number"] for r in multiples).most_common(15)
    ]

    return {
        "variable_pointer_fields": len(vps),
        "multiple_fields": len(multiples),
        "top_variable_pointer_files": vp_top,
        "top_multiple_files": m_top,
    }


def compute_package_matrix(schema: list[dict], edges: list[dict], top_n: int = 15) -> dict:
    """Cross-package pointer dependency counts (top N packages)."""
    pkg_pairs: dict[tuple[str, str], int] = collections.Counter()
    for e in edges:
        src_pkg = e["from_pkg"]
        tgt_pkg = e["to_pkg"]
        if src_pkg != tgt_pkg:
            pkg_pairs[(src_pkg, tgt_pkg)] += 1

    involvement: dict[str, int] = collections.Counter()
    for (s, t), v in pkg_pairs.items():
        involvement[s] += v
        involvement[t] += v
    top_pkgs = [p for p, _ in involvement.most_common(top_n)]

    matrix: list[dict] = []
    for src in top_pkgs:
        row = {"package": src}
        for tgt in top_pkgs:
            row[tgt] = pkg_pairs.get((src, tgt), 0)
        matrix.append(row)
    return {"top_packages": top_pkgs, "matrix": matrix}


# ---------------------------------------------------------------------------
# Data-file writers
# ---------------------------------------------------------------------------


def write_pointer_graph(edges: list[dict], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(edges, indent=2, default=str))
    fields = ["from_file", "from_label", "from_pkg", "field_num", "field_label",
              "to_file", "to_label", "to_pkg"]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(edges)


def write_hub_csv(hubs: list[dict], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file_number", "label", "package", "inbound_count"])
        w.writeheader()
        w.writerows(hubs)


def write_summary(topology: dict, variety: dict, pkg_matrix: dict, path: Path) -> None:
    path.write_text(json.dumps({**topology, **variety, "package_matrix": pkg_matrix},
                               indent=2, default=str))


def write_report(topology: dict, variety: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Phase 3 — Structural Topology",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Pointer edges:** {topology['total_pointer_edges']:,}",
        f"- **Unique source files:** {topology['unique_source_files']:,}",
        f"- **Unique target files:** {topology['unique_target_files']:,}",
        f"- **Hub files (≥10 inbound):** {topology['hub_files_10plus']:,}",
        f"- **Variable pointer fields (V-type):** {variety['variable_pointer_fields']:,}",
        f"- **MULTIPLE fields (sub-files, M-type):** {variety['multiple_fields']:,}",
        "",
        "## Top 20 Hub Files (most referenced)",
        "",
        "| Rank | File # | Label | Package | Inbound |",
        "|-----:|-------:|:------|:--------|--------:|",
    ]
    for i, h in enumerate(topology["top_hubs"][:20], 1):
        lines.append(
            f"| {i} | {h['file_number']:.10g} | {h['label']} | "
            f"{h['package'] or '—'} | {h['inbound_count']} |"
        )

    lines += [
        "",
        "## Top 15 Outbound-Dense Files (most FK-rich)",
        "",
        "| Rank | File # | Label | Package | Outbound |",
        "|-----:|-------:|:------|:--------|---------:|",
    ]
    for i, r in enumerate(topology["top_outbound"][:15], 1):
        lines.append(
            f"| {i} | {r['file_number']:.10g} | {r['label']} | "
            f"{r['package'] or '—'} | {r['outbound_count']} |"
        )

    lines += [
        "",
        "## Output Files",
        "",
        "- `all_fields.json` — full schema cache (for phases 4, 7, 8)",
        "- `pointer_graph.json` / `.csv` — edge list",
        "- `hub_files.csv` — files with ≥10 inbound pointers",
        "- `summary.json` — topology stats (consumed by viz + report)",
        "- `phase3_pointer_graph.png` / `.dot` — graph visualizations",
        "- `phase3_pkg_matrix.png` — cross-package dependency heatmap",
        "",
    ]
    path.write_text("\n".join(lines))


def render_terminal(topology: dict, variety: dict) -> None:
    console.print(f"\nPointer edges: [bold]{topology['total_pointer_edges']:,}[/bold]")
    console.print(f"Hub files (≥10 inbound): [bold]{topology['hub_files_10plus']}[/bold]")
    console.print(f"Variable pointer fields: [bold]{variety['variable_pointer_fields']}[/bold]")
    console.print(f"MULTIPLE fields:         [bold]{variety['multiple_fields']}[/bold]")
    console.print("\n[bold]Top 15 hubs:[/bold]")
    for h in topology["top_hubs"][:15]:
        console.print(
            f"  {h['file_number']:8.2f}  {h['label'][:40]:40s}  "
            f"← {h['inbound_count']:3d}  [{h['package'] or '?'}]"
        )


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 3 — Structural Topology (Analysis)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        schema = build_schema(conn)

    edges = collect_pointer_edges(schema)
    topology = compute_topology_stats(edges)
    variety = compute_variety_stats(schema)
    pkg_matrix = compute_package_matrix(schema, edges)

    render_terminal(topology, variety)

    write_pointer_graph(edges, OUTPUT_DIR / "pointer_graph.json",
                        OUTPUT_DIR / "pointer_graph.csv")
    write_hub_csv(topology["top_hubs"], OUTPUT_DIR / "hub_files.csv")
    write_summary(topology, variety, pkg_matrix, OUTPUT_DIR / "summary.json")
    write_report(topology, variety, OUTPUT_DIR / "phase3-topology-report.md")

    console.print()
    for name in [
        "all_fields.json", "pointer_graph.json", "pointer_graph.csv",
        "hub_files.csv", "summary.json", "phase3-topology-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 3 analysis complete")
    console.print("\nNext: run [bold]phase3-viz.py[/bold] to generate PNG + DOT visualizations.")


if __name__ == "__main__":
    main()
