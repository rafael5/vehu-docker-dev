"""
Phase 3 — Structural Topology
==============================
Goal: Map the pointer graph — how files reference each other.
Identifies hub files (most-referenced) and outbound-dense files.

Prerequisites:
    phase1_scope.py — inventory.json
    phase3 also reads all_fields.json if already cached; otherwise builds it.

Outputs:
    ~/data/vista-fm-browser/output/all_fields.json   (full schema cache)
    ~/data/vista-fm-browser/output/pointer_graph.json
    ~/data/vista-fm-browser/output/phase3_pointer_graph.png
    ~/data/vista-fm-browser/output/phase3_pkg_matrix.png
    ~/data/vista-fm-browser/output/phase3_pointer_graph.dot

Run inside the VEHU container:
    python scripts/analysis/phase3_topology.py
"""

import collections
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()


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

    schema: list[dict] = []
    for file_num, file_label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for field_num, fld in fd.fields.items():
            schema.append(
                {
                    "file_number": file_num,
                    "file_label": file_label,
                    "package": pkg_by_file.get(file_num, "(unpackaged)"),
                    "field_number": field_num,
                    "field_label": fld.label,
                    "datatype_code": fld.datatype_code,
                    "datatype_name": fld.datatype_name,
                    "pointer_file": fld.pointer_file,
                    "set_values": fld.set_values,
                }
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(schema, indent=2, default=str))
    console.print(
        f"Schema: [bold]{len(schema):,}[/bold] fields across "
        f"{len(dd.list_files()):,} files\n"
        f"Written to [green]{cache}[/green]"
    )
    return schema


def analyze_pointers(
    schema: list[dict], conn: YdbConnection
) -> tuple[list[dict], dict[float, set], dict[float, set]]:
    """
    Extract pointer fields and compute inbound/outbound edge sets.
    Returns (pointer_fields, inbound, outbound).
    """
    pointer_fields = [
        r for r in schema if r["datatype_code"] == "P" and r["pointer_file"]
    ]

    inbound: dict[float, set[float]] = {}
    for r in pointer_fields:
        tgt = r["pointer_file"]
        inbound.setdefault(tgt, set()).add(r["file_number"])

    outbound: dict[float, set[float]] = {}
    for r in pointer_fields:
        outbound.setdefault(r["file_number"], set()).add(r["pointer_file"])

    console.print(f"\nPointer fields: [bold]{len(pointer_fields):,}[/bold]")
    console.print(f"Unique targets:  [bold]{len(inbound):,}[/bold] files referenced by pointers")

    dd = DataDictionary(conn)
    console.print("\n[bold]Top 30 hub files (most-referenced):[/bold]")
    for tgt, srcs in sorted(inbound.items(), key=lambda x: -len(x[1]))[:30]:
        fd = dd.get_file(tgt)
        label = fd.label if fd else "?"
        console.print(
            f"  File {tgt:8.2f}  {label:40s}  ← referenced by {len(srcs):3d} files"
        )

    console.print("\n[bold]Top 20 files by outbound pointer count (most FK-rich):[/bold]")
    for file_num, targets in sorted(outbound.items(), key=lambda x: -len(x[1]))[:20]:
        fd_label = next(
            (r["file_label"] for r in schema if r["file_number"] == file_num), "?"
        )
        pkg = next(
            (r["package"] for r in schema if r["file_number"] == file_num), "?"
        )
        console.print(
            f"  File {file_num:8.2f}  {fd_label:40s}  → {len(targets):3d} targets  [{pkg}]"
        )

    return pointer_fields, inbound, outbound


def analyze_variable_pointers(schema: list[dict]) -> None:
    """3.5 — Variable pointer fields (polymorphic FKs)."""
    variable_pointers = [r for r in schema if r["datatype_code"] == "V"]
    console.print(f"\nVariable pointer fields: [bold]{len(variable_pointers)}[/bold]")
    vp_by_file = collections.Counter(r["file_number"] for r in variable_pointers)
    for file_num, count in vp_by_file.most_common(10):
        label = next(
            (r["file_label"] for r in schema if r["file_number"] == file_num), "?"
        )
        console.print(f"  File {file_num:.2f}  {label:40s}  {count} variable pointer fields")


def analyze_multiples(schema: list[dict], conn: YdbConnection) -> None:
    """3.6 — MULTIPLE (sub-file) depth map."""
    multiple_fields = [r for r in schema if r["datatype_code"] == "M"]
    console.print(f"\nMULTIPLE fields (sub-files): [bold]{len(multiple_fields)}[/bold]")
    multiples_per_file = collections.Counter(r["file_number"] for r in multiple_fields)
    dd = DataDictionary(conn)
    console.print("[bold]Files with most MULTIPLE fields:[/bold]")
    for file_num, count in multiples_per_file.most_common(15):
        fd = dd.get_file(file_num)
        label = fd.label if fd else "?"
        console.print(f"  File {file_num:8.2f}  {label:40s}  {count} sub-files")


def export_pointer_graph(pointer_fields: list[dict]) -> None:
    edges = [
        {
            "from_file": r["file_number"],
            "from_label": r["file_label"],
            "from_pkg": r["package"],
            "field_num": r["field_number"],
            "field_label": r["field_label"],
            "to_file": r["pointer_file"],
        }
        for r in pointer_fields
    ]
    out = OUTPUT_DIR / "pointer_graph.json"
    out.write_text(json.dumps(edges, indent=2, default=str))
    console.print(f"Pointer graph: [bold]{len(edges):,}[/bold] edges written to [green]{out}[/green]")


