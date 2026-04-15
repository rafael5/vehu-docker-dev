"""
Phase 1 — Scope Survey (Visualization)
=======================================
Consumes the data files produced by phase1-scope.py and renders
static PNG visualizations. No database connection required.

Inputs (from ~/data/vista-fm-browser/phase1/):
    summary.json            — scope stats + top packages + type distribution
    type_distribution.csv   — (alternative input, used if summary.json missing)
    packages.csv            — (alternative input for package bar chart)

Outputs:
    phase1_scope.png        — package bar chart + field-type pie

Future visualization formats (D3.js web, Plotly HTML, SVG) should read the
same data files and live as sibling viz scripts, e.g. phase1-scope-viz-d3.py.

Run (host or container — no DB needed):
    python scripts/analysis/phase1-viz.py
"""

import csv
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

DATA_DIR = Path("~/data/vista-fm-browser/phase1/").expanduser()


# ---------------------------------------------------------------------------
# Data loaders (JSON preferred, CSV fallback)
# ---------------------------------------------------------------------------


def load_summary() -> dict:
    path = DATA_DIR / "summary.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run phase1-scope.py first."
        )
    return json.loads(path.read_text())


def load_type_distribution_csv() -> list[dict]:
    path = DATA_DIR / "type_distribution.csv"
    if not path.exists():
        return []
    with path.open() as f:
        return [
            {"code": r["datatype_code"], "name": r["datatype_name"],
             "count": int(r["count"])}
            for r in csv.DictReader(f)
        ]


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def plot_package_bar(ax, summary: dict) -> None:
    top = summary["top_packages_by_file_count"][:20]
    names = [r["name"][:30] for r in reversed(top)]
    counts = [r["file_count"] for r in reversed(top)]
    bars = ax.barh(names, counts, color="steelblue")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_xlabel("File count")
    ax.set_title(
        f"Top 20 VistA Packages by File Count\n"
        f"(total: {summary['total_files']:,} files, "
        f"{summary['total_packages']:,} packages)"
    )
    ax.tick_params(axis="y", labelsize=8)


def plot_type_pie(ax, types: list[dict]) -> None:
    labels = [f"{t['code']}\n{t['name']} ({t['count']:,})" for t in types]
    sizes = [t["count"] for t in types]
    ax.pie(
        sizes,
        labels=labels,
        explode=[0.05] * len(sizes),
        autopct="%1.1f%%",
        startangle=140,
        textprops={"fontsize": 8},
    )
    ax.set_title("Field Type Distribution across All Files")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 1 — Visualization")

    summary = load_summary()
    types = summary.get("type_distribution") or load_type_distribution_csv()

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    plot_package_bar(axes[0], summary)
    plot_type_pie(axes[1], types)
    plt.tight_layout()

    out_path = DATA_DIR / "phase1_scope.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [green]wrote[/green] {out_path}")
    console.rule("[bold green]Phase 1 visualization complete")


if __name__ == "__main__":
    main()
