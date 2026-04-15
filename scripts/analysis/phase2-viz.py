"""
Phase 2 — Volume Survey (Visualization)
========================================
Consumes data files produced by phase2-volume.py and renders static PNG
visualizations. No database connection required.

Inputs (from <repo>/output/phase2/):
    summary.json               — tier counts + top-50 files (primary input)
    file_volume.csv            — (fallback: recomputes top-50 if summary missing)

Outputs:
    phase2_volume.png          — top-50 bar chart with tier colors + legend

Run (host or container — no DB needed):
    python scripts/analysis/phase2-viz.py
"""

import csv
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

DATA_DIR = Path(__file__).resolve().parents[2] / "output" / "phase2"

TIER_COLORS = {
    "massive": "#d62728",
    "large":   "#ff7f0e",
    "medium":  "#2ca02c",
    "small":   "#1f77b4",
    "tiny":    "#aec7e8",
    "empty":   "#cccccc",
}


def load_summary() -> dict | None:
    path = DATA_DIR / "summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_top_from_csv(n: int = 50) -> list[dict]:
    path = DATA_DIR / "file_volume.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Neither summary.json nor file_volume.csv found in {DATA_DIR}. "
            "Run phase2-volume.py first."
        )
    with path.open() as f:
        rows = [
            {
                "file_number": float(r["file_number"]),
                "label": r["label"],
                "entry_count": int(r["entry_count"]),
                "tier": r["tier"],
                "package": r.get("package", ""),
            }
            for r in csv.DictReader(f)
        ]
    rows.sort(key=lambda r: -r["entry_count"])
    return rows[:n]


def plot_top_n(rows: list[dict], total_files: int, out_path: Path) -> None:
    rows = [r for r in rows if r["entry_count"] > 0]
    if not rows:
        console.print("[yellow]No files with data — nothing to plot.[/yellow]")
        return

    labels = [f"{r['label'][:35]} (#{r['file_number']:g})" for r in reversed(rows)]
    counts = [r["entry_count"] for r in reversed(rows)]
    colors = [TIER_COLORS.get(r["tier"], "#888888") for r in reversed(rows)]

    fig, ax = plt.subplots(figsize=(12, max(10, len(rows) * 0.28)))
    ax.barh(labels, counts, color=colors, log=True)
    ax.set_xlabel("Entry count (log scale)")
    ax.set_title(
        f"Top {len(rows)} FileMan Files by Entry Count\n"
        f"({len(rows)} files shown of {total_files:,} total)"
    )
    ax.tick_params(axis="y", labelsize=7)

    patches = [mpatches.Patch(color=v, label=k) for k, v in TIER_COLORS.items()]
    ax.legend(handles=patches, loc="lower right", fontsize=8)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 2 — Visualization")

    summary = load_summary()
    if summary:
        rows = summary["top_50_files"]
        total_files = summary["total_files"]
    else:
        console.print("[dim]summary.json missing — reading file_volume.csv[/dim]")
        rows = load_top_from_csv(50)
        total_files = len(rows)

    out_path = DATA_DIR / "phase2_volume.png"
    plot_top_n(rows, total_files, out_path)
    console.print(f"  [green]wrote[/green] {out_path}")
    console.rule("[bold green]Phase 2 visualization complete")


if __name__ == "__main__":
    main()
