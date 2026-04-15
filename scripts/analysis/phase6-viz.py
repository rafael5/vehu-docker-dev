"""
Phase 6 — Data Coverage (Visualization)
========================================
Consumes summary.json from phase6-coverage.py. No DB connection required.

Inputs (from ~/data/vista-fm-browser/phase6/):
    summary.json

Outputs:
    phase6_coverage_<file_num>.png
"""

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

DATA_DIR = Path("~/data/vista-fm-browser/phase6/").expanduser()


def cov_color(pct: float) -> str:
    if pct >= 80:
        return "#2ca02c"
    if pct >= 20:
        return "#ff7f0e"
    return "#d62728"


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 6 — Visualization")

    path = DATA_DIR / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run phase6-coverage.py first.")
    summary = json.loads(path.read_text())

    fields = summary.get("fields", [])
    if not fields or summary.get("sample_size", 0) == 0:
        console.print("[yellow]No coverage data — nothing to plot.[/yellow]")
        return

    file_num = summary["file_number"]
    file_label = summary["file_label"]
    n = summary["sample_size"]

    rows_sorted = sorted(fields, key=lambda r: r["pct"])
    labels = [
        f"{r['field']:.4f} {r['label'][:28]} ({r['type_name'][:3]})"
        for r in rows_sorted
    ]
    pcts = [r["pct"] for r in rows_sorted]
    colors = [cov_color(p) for p in pcts]

    fig, ax = plt.subplots(figsize=(11, max(8, len(labels) * 0.22)))
    ax.barh(labels, pcts, color=colors)
    ax.set_xlim(0, 105)
    ax.set_xlabel("% of sampled entries where field is populated")
    ax.set_title(
        f"Field Coverage — {file_label} (File #{file_num})\n"
        f"n={n} sampled entries  |  Green ≥80%, Orange 20–80%, Red <20%"
    )
    ax.tick_params(axis="y", labelsize=7)
    ax.axvline(x=80, color="green", linestyle="--", alpha=0.4, linewidth=0.8)
    ax.axvline(x=20, color="orange", linestyle="--", alpha=0.4, linewidth=0.8)
    plt.tight_layout()

    tag = f"{int(file_num)}" if file_num == int(file_num) else f"{file_num:.4g}"
    out = DATA_DIR / f"phase6_coverage_{tag}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [green]wrote[/green] {out}")
    console.rule("[bold green]Phase 6 visualization complete")


if __name__ == "__main__":
    main()
