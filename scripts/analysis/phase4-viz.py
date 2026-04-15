"""
Phase 4 — Data Variety and Naming (Visualization)
===================================================
Consumes data files produced by phase4-variety.py. No DB connection required.

Inputs (from ~/data/vista-fm-browser/phase4/):
    summary.json

Outputs:
    phase4_label_frequency.png
    phase4_label_type_heatmap.png
    phase4_set_similarity.png
"""

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

DATA_DIR = Path("~/data/vista-fm-browser/phase4/").expanduser()


def plot_label_frequency(summary: dict, out_path: Path) -> None:
    top = summary["top_labels"][:40]
    names = [lbl for lbl, _ in reversed(top)]
    counts = [c for _, c in reversed(top)]
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.barh(names, counts, color="steelblue")
    ax.set_xlabel("Number of fields with this label")
    ax.set_title("Top 40 Field Labels — Shared Vocabulary Across VistA Packages")
    ax.tick_params(axis="y", labelsize=8)
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_label_type_heatmap(summary: dict, out_path: Path) -> None:
    incon = summary["top_inconsistencies"][:30]
    if not incon:
        return
    all_types = ["F", "P", "S", "D", "N", "M", "W", "C", "K", "V"]
    rows = []
    for item in incon:
        total = item["occurrences"]
        rows.append([item["types"].get(t, 0) / total for t in all_types])
    mat = np.array(rows)
    ylabels = [item["label"][:35] for item in incon]

    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(mat, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(all_types)))
    ax.set_yticks(range(len(ylabels)))
    ax.set_xticklabels(all_types, fontsize=9)
    ax.set_yticklabels(ylabels, fontsize=7)
    plt.colorbar(im, ax=ax, label="Fraction with this type")
    ax.set_title(
        "Label-Type Inconsistency — Same Label, Different Types\n"
        "(mixed row = inconsistent)"
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_set_similarity(summary: dict, out_path: Path) -> None:
    sets = summary["top_shared_sets"][:30]
    if len(sets) < 2:
        return
    keys = [frozenset((k, v) for k, v in s["codes"].items()) for s in sets]
    n = len(keys)
    sim = np.zeros((n, n))
    for i, ki in enumerate(keys):
        for j, kj in enumerate(keys):
            if i == j:
                sim[i, j] = 1.0
            else:
                inter = len(ki & kj)
                union = len(ki | kj)
                sim[i, j] = inter / union if union else 0

    labels = [
        ", ".join(f"{k}={v}" for k, v in list(s["codes"].items())[:2])[:25]
        for s in sets
    ]
    fig, ax = plt.subplots(figsize=(12, 11))
    im = ax.imshow(sim, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=6)
    ax.set_yticklabels(labels, fontsize=6)
    plt.colorbar(im, ax=ax, label="Jaccard similarity")
    ax.set_title(
        "SET Value Set Similarity (top 30 most-used)\n"
        "1.0 = identical value sets used under different labels"
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 4 — Visualization")

    summary_path = DATA_DIR / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"{summary_path} not found — run phase4-variety.py first."
        )
    summary = json.loads(summary_path.read_text())

    for fname, fn in [
        ("phase4_label_frequency.png", plot_label_frequency),
        ("phase4_label_type_heatmap.png", plot_label_type_heatmap),
        ("phase4_set_similarity.png", plot_set_similarity),
    ]:
        out = DATA_DIR / fname
        fn(summary, out)
        console.print(f"  [green]wrote[/green] {out}")

    console.rule("[bold green]Phase 4 visualization complete")


if __name__ == "__main__":
    main()
