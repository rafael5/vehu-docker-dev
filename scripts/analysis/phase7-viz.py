"""
Phase 7 — Normalization Candidates (Visualization)
====================================================
Consumes data files from phase7-candidates.py. No DB connection required.

Inputs (from ~/data/vista-fm-browser/phase7/):
    normalization_candidates.json
    summary.json

Outputs:
    phase7_candidates.png  — bar chart (by rule) + scatter (priority vs occurrences)
"""

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

DATA_DIR = Path("~/data/vista-fm-browser/phase7/").expanduser()

RULE_COLORS = {
    "label_type_conflict": "#d62728",
    "hub_file_reference": "#ff7f0e",
    "date_as_free_text": "#9467bd",
    "pointer_to_empty_file": "#1f77b4",
}


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 7 — Visualization")

    cands_path = DATA_DIR / "normalization_candidates.json"
    if not cands_path.exists():
        raise FileNotFoundError(f"{cands_path} not found — run phase7-candidates.py first.")
    candidates = json.loads(cands_path.read_text())
    if not candidates:
        console.print("[yellow]No candidates — nothing to plot.[/yellow]")
        return

    df = pd.DataFrame(candidates)
    rule_counts = df["rule"].value_counts()

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    ax = axes[0]
    colors = [RULE_COLORS.get(r, "gray") for r in rule_counts.index]
    bars = ax.bar(rule_counts.index, rule_counts.values, color=colors)
    ax.bar_label(bars, padding=3)
    ax.set_xlabel("Rule")
    ax.set_ylabel("Candidate count")
    ax.set_title("Normalization Candidates by Rule Type")
    ax.tick_params(axis="x", rotation=20, labelsize=8)

    ax2 = axes[1]
    for rule, grp in df.groupby("rule"):
        if "occurrences" in grp.columns:
            x = grp["occurrences"].fillna(grp["priority"])
        else:
            x = grp["priority"]
        y = grp["priority"]
        ax2.scatter(x, y, label=rule, alpha=0.6, color=RULE_COLORS.get(rule, "gray"), s=40)
    ax2.set_xlabel("Occurrences (field count or source file count)")
    ax2.set_ylabel("Priority score")
    ax2.set_title("Normalization Candidates — Priority vs Occurrences")
    ax2.legend(fontsize=8)

    plt.tight_layout()
    out = DATA_DIR / "phase7_candidates.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [green]wrote[/green] {out}")
    console.rule("[bold green]Phase 7 visualization complete")


if __name__ == "__main__":
    main()