def visualize_graph(
    schema: list[dict],
    pointer_fields: list[dict],
    inbound: dict[float, set],
    conn: YdbConnection,
) -> None:
    """Hub-file subgraph PNG."""
    fi = FileInventory(conn)
    fi.load()
    file_labels: dict[float, str] = {
        fr.file_number: f"#{fr.file_number:.0f}\n{fr.label[:18]}"
        for fr in fi.list_files()
    }

    G = nx.DiGraph()
    for r in pointer_fields:
        G.add_edge(r["file_number"], r["pointer_file"], field_label=r["field_label"])

    console.print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    hub_file_nums = {tgt for tgt, srcs in inbound.items() if len(srcs) >= 10}
    neighbors: set[float] = set()
    for h in hub_file_nums:
        neighbors.update(G.predecessors(h))
    sub_nodes = hub_file_nums | neighbors
    H = G.subgraph(sub_nodes).copy()

    sizes = [
        3000 + 500 * len(inbound.get(n, set())) if n in hub_file_nums else 600
        for n in H.nodes()
    ]
    colors = ["#d62728" if n in hub_file_nums else "#aec7e8" for n in H.nodes()]

    pos = nx.spring_layout(H, k=2.5, seed=42)
    fig, ax = plt.subplots(figsize=(20, 14))
    nx.draw_networkx_nodes(H, pos, node_size=sizes, node_color=colors, alpha=0.85, ax=ax)
    nx.draw_networkx_labels(
        H,
        pos,
        labels={n: file_labels.get(n, str(n)) for n in H.nodes()},
        font_size=6,
        ax=ax,
    )
    nx.draw_networkx_edges(
        H, pos, alpha=0.2, arrows=True, arrowsize=8, edge_color="gray", ax=ax
    )
    ax.set_title(
        "FileMan Pointer Graph — Hub Files (≥10 inbound) + Neighbors\n"
        "Red = hub file, Blue = source file",
        fontsize=12,
    )
    ax.axis("off")
    plt.tight_layout()
    out_path = OUTPUT_DIR / "phase3_pointer_graph.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Graph saved to [green]{out_path}[/green]")


def visualize_pkg_matrix(schema: list[dict], pointer_fields: list[dict]) -> None:
    """Package × package dependency matrix heatmap."""
    pkg_by_file = {r["file_number"]: r["package"] for r in schema}
    pkg_pairs: dict[tuple[str, str], int] = collections.Counter()
    for r in pointer_fields:
        src_pkg = pkg_by_file.get(r["file_number"], "(unpackaged)")
        tgt_pkg = pkg_by_file.get(r["pointer_file"], "(unpackaged)")
        if src_pkg != tgt_pkg:
            pkg_pairs[(src_pkg, tgt_pkg)] += 1

    all_pkgs = set(s for s, _ in pkg_pairs) | set(t for _, t in pkg_pairs)
    top_pkgs = [
        p
        for p, _ in collections.Counter(
            {
                p: sum(
                    v
                    for (s, t), v in pkg_pairs.items()
                    if s == p or t == p
                )
                for p in all_pkgs
            }
        ).most_common(15)
    ]

    matrix = pd.DataFrame(0, index=top_pkgs, columns=top_pkgs)
    for (src, tgt), cnt in pkg_pairs.items():
        if src in top_pkgs and tgt in top_pkgs:
            matrix.loc[src, tgt] += cnt

    fig, ax = plt.subplots(figsize=(14, 12))
    im = ax.imshow(matrix.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(top_pkgs)))
    ax.set_yticks(range(len(top_pkgs)))
    ax.set_xticklabels([p[:20] for p in top_pkgs], rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels([p[:20] for p in top_pkgs], fontsize=7)
    plt.colorbar(im, ax=ax, label="Cross-package pointer count")
    ax.set_title(
        "Cross-Package Pointer Dependency Matrix\n"
        "(row→column = 'row package points to column package')"
    )
    plt.tight_layout()
    out_path = OUTPUT_DIR / "phase3_pkg_matrix.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Package matrix saved to [green]{out_path}[/green]")


def export_dot(
    hub_file_nums: set[float],
    H: "nx.DiGraph",
    file_labels: dict[float, str],
) -> None:
    dot_lines = [
        "digraph vista_pointers {",
        "  rankdir=LR;",
        "  node [shape=box fontsize=9];",
    ]
    for n in hub_file_nums:
        lbl = file_labels.get(n, str(n)).replace("\n", " ")
        dot_lines.append(f'  "{n}" [label="{lbl}" style=filled fillcolor=salmon];')
    for u, v in H.edges():
        dot_lines.append(f'  "{u}" -> "{v}";')
    dot_lines.append("}")
    out = OUTPUT_DIR / "phase3_pointer_graph.dot"
    out.write_text("\n".join(dot_lines))
    console.print(
        f"DOT file written to [green]{out}[/green]\n"
        "  Render with: dot -Tsvg phase3_pointer_graph.dot -o graph.svg"
    )


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 3 — Structural Topology")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        schema = build_schema(conn)
        pointer_fields, inbound, outbound = analyze_pointers(schema, conn)
        analyze_variable_pointers(schema)
        analyze_multiples(schema, conn)
        export_pointer_graph(pointer_fields)
        visualize_graph(schema, pointer_fields, inbound, conn)
        visualize_pkg_matrix(schema, pointer_fields)

    console.rule("[bold green]Phase 3 complete")


if __name__ == "__main__":
    main()
