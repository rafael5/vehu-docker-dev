"""
Phase 5 — Schema Deep Dive (Visualization)
===========================================
Consumes summary.json from phase5-deep-dive.py and produces a field
documentation completeness heatmap for the most recently analysed file.
No DB connection required.

Inputs (from ~/data/vista-fm-browser/phase5/):
    summary.json   — last-analysed file's stats + full field list

Outputs:
    phase5_schema_<file_num>.png
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

DATA_DIR = Path("~/data/vista-fm-browser/phase5/").expanduser()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 5 — Visualization")

    path = DATA_DIR / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run phase5-deep-dive.py first.")
    summary = json.loads(path.read_text())

    fields = summary.get("fields", [])
    if not fields:
        console.print("[yellow]No fields in summary — nothing to plot.[/yellow]")
        return

    file_num = summary.get("file_number")
    file_label = summary.get("file_label", "")

    def has(r, k): return 1.0 if r.get(k) else 0.0

    mat = np.array([[
        has(r, "has_description"),
        has(r, "has_input_transform"),
        1.0 if r.get("set_values") else 0.0,
        1.0 if r.get("last_edited") else 0.0,
        1.0 if r.get("help_prompt") else 0.0,
    ] for r in fields], dtype=float)

    attr_labels = ["Description", "Input Transform", "Set Values", "Last Edited", "Help Prompt"]
    field_names = [f"{r['field']:.4f} {r['label'][:30]}" for r in fields]

    fig, ax = plt.subplots(figsize=(10, max(6, len(field_names) * 0.22)))
    im = ax.imshow(mat, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(attr_labels)))
    ax.set_yticks(range(len(field_names)))
    ax.set_xticklabels(attr_labels, fontsize=9)
    ax.set_yticklabels(field_names, fontsize=6)
    plt.colorbar(im, ax=ax, label="Present (1) / Absent (0)", shrink=0.4)
    ax.set_title(
        f"Field Documentation Completeness — {file_label} (File #{file_num})\n"
        "Green = present, Red = missing"
    )
    plt.tight_layout()
    tag = f"{int(file_num)}" if file_num == int(file_num) else f"{file_num:.4g}"
    out = DATA_DIR / f"phase5_schema_{tag}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [green]wrote[/green] {out}")
    console.rule("[bold green]Phase 5 visualization complete")


if __name__ == "__main__":
    main()
