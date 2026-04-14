"""
Phase 4 — Data Variety and Naming Analysis
==========================================
Goal: Understand what values exist (SET-OF-CODES), how naming is used
consistently or inconsistently, and where the same concept appears under
different labels.

Prerequisites:
    phase3_topology.py — all_fields.json (schema cache, built automatically if missing)

Outputs:
    ~/data/vista-fm-browser/output/phase4_label_frequency.png
    ~/data/vista-fm-browser/output/phase4_label_type_heatmap.png
    ~/data/vista-fm-browser/output/phase4_set_similarity.png

Run inside the VEHU container:
    python scripts/analysis/phase4_variety.py
"""

import collections
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()


def load_schema(conn: YdbConnection) -> list[dict]:
    """Load all_fields.json if cached, otherwise build it."""
    cache = OUTPUT_DIR / "all_fields.json"
    if cache.exists():
        console.print(f"[dim]Loading cached schema from {cache}[/dim]")
        return json.loads(cache.read_text())

    console.print("\n[bold]Building full schema (reading all ^DD entries)...[/bold]")
    dd = DataDictionary(conn)
    fi = FileInventory(conn)
    fi.load()
    pkg_by_file = {
        fr.file_number: (fr.package_name or "(unpackaged)") for fr in fi.list_files()
    }
    schema: list[dict] = []
    for file_num, file_label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for field_num, fld in fd.fields.items():
            schema.append(
                {
                    "file_number": file_num,
                    "file_label": file_label,
                    "package": pkg_by_file.get(file_num, "(unpackaged)"),
                    "field_number": field_num,
                    "field_label": fld.label,
                    "datatype_code": fld.datatype_code,
                    "datatype_name": fld.datatype_name,
                    "pointer_file": fld.pointer_file,
                    "set_values": fld.set_values,
                }
            )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(schema, indent=2, default=str))
    console.print(f"Schema: {len(schema):,} fields — written to [green]{cache}[/green]")
    return schema


def canon_set(sv: dict) -> frozenset:
    return frozenset((k.strip().upper(), v.strip().upper()) for k, v in sv.items())


def section_41_set_inventory(schema: list[dict]) -> tuple[list, dict]:
    """4.1 — SET-OF-CODES inventory."""
    set_fields = [r for r in schema if r["datatype_code"] == "S" and r["set_values"]]
    console.print(f"\nSET-OF-CODES fields with defined values: [bold]{len(set_fields)}[/bold]")

    seen_sets: dict[frozenset, list[dict]] = {}
    for r in set_fields:
        key = canon_set(r["set_values"])
        seen_sets.setdefault(key, []).append(r)

    shared = [(key, grp) for key, grp in seen_sets.items() if len(grp) >= 5]
    shared.sort(key=lambda x: -len(x[1]))

    console.print(f"\nValue sets shared across ≥5 fields: [bold]{len(shared)}[/bold]")
    for key, group in shared[:15]:
        sample_codes = dict(list(key)[:4])
        console.print(f"\n  codes={sample_codes}")
        console.print(
            f"  used in {len(group)} fields across "
            f"{len(set(r['file_number'] for r in group))} files:"
        )
        for r in group[:4]:
            console.print(
                f"    File {r['file_number']:.2f} {r['file_label']:30s} · {r['field_label']}"
            )

    return shared, seen_sets


def section_42_boolean_patterns(seen_sets: dict) -> None:
    """4.2 — YES/NO and ACTIVE/INACTIVE patterns."""
    boolean_patterns = [
        frozenset({("Y", "YES"), ("N", "NO")}),
        frozenset({("1", "YES"), ("0", "NO")}),
        frozenset({("A", "ACTIVE"), ("I", "INACTIVE")}),
        frozenset({("1", "ACTIVE"), ("0", "INACTIVE")}),
    ]
    console.print("\n[bold]Boolean-equivalent SET patterns:[/bold]")
    for pattern in boolean_patterns:
        matches = seen_sets.get(pattern, [])
        if matches:
            codes = dict(list(pattern))
            console.print(
                f"  {codes}: {len(matches)} fields in "
                f"{len(set(r['file_number'] for r in matches))} files"
            )


def section_43_label_frequency(schema: list[dict]) -> dict[str, int]:
    """4.3 — Label frequency (shared vocabulary)."""
    label_counter = collections.Counter(
        r["field_label"].strip().upper() for r in schema
    )
    console.print("\n[bold]Top 40 field labels across all files:[/bold]")
    for label, count in label_counter.most_common(40):
        console.print(f"  {label:45s}  {count:5,}")
    return label_counter


def section_44_label_type_consistency(schema: list[dict]) -> list[dict]:
    """4.4 — Same label, different types."""
    label_groups: dict[str, list[dict]] = {}
    for r in schema:
        key = r["field_label"].strip().upper()
        label_groups.setdefault(key, []).append(r)

    inconsistent = []
    for label, rows in label_groups.items():
        if len(rows) < 5:
            continue
        types = set(r["datatype_code"] for r in rows)
        if len(types) > 1:
            type_dist = collections.Counter(r["datatype_code"] for r in rows)
            inconsistent.append(
                {
                    "label": label,
                    "occurrences": len(rows),
                    "types": dict(type_dist),
                    "files": len(set(r["file_number"] for r in rows)),
                }
            )

    inconsistent.sort(key=lambda x: -x["occurrences"])
    console.print(
        f"\nLabels with same name but inconsistent types (≥5 occurrences): "
        f"[bold]{len(inconsistent)}[/bold]"
    )
    for item in inconsistent[:20]:
        console.print(
            f"  {item['label']:40s}  in {item['occurrences']:4d} fields  "
            f"types={item['types']}"
        )
    return inconsistent


