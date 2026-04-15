"""
Phase 8 — Rollup (Visualization)
=================================
Consumes summary.json from phase8-rollup.py and produces a single-page
summary-dashboard PNG. No DB connection required.

Inputs (from ~/data/vista-fm-browser/phase8/):
    summary.json

Outputs:
    phase8_dashboard.png   — 4-panel summary dashboard
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

DATA_DIR = Path("~/data/vista-fm-browser/phase8/").expanduser()


def plot_dashboard(rollup: dict, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Panel 1: volume tiers
    ax = axes[0, 0]
    tiers = ["massive", "large", "medium", "small", "tiny", "empty"]
    colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4", "#aec7e8", "#cccccc"]
    counts = [rollup["volume"]["tier_counts"].get(t, 0) for t in tiers]
    bars = ax.bar(tiers, counts, color=colors)
    ax.bar_label(bars, padding=3)
    ax.set_title("Volume Tiers (files per tier)")
    ax.set_ylabel("Files")

    # Panel 2: normalization rules
    ax = axes[0, 1]
    rule_colors = {
        "label_type_conflict": "#d62728",
        "hub_file_reference": "#ff7f0e",
        "date_as_free_text": "#9467bd",
        "pointer_to_empty_file": "#1f77b4",
    }
    by_rule = rollup["normalization"].get("by_rule", {})
    if by_rule:
        rules, vals = zip(*sorted(by_rule.items(), key=lambda x: -x[1]))
        bars = ax.bar(rules, vals, color=[rule_colors.get(r, "gray") for r in rules])
        ax.bar_label(bars, padding=3)
        ax.tick_params(axis="x", rotation=20, labelsize=8)
    ax.set_title(f"Normalization Candidates by Rule ({rollup['normalization']['total_candidates']} total)")

    # Panel 3: top hubs
    ax = axes[1, 0]
    hubs = rollup["topology"]["top_hubs"][:10]
    if hubs:
        names = [f"#{h.get('file_number', 0):.10g} {h.get('label', '?')[:20]}" for h in reversed(hubs)]
        ibc = [h.get("inbound_count", 0) for h in reversed(hubs)]
        bars = ax.barh(names, ibc, color="steelblue")
        ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_title("Top 10 Hub Files (inbound pointer count)")
    ax.tick_params(axis="y", labelsize=8)

    # Panel 4: scope summary text
    ax = axes[1, 1]
    ax.axis("off")
    s = rollup["scope"]
    t = rollup["topology"]
    va = rollup["variety"]
    n = rollup["normalization"]
    text = (
        f"Scope\n"
        f"  Files: {s['total_files']:,}\n"
        f"  Packages: {s['total_packages']:,}\n"
        f"  Fields: {s['total_fields']:,}\n"
        f"  Files with data: {s['files_with_data']:,}\n"
        f"  Total entries: {s['total_entries']:,}\n\n"
        f"Topology\n"
        f"  Pointer edges: {t['total_pointer_edges']:,}\n"
        f"  Hubs (≥10): {t['hub_files_10plus']:,}\n"
        f"  Variable pointers: {t['variable_pointer_fields']:,}\n"
        f"  MULTIPLE: {t['multiple_fields']:,}\n\n"
        f"Variety\n"
        f"  Unique labels: {va['unique_labels']:,}\n"
        f"  Shared value sets: {va['shared_sets_count']:,}\n"
        f"  Label-type conflicts: {va['label_type_inconsistencies']:,}\n\n"
        f"Normalization\n"
        f"  Total candidates: {n['total_candidates']:,}\n"
        f"  Max priority: {n['priority_max']}\n"
    )
    ax.text(0.02, 0.98, text, fontsize=11, verticalalignment="top",
            fontfamily="monospace")
    ax.set_title("Summary", fontsize=12, loc="left")

    fig.suptitle("VistA FileMan — Normalization Rollup", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 8 — Visualization")

    path = DATA_DIR / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run phase8-rollup.py first.")
    rollup = json.loads(path.read_text())

    out = DATA_DIR / "phase8_dashboard.png"
    plot_dashboard(rollup, out)
    console.print(f"  [green]wrote[/green] {out}")
    console.rule("[bold green]Phase 8 visualization complete")


if __name__ == "__main__":
    main()
