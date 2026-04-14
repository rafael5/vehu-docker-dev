"""
Phase 7 — Normalization Candidate Identification
================================================
Goal: Apply rules to the schema data collected in Phases 3–6 to produce a
ranked list of normalization targets.

Prerequisites:
    phase3_topology.py  — all_fields.json (full schema cache)
    phase2_volume.py    — file_volume.json (for orphan pointer rule)

Outputs:
    ~/data/vista-fm-browser/output/normalization_candidates.json
    ~/data/vista-fm-browser/output/phase7_candidates.png

Run inside the VEHU container:
    python scripts/analysis/phase7_candidates.py
"""

import collections
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from rich.console import Console
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/output/").expanduser()

RULE_COLORS = {
    "label_type_conflict": "#d62728",
    "hub_file_reference": "#ff7f0e",
    "date_as_free_text": "#9467bd",
    "pointer_to_empty_file": "#1f77b4",
}


def load_schema(conn: YdbConnection) -> list[dict]:
    cache = OUTPUT_DIR / "all_fields.json"
    if cache.exists():
        console.print(f"[dim]Loading cached schema from {cache}[/dim]")
        return json.loads(cache.read_text())

    console.print("\n[bold]Building full schema...[/bold]")
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
    return schema


def load_volume_map() -> dict[float, int]:
    """Load file_volume.json if available (needed for orphan pointer rule)."""
    vol_path = OUTPUT_DIR / "file_volume.json"
    if not vol_path.exists():
        console.print(
            "[yellow]file_volume.json not found — skipping pointer_to_empty_file rule.[/yellow]\n"
            "  Run phase2_volume.py first to enable this rule."
        )
        return {}
    data = json.loads(vol_path.read_text())
    return {float(r["file_number"]): int(r["entry_count"]) for r in data}


def apply_rules(schema: list[dict], volume_map: dict[float, int]) -> list[dict]:
    """Apply all normalization rules and return sorted candidate list."""
    candidates: list[dict] = []

    # Rule 1: Same label, different types (≥5 occurrences)
    label_groups: dict[str, list[dict]] = {}
    for r in schema:
        key = r["field_label"].strip().upper()
        label_groups.setdefault(key, []).append(r)

    for label, rows in label_groups.items():
        types = set(r["datatype_code"] for r in rows)
        if len(rows) >= 5 and len(types) > 1:
            type_dist = collections.Counter(r["datatype_code"] for r in rows)
            dominant = type_dist.most_common(1)[0][0]
            candidates.append(
                {
                    "rule": "label_type_conflict",
                    "label": label,
                    "occurrences": len(rows),
                    "types": dict(type_dist),
                    "recommended_type": dominant,
                    "priority": len(rows),
                }
            )

    # Rule 2: High-inbound hub file (>10 files reference it)
    pointer_fields = [
        r for r in schema if r["datatype_code"] == "P" and r["pointer_file"]
    ]
    inbound: dict[float, set[float]] = {}
    for r in pointer_fields:
        tgt = r["pointer_file"]
        inbound.setdefault(tgt, set()).add(r["file_number"])

    for tgt, srcs in inbound.items():
        if len(srcs) >= 10:
            fd_label = next(
                (r["file_label"] for r in schema if r["file_number"] == tgt), "?"
            )
            candidates.append(
                {
                    "rule": "hub_file_reference",
                    "file": tgt,
                    "label": fd_label,
                    "source_files": len(srcs),
                    "priority": len(srcs),
                }
            )

    # Rule 3: DATE field stored as FREE TEXT
    for r in schema:
        if "DATE" in r["field_label"].upper() and r["datatype_code"] == "F":
            candidates.append(
                {
                    "rule": "date_as_free_text",
                    "file": r["file_number"],
                    "file_label": r["file_label"],
                    "field": r["field_number"],
                    "field_label": r["field_label"],
                    "package": r["package"],
                    "priority": 5,
                }
            )

    # Rule 4: Orphan pointer (points to a file with no data) — only if volume_map available
    if volume_map:
        for r in schema:
            if r["datatype_code"] == "P" and r["pointer_file"]:
                if volume_map.get(r["pointer_file"], -1) == 0:
                    candidates.append(
                        {
                            "rule": "pointer_to_empty_file",
                            "file": r["file_number"],
                            "file_label": r["file_label"],
                            "field": r["field_number"],
                            "field_label": r["field_label"],
                            "target_file": r["pointer_file"],
                            "priority": 3,
                        }
                    )

    candidates.sort(key=lambda x: -x["priority"])
    return candidates


def export_candidates(candidates: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "normalization_candidates.json"
    out.write_text(json.dumps(candidates, indent=2, default=str))
    console.print(
        f"Normalization candidates: [bold]{len(candidates):,}[/bold] written to [green]{out}[/green]"
    )


def print_candidates_table(candidates: list[dict]) -> None:
    t = Table(
        title=f"Top 30 Normalization Candidates (of {len(candidates)})",
        show_lines=False,
    )
    t.add_column("Priority", style="red", justify="right", width=8)
    t.add_column("Rule", style="yellow", width=28)
    t.add_column("Label/File", style="white", width=35)
    t.add_column("Detail", style="dim", width=30)

    for c in candidates[:30]:
        rule = c["rule"]
        pri = str(c["priority"])
        if rule == "label_type_conflict":
            name = c.get("label", "")
            detail = str(c.get("types", ""))
        elif rule == "hub_file_reference":
            name = c.get("label", "")
            detail = f"{c.get('source_files', '')} files reference it"
        elif rule == "date_as_free_text":
            name = c.get("field_label", "")
            detail = f"File {c.get('file', '')} [{c.get('package', '')}]"
        else:
            name = c.get("field_label", "")
            detail = f"→ empty File {c.get('target_file', '')}"
        t.add_row(pri, rule, name, detail)

    console.print(t)


def visualize(candidates: list[dict]) -> None:
    if not candidates:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_cands = pd.DataFrame(candidates)
    rule_counts = df_cands["rule"].value_counts()

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Chart 1: candidates by rule type
    ax = axes[0]
    colors_bar = [RULE_COLORS.get(r, "gray") for r in rule_counts.index]
    bars = ax.bar(rule_counts.index, rule_counts.values, color=colors_bar)
    ax.bar_label(bars, padding=3)
    ax.set_xlabel("Rule")
    ax.set_ylabel("Candidate count")
    ax.set_title("Normalization Candidates by Rule Type")
    ax.tick_params(axis="x", rotation=20, labelsize=8)

    # Chart 2: scatter priority vs occurrences
    ax2 = axes[1]
    for rule, grp in df_cands.groupby("rule"):
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
    out_path = OUTPUT_DIR / "phase7_candidates.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"Candidates chart saved to [green]{out_path}[/green]")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 7 — Normalization Candidate Identification")

    with YdbConnection.connect() as conn:
        schema = load_schema(conn)

    volume_map = load_volume_map()
    candidates = apply_rules(schema, volume_map)
    export_candidates(candidates)
    print_candidates_table(candidates)
    visualize(candidates)

    console.rule("[bold green]Phase 7 complete")


if __name__ == "__main__":
    main()