def section_45_canonical_positions(schema: list[dict]) -> None:
    """4.5 — Canonical field positions."""
    canonical_positions = {
        0.01: "PRIMARY NAME/IDENTIFIER",
        0.02: "CATEGORY/TYPE",
        0.03: "PARENT REFERENCE or DATE",
        0.05: "SEX or SECONDARY IDENTIFIER",
        0.07: "STATUS",
        0.09: "SSN or UNIQUE ID",
        1.0: "SECONDARY CONTENT or ADDRESS",
        99.0: "CLASS/CATEGORY",
    }
    console.print("\n[bold]Canonical field position analysis:[/bold]")
    for pos, concept in canonical_positions.items():
        hits = [r for r in schema if abs(r["field_number"] - pos) < 0.001]
        if not hits:
            continue
        type_dist = collections.Counter(r["datatype_code"] for r in hits)
        top_labels = collections.Counter(r["field_label"].upper() for r in hits)
        console.print(f"\n  Field {pos:.2f}  ({concept}):  {len(hits)} definitions")
        console.print(f"    Types:  {dict(type_dist.most_common(4))}")
        console.print(f"    Labels: {dict(top_labels.most_common(5))}")


def visualize(
    label_counter: dict[str, int],
    inconsistent: list[dict],
    shared: list,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Chart 1: top 40 field label frequencies
    top_labels_list = label_counter.most_common(40)
    lnames = [lbl for lbl, _ in reversed(top_labels_list)]
    lcounts = [c for _, c in reversed(top_labels_list)]

    fig, ax = plt.subplots(figsize=(10, 12))
    ax.barh(lnames, lcounts, color="steelblue")
    ax.set_xlabel("Number of fields with this label (across all files)")
    ax.set_title("Top 40 Field Labels — Shared Vocabulary Across VistA Packages")
    ax.tick_params(axis="y", labelsize=8)
    plt.tight_layout()
    out1 = OUTPUT_DIR / "phase4_label_frequency.png"
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Label frequency chart saved to [green]{out1}[/green]")

    # Chart 2: label-type inconsistency heatmap
    all_types = ["F", "P", "S", "D", "N", "M", "W", "C", "K", "V"]
    top_incon = sorted(inconsistent, key=lambda x: -x["occurrences"])[:30]
    rows_data = []
    for item in top_incon:
        total = item["occurrences"]
        row = [item["types"].get(t, 0) / total for t in all_types]
        rows_data.append(row)

    if rows_data:
        mat = np.array(rows_data)
        ylabels = [item["label"][:35] for item in top_incon]
        fig2, ax2 = plt.subplots(figsize=(12, 10))
        im = ax2.imshow(mat, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
        ax2.set_xticks(range(len(all_types)))
        ax2.set_yticks(range(len(ylabels)))
        ax2.set_xticklabels(all_types, fontsize=9)
        ax2.set_yticklabels(ylabels, fontsize=7)
        plt.colorbar(im, ax=ax2, label="Fraction of occurrences with this type")
        ax2.set_title(
            "Label-Type Inconsistency — Same Label, Different Types\n"
            "(darker = most common type for that label; mixed row = inconsistent)"
        )
        plt.tight_layout()
        out2 = OUTPUT_DIR / "phase4_label_type_heatmap.png"
        fig2.savefig(out2, dpi=150, bbox_inches="tight")
        plt.close(fig2)
        console.print(f"Label-type heatmap saved to [green]{out2}[/green]")

    # Chart 3: SET value set Jaccard similarity matrix
    top_sets = [(key, grp) for key, grp in sorted(shared, key=lambda x: -len(x[1]))[:30]]
    n = len(top_sets)
    if n > 1:
        sim = np.zeros((n, n))
        for i, (ki, _) in enumerate(top_sets):
            for j, (kj, _) in enumerate(top_sets):
                if i == j:
                    sim[i, j] = 1.0
                else:
                    inter = len(ki & kj)
                    union = len(ki | kj)
                    sim[i, j] = inter / union if union else 0

        set_labels_plot = [
            ", ".join(f"{k}={v}" for k, v in list(dict(key))[:2])[:25]
            for key, _ in top_sets
        ]
        fig3, ax3 = plt.subplots(figsize=(12, 11))
        im3 = ax3.imshow(sim, cmap="Blues", vmin=0, vmax=1)
        ax3.set_xticks(range(n))
        ax3.set_yticks(range(n))
        ax3.set_xticklabels(set_labels_plot, rotation=45, ha="right", fontsize=6)
        ax3.set_yticklabels(set_labels_plot, fontsize=6)
        plt.colorbar(im3, ax=ax3, label="Jaccard similarity")
        ax3.set_title(
            "SET Value Set Similarity (top 30 most-used)\n"
            "1.0 = identical value sets used under different labels"
        )
        plt.tight_layout()
        out3 = OUTPUT_DIR / "phase4_set_similarity.png"
        fig3.savefig(out3, dpi=150, bbox_inches="tight")
        plt.close(fig3)
        console.print(f"SET similarity matrix saved to [green]{out3}[/green]")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 4 — Data Variety and Naming Analysis")

    with YdbConnection.connect() as conn:
        schema = load_schema(conn)

    shared, seen_sets = section_41_set_inventory(schema)
    section_42_boolean_patterns(seen_sets)
    label_counter = section_43_label_frequency(schema)
    inconsistent = section_44_label_type_consistency(schema)
    section_45_canonical_positions(schema)

    visualize(label_counter, inconsistent, shared)

    console.rule("[bold green]Phase 4 complete")


if __name__ == "__main__":
    main()
