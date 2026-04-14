"""
Phase 2 — Volume Survey
=======================
Goal: Find out where the actual data lives. Separates heavyweight clinical
files from small configuration files by entry count.

Prerequisite: phase1_scope.py must have run (inventory.json needed for
package lookup). Or run standalone — it loads inventory internally.

Outputs:
    ~/data/vista-fm-browser/output/file_volume.json
    ~/data/vista-fm-browser/output/file_volume.csv
    ~/data/vista-fm-browser/output/phase2_volume.png

Run inside the VEHU container:
    python scripts/analysis/phase2_volume.py
"""

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()

TIER_COLORS = {
    "massive": "#d62728",
    "large": "#ff7f0e",
    "medium": "#2ca02c",
    "small": "#1f77b4",
    "tiny": "#aec7e8",
}


def tier_label(count: int) -> str:
    if count >= 100_000:
        return "massive"
    if count >= 10_000:
        return "large"
    if count >= 1_000:
        return "medium"
    if count >= 100:
        return "small"
    return "tiny"


def tier_color(count: int) -> str:
    return TIER_COLORS[tier_label(count)]


def collect_volume(conn: YdbConnection) -> tuple[list, dict]:
    """
    Count entries for every file. Returns (volume, tiers).

    volume: sorted list of (count, file_number, label) descending
    tiers: dict mapping tier name -> list of (file_number, label[, count])
    """
    reader = FileReader(conn, DataDictionary(conn))
    fi = FileInventory(conn)
    fi.load()

    console.print("\n[bold]Counting entries for all files...[/bold] (this takes a few minutes)")
    volume: list[tuple[int, float, str]] = []
    for fr in fi.list_files():
        count = reader.count_entries(fr.file_number)
        if count > 0:
            volume.append((count, fr.file_number, fr.label))

    volume.sort(reverse=True)
    console.print(f"Files with data: [bold]{len(volume)}[/bold] of {len(fi.list_files())}")

    tiers: dict[str, list] = {
        "massive (>100K entries)": [],
        "large (10K–100K)": [],
        "medium (1K–10K)": [],
        "small (100–1K)": [],
        "tiny (<100)": [],
        "empty (0)": [],
    }
    for count, num, label in volume:
        if count >= 100_000:
            tiers["massive (>100K entries)"].append((num, label, count))
        elif count >= 10_000:
            tiers["large (10K–100K)"].append((num, label, count))
        elif count >= 1_000:
            tiers["medium (1K–10K)"].append((num, label, count))
        elif count >= 100:
            tiers["small (100–1K)"].append((num, label, count))
        else:
            tiers["tiny (<100)"].append((num, label, count))

    console.print("\n[bold]Volume tiers:[/bold]")
    for tier, files in tiers.items():
        console.print(f"  {tier}: {len(files)} files")

    console.print("\n[bold]Top 40 files by entry count:[/bold]")
    file_map = {fr.file_number: fr.package_name or "?" for fr in fi.list_files()}
    for count, num, label in volume[:40]:
        pkg = file_map.get(num, "?")
        console.print(f"  {num:8.2f}  {label:40s}  {count:>10,}  [{pkg}]")

    return volume, tiers


def export_volume(volume: list) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    out_json = OUTPUT_DIR / "file_volume.json"
    out_json.write_text(
        json.dumps(
            [{"file_number": n, "label": l, "entry_count": c} for c, n, l in volume],
            indent=2,
        )
    )
    console.print(f"Volume JSON written to [green]{out_json}[/green]")

    # CSV via pandas
    rows = []
    for count, num, label in volume:
        rows.append(
            {
                "file_number": num,
                "label": label,
                "entry_count": count,
                "tier": tier_label(count),
            }
        )
    df = pd.DataFrame(rows)
    out_csv = OUTPUT_DIR / "file_volume.csv"
    df.to_csv(out_csv, index=False)
    console.print(f"Volume CSV written to [green]{out_csv}[/green]")

    console.print("\n[bold]Tier summary:[/bold]")
    console.print(df.groupby("tier")["file_number"].count().rename("files").to_string())


def visualize(volume: list, tiers: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    top50 = [(count, num, label) for count, num, label in volume if count > 0][:50]
    labels_plot = [f"{label[:35]} (#{num:.0f})" for _, num, label in reversed(top50)]
    counts_plot = [count for count, _, _ in reversed(top50)]
    colors = [tier_color(c) for c in counts_plot]

    empty_count = len(tiers.get("empty (0)", []))
    total_count = sum(len(v) for v in tiers.values())

    fig, ax = plt.subplots(figsize=(12, max(10, len(top50) * 0.28)))
    ax.barh(labels_plot, counts_plot, color=colors, log=True)
    ax.set_xlabel("Entry count (log scale)")
    ax.set_title(
        f"Top {len(top50)} FileMan Files by Entry Count\n"
        f"({len(volume)} files with data of {total_count + empty_count} total)"
    )
    ax.tick_params(axis="y", labelsize=7)

    patches = [mpatches.Patch(color=v, label=k) for k, v in TIER_COLORS.items()]
    ax.legend(handles=patches, loc="lower right", fontsize=8)

    plt.tight_layout()
    out_path = OUTPUT_DIR / "phase2_volume.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Chart saved to [green]{out_path}[/green]")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 2 — Volume Survey")

    with YdbConnection.connect() as conn:
        volume, tiers = collect_volume(conn)

    export_volume(volume)
    visualize(volume, tiers)

    console.rule("[bold green]Phase 2 complete")


if __name__ == "__main__":
    main()
