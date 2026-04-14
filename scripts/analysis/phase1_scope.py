"""
Phase 1 — Scope Survey
======================
Goal: Know the total size of the problem in five numbers before touching any field.

Outputs:
    ~/data/vista-fm-browser/output/inventory.json
    ~/data/vista-fm-browser/output/phase1_scope.png

Run inside the VEHU container:
    python scripts/analysis/phase1_scope.py

Requires: source /usr/local/etc/ydb_env_set (YottaDB environment active)
"""

import collections
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()


def section_10_file_registry(conn: YdbConnection) -> None:
    """1.0 — Inspect File #1 (the file registry itself)."""
    dd = DataDictionary(conn)
    fd1 = dd.get_file(1)
    if fd1 is None:
        console.print("[red]File #1 not found[/red]")
        return
    console.print(
        f"\n[bold]File #1:[/bold] {fd1.label}  global=^DIC  fields={fd1.field_count}"
    )
    for field_num, fld in sorted(fd1.fields.items()):
        ptr = f" → File #{fld.pointer_file}" if fld.pointer_file else ""
        console.print(f"  {field_num:7.4f}  {fld.label:30s}  {fld.datatype_name}{ptr}")

    reader = FileReader(conn, dd)
    total = reader.count_entries(1)
    console.print(f"\nFile #1 has [bold]{total}[/bold] entries (registered FileMan files)")


def section_11_package_counts(conn: YdbConnection) -> tuple[FileInventory, dict]:
    """1.1 — Package and file counts. Returns (fi, summary_dict)."""
    fi = FileInventory(conn)
    fi.load()
    s = fi.summary()

    console.print(f"\n[bold]Scope Summary[/bold]")
    console.print(f"  Files total:      {s['total_files']}")
    console.print(f"  Packages total:   {s['total_packages']}")
    console.print(f"  Unpackaged files: {s['unpackaged_files']}")

    grouped = fi.files_by_package()
    by_count = sorted(
        ((k, len(v)) for k, v in grouped.items() if k != "(unpackaged)"),
        key=lambda x: -x[1],
    )
    console.print("\n[bold]Top 20 packages by file count:[/bold]")
    for name, count in by_count[:20]:
        console.print(f"  {name:45s} {count:4d} files")

    return fi, s


def section_12_field_counts(conn: YdbConnection) -> int:
    """1.2 — Total field count across all files."""
    dd = DataDictionary(conn)
    all_files = dd.list_files()
    total_fields = 0
    for file_num, _label in all_files:
        fd = dd.get_file(file_num)
        if fd:
            total_fields += fd.field_count

    console.print(f"\n[bold]Field Counts[/bold]")
    console.print(f"  Total files:     {len(all_files)}")
    console.print(f"  Total fields:    {total_fields}")
    console.print(f"  Avg fields/file: {total_fields / max(len(all_files), 1):.1f}")
    return total_fields


def section_13_type_distribution(
    conn: YdbConnection,
) -> tuple[dict[str, int], dict[str, str]]:
    """1.3 — Field type distribution. Returns (type_counts, type_names)."""
    dd = DataDictionary(conn)
    type_counts: dict[str, int] = collections.Counter()
    type_names: dict[str, str] = {}
    for file_num, _label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for fld in fd.fields.values():
            type_counts[fld.datatype_code] += 1
            type_names[fld.datatype_code] = fld.datatype_name

    t = Table(title="Field Type Distribution", show_lines=False)
    t.add_column("Code", style="cyan", justify="center")
    t.add_column("Name", style="white")
    t.add_column("Count", style="yellow", justify="right")
    t.add_column("%", style="green", justify="right")
    total = sum(type_counts.values())
    for code, count in type_counts.most_common():
        pct = 100 * count / total
        t.add_row(code, type_names.get(code, ""), f"{count:,}", f"{pct:.1f}%")
    console.print(t)

    return type_counts, type_names


def section_14_export(conn: YdbConnection) -> Path:
    """1.4 — Export inventory JSON."""
    fi = FileInventory(conn)
    fi.load()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = fi.export_json(OUTPUT_DIR)
    console.print(f"\nInventory written to [green]{out}[/green]")
    return out


def visualize(
    fi: FileInventory,
    summary: dict,
    type_counts: dict[str, int],
    type_names: dict[str, str],
) -> None:
    """Save phase1_scope.png — package bar + type pie."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    top = summary.get("top_packages_by_file_count", [])[:20]
    names = [r["name"][:30] for r in reversed(top)]
    counts = [r["file_count"] for r in reversed(top)]

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    ax = axes[0]
    bars = ax.barh(names, counts, color="steelblue")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_xlabel("File count")
    ax.set_title(
        f"Top 20 VistA Packages by File Count\n"
        f"(total: {summary['total_files']} files, {summary['total_packages']} packages)"
    )
    ax.tick_params(axis="y", labelsize=8)

    ax2 = axes[1]
    labels = [
        f"{code}\n{type_names.get(code, '')} ({count:,})"
        for code, count in type_counts.most_common()
    ]
    sizes = [count for _, count in type_counts.most_common()]
    explode = [0.05] * len(sizes)
    ax2.pie(
        sizes,
        labels=labels,
        explode=explode,
        autopct="%1.1f%%",
        startangle=140,
        textprops={"fontsize": 8},
    )
    ax2.set_title("Field Type Distribution across All Files")

    plt.tight_layout()
    out_path = OUTPUT_DIR / "phase1_scope.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Chart saved to [green]{out_path}[/green]")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 1 — Scope Survey")

    with YdbConnection.connect() as conn:
        section_10_file_registry(conn)
        fi, summary = section_11_package_counts(conn)
        section_12_field_counts(conn)
        type_counts, type_names = section_13_type_distribution(conn)
        section_14_export(conn)

    visualize(fi, summary, type_counts, type_names)

    console.rule("[bold green]Phase 1 complete")


if __name__ == "__main__":
    main()
