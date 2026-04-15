"""
Phase 3 — Structural Topology (Visualization)
==============================================
Consumes data files produced by phase3-topology.py and renders static PNG
visualizations + a Graphviz DOT file. No database connection required.

Inputs (from ~/data/vista-fm-browser/phase3/):
    pointer_graph.json      — edge list (from_file, to_file, labels, pkg)
    summary.json            — topology stats + hub list + package matrix

Outputs:
    phase3_pointer_graph.png  — hub subgraph (hubs + neighbors)
    phase3_pointer_graph.dot  — Graphviz source (render: dot -Tsvg file.dot -o x.svg)
    phase3_pkg_matrix.png     — cross-package dependency heatmap

Run (host or container — no DB needed):
    python scripts/analysis/phase3-viz.py
"""

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

DATA_DIR = Path("~/data/vista-fm-browser/phase3/").expanduser()


def load_inputs() -> tuple[list[dict], dict]:
    edges_path = DATA_DIR / "pointer_graph.json"
    summary_path = DATA_DIR / "summary.json"
    if not edges_path.exists() or not summary_path.exists():
        raise FileNotFoundError(
            f"Missing inputs in {DATA_DIR} — run phase3-topology.py first."
        )
    return json.loads(edges_path.read_text()), json.loads(summary_path.read_text())


def plot_hub_subgraph(edges: list[dict], summary: dict, out_path: Path) -> nx.DiGraph:
    G = nx.DiGraph()
    labels: dict[float, str] = {}
    for e in edges:
        G.add_edge(e["from_file"], e["to_file"], field_label=e["field_label"])
        labels[e["from_file"]] = e["from_label"]
        labels[e["to_file"]] = e["to_label"]

    hub_nums = {h["file_number"] for h in summary["top_hubs"]}
    neighbors: set[float] = set()
    for h in hub_nums:
        if h in G:
            neighbors.update(G.predecessors(h))
    H = G.subgraph(hub_nums | neighbors).copy()

    inbound_map = {h["file_number"]: h["inbound_count"] for h in summary["top_hubs"]}
    sizes = [
        3000 + 500 * inbound_map.get(n, 0) if n in hub_nums else 600
        for n in H.nodes()
    ]
    colors = ["#d62728" if n in hub_nums else "#aec7e8" for n in H.nodes()]
    node_labels = {n: f"#{n:.0f}\n{labels.get(n, '')[:18]}" for n in H.nodes()}

    pos = nx.spring_layout(H, k=2.5, seed=42)
    fig, ax = plt.subplots(figsize=(20, 14))
    nx.draw_networkx_nodes(H, pos, node_size=sizes, node_color=colors, alpha=0.85, ax=ax)
    nx.draw_networkx_labels(H, pos, labels=node_labels, font_size=6, ax=ax)
    nx.draw_networkx_edges(H, pos, alpha=0.2, arrows=True, arrowsize=8,
                           edge_color="gray", ax=ax)
    ax.set_title(
        "FileMan Pointer Graph — Hub Files (≥10 inbound) + Neighbors\n"
        "Red = hub file, Blue = source file",
        fontsize=12,
    )
    ax.axis("off")
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return H


def write_dot(H: nx.DiGraph, summary: dict, out_path: Path) -> None:
    hub_nums = {h["file_number"] for h in summary["top_hubs"]}
    labels = {n: "" for n in H.nodes()}
    for h in summary["top_hubs"]:
        labels[h["file_number"]] = h["label"]

    lines = [
        "digraph vista_pointers {",
        "  rankdir=LR;",
        "  node [shape=box fontsize=9];",
    ]
    for n in hub_nums:
        lbl = labels.get(n, str(n)).replace('"', "'")
        lines.append(f'  "{n}" [label="#{n:g}\\n{lbl}" style=filled fillcolor=salmon];')
    for u, v in H.edges():
        lines.append(f'  "{u}" -> "{v}";')
    lines.append("}")
    out_path.write_text("\n".join(lines))


def plot_package_matrix(summary: dict, out_path: Path) -> None:
    pm = summary.get("package_matrix", {})
    pkgs = pm.get("top_packages", [])
    if not pkgs:
        console.print("[yellow]No package_matrix in summary — skipping heatmap.[/yellow]")
        return
    rows = pm["matrix"]
    data = [[row[p] for p in pkgs] for row in rows]

    fig, ax = plt.subplots(figsize=(14, 12))
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(pkgs)))
    ax.set_yticks(range(len(pkgs)))
    ax.set_xticklabels([p[:20] for p in pkgs], rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels([p[:20] for p in pkgs], fontsize=7)
    plt.colorbar(im, ax=ax, label="Cross-package pointer count")
    ax.set_title(
        "Cross-Package Pointer Dependency Matrix\n"
        "(row→column = row package points to column package)"
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 3 — Visualization")

    edges, summary = load_inputs()
    console.print(
        f"Loaded {len(edges):,} pointer edges, "
        f"{len(summary.get('top_hubs', []))} hubs"
    )

    graph_png = DATA_DIR / "phase3_pointer_graph.png"
    dot_path = DATA_DIR / "phase3_pointer_graph.dot"
    matrix_png = DATA_DIR / "phase3_pkg_matrix.png"

    H = plot_hub_subgraph(edges, summary, graph_png)
    console.print(f"  [green]wrote[/green] {graph_png}")
    write_dot(H, summary, dot_path)
    console.print(f"  [green]wrote[/green] {dot_path}")
    plot_package_matrix(summary, matrix_png)
    console.print(f"  [green]wrote[/green] {matrix_png}")

    console.rule("[bold green]Phase 3 visualization complete")


if __name__ == "__main__":
    main()
