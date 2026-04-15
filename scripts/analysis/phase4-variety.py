"""
Phase 4 — Data Variety and Naming Analysis (Analysis)
======================================================
Goal: Understand what values exist (SET-OF-CODES), how naming is used
consistently or inconsistently, and where the same concept appears under
different labels.

This is analysis-only. Visualization is handled by phase4-viz.py.

Prerequisites:
    phase3-topology.py — all_fields.json (schema cache; built here if missing)

Outputs (all in ~/data/vista-fm-browser/phase4/):
    label_frequency.csv        — every unique label with occurrence count
    label_type_inconsistency.csv — labels used with ≥2 datatypes
    shared_sets.json           — value sets reused across ≥5 fields
    canonical_positions.json   — standard field-position analysis
    summary.json               — top-N slices for viz + report
    phase4-variety-report.md   — executive report

Run inside the VEHU container:
    python scripts/analysis/phase4-variety.py
"""

import collections
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase4/").expanduser()
PHASE3_DIR = Path("~/data/vista-fm-browser/phase3/").expanduser()


def load_schema(conn: YdbConnection) -> list[dict]:
    cache = PHASE3_DIR / "all_fields.json"
    if cache.exists():
        console.print(f"[dim]Loading cached schema from {cache}[/dim]")
        return json.loads(cache.read_text())

    console.print("\n[bold]Building full schema (reading all ^DD entries)...[/bold]")
    dd = DataDictionary(conn)
    fi = FileInventory(conn)
    fi.load()
    pkg_by_file = {fr.file_number: (fr.package_name or "(unpackaged)") for fr in fi.list_files()}
    schema: list[dict] = []
    for file_num, file_label in dd.list_files():
        fd = dd.get_file(file_num)
        if not fd:
            continue
        for field_num, fld in fd.fields.items():
            schema.append({
                "file_number": file_num, "file_label": file_label,
                "package": pkg_by_file.get(file_num, "(unpackaged)"),
                "field_number": field_num, "field_label": fld.label,
                "datatype_code": fld.datatype_code, "datatype_name": fld.datatype_name,
                "pointer_file": fld.pointer_file, "set_values": fld.set_values,
            })
    PHASE3_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(schema, indent=2, default=str))
    return schema


def canon_set(sv: dict) -> frozenset:
    return frozenset((k.strip().upper(), v.strip().upper()) for k, v in sv.items())


def analyze_shared_sets(schema: list[dict]) -> tuple[list[dict], dict[frozenset, list]]:
    """Find SET value-sets reused across ≥5 fields."""
    set_fields = [r for r in schema if r["datatype_code"] == "S" and r["set_values"]]
    seen_sets: dict[frozenset, list] = {}
    for r in set_fields:
        seen_sets.setdefault(canon_set(r["set_values"]), []).append(r)

    shared: list[dict] = []
    for key, group in sorted(seen_sets.items(), key=lambda x: -len(x[1])):
        if len(group) < 5:
            continue
        shared.append({
            "codes": dict(key),
            "occurrences": len(group),
            "unique_files": len({r["file_number"] for r in group}),
            "sample_fields": [
                {
                    "file_number": r["file_number"],
                    "file_label": r["file_label"],
                    "field_label": r["field_label"],
                }
                for r in group[:5]
            ],
        })
    return shared, seen_sets


def analyze_boolean_patterns(seen_sets: dict[frozenset, list]) -> list[dict]:
    patterns = [
        frozenset({("Y", "YES"), ("N", "NO")}),
        frozenset({("1", "YES"), ("0", "NO")}),
        frozenset({("A", "ACTIVE"), ("I", "INACTIVE")}),
        frozenset({("1", "ACTIVE"), ("0", "INACTIVE")}),
    ]
    out: list[dict] = []
    for p in patterns:
        matches = seen_sets.get(p, [])
        if matches:
            out.append({
                "codes": dict(p),
                "field_count": len(matches),
                "file_count": len({r["file_number"] for r in matches}),
            })
    return out


def analyze_label_frequency(schema: list[dict]) -> list[tuple[str, int]]:
    c = collections.Counter(r["field_label"].strip().upper() for r in schema)
    return c.most_common()


def analyze_label_type_inconsistency(schema: list[dict]) -> list[dict]:
    groups: dict[str, list] = {}
    for r in schema:
        groups.setdefault(r["field_label"].strip().upper(), []).append(r)
    inconsistent: list[dict] = []
    for label, rows in groups.items():
        if len(rows) < 5:
            continue
        types = collections.Counter(r["datatype_code"] for r in rows)
        if len(types) > 1:
            inconsistent.append({
                "label": label, "occurrences": len(rows),
                "types": dict(types),
                "files": len({r["file_number"] for r in rows}),
            })
    inconsistent.sort(key=lambda x: -x["occurrences"])
    return inconsistent


def analyze_canonical_positions(schema: list[dict]) -> list[dict]:
    canonical = {
        0.01: "PRIMARY NAME/IDENTIFIER",
        0.02: "CATEGORY/TYPE",
        0.03: "PARENT REFERENCE or DATE",
        0.05: "SEX or SECONDARY IDENTIFIER",
        0.07: "STATUS",
        0.09: "SSN or UNIQUE ID",
        1.0: "SECONDARY CONTENT or ADDRESS",
        99.0: "CLASS/CATEGORY",
    }
    out: list[dict] = []
    for pos, concept in canonical.items():
        hits = [r for r in schema if abs(r["field_number"] - pos) < 0.001]
        if not hits:
            continue
        types = collections.Counter(r["datatype_code"] for r in hits)
        labels = collections.Counter(r["field_label"].upper() for r in hits)
        out.append({
            "position": pos, "canonical_concept": concept,
            "definitions": len(hits),
            "top_types": dict(types.most_common(5)),
            "top_labels": dict(labels.most_common(5)),
        })
    return out


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_label_frequency_csv(rows: list[tuple[str, int]], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "count"])
        w.writerows(rows)


def write_inconsistency_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "occurrences", "file_count", "types"])
        for r in rows:
            w.writerow([r["label"], r["occurrences"], r["files"],
                        "|".join(f"{k}:{v}" for k, v in r["types"].items())])


def write_report(summary: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Phase 4 — Data Variety and Naming Analysis",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Unique field labels:** {summary['unique_labels']:,}",
        f"- **SET-OF-CODES fields with values:** {summary['set_fields_with_values']:,}",
        f"- **Shared value sets (reused ≥5 fields):** {summary['shared_sets_count']:,}",
        f"- **Label-type inconsistencies (≥5 fields, ≥2 types):** {summary['label_type_inconsistencies']:,}",
        f"- **Boolean pattern variants:** {len(summary['boolean_patterns'])}",
        "",
        "## Top 20 Most-Common Field Labels",
        "",
        "| Label | Count |",
        "|:------|------:|",
    ]
    for lbl, count in summary["top_labels"][:20]:
        lines.append(f"| {lbl} | {count:,} |")

    lines += [
        "",
        "## Top 15 Label-Type Inconsistencies",
        "",
        "| Label | Occurrences | Files | Types |",
        "|:------|------------:|------:|:------|",
    ]
    for r in summary["top_inconsistencies"][:15]:
        types_str = ", ".join(f"{k}:{v}" for k, v in r["types"].items())
        lines.append(f"| {r['label']} | {r['occurrences']} | {r['files']} | {types_str} |")

    if summary["boolean_patterns"]:
        lines += [
            "",
            "## Boolean-Equivalent Patterns",
            "",
            "| Codes | Fields | Files |",
            "|:------|-------:|------:|",
        ]
        for b in summary["boolean_patterns"]:
            lines.append(f"| `{b['codes']}` | {b['field_count']} | {b['file_count']} |")

    lines += [
        "",
        "## Output Files",
        "",
        "- `label_frequency.csv` — every label with count",
        "- `label_type_inconsistency.csv` — same-label/different-type conflicts",
        "- `shared_sets.json` — reused SET value sets",
        "- `canonical_positions.json` — standard-position field analysis",
        "- `summary.json` — top-N slices (consumed by viz + report)",
        "- `phase4_*.png` — visualizations (from phase4-viz.py)",
        "",
    ]
    path.write_text("\n".join(lines))


def render_terminal(summary: dict) -> None:
    console.print(f"\nUnique labels: [bold]{summary['unique_labels']:,}[/bold]")
    console.print(f"Shared sets (≥5 fields): [bold]{summary['shared_sets_count']}[/bold]")
    console.print(f"Label-type conflicts: [bold]{summary['label_type_inconsistencies']}[/bold]")
    console.print("\n[bold]Top 15 label-type conflicts:[/bold]")
    for r in summary["top_inconsistencies"][:15]:
        console.print(f"  {r['label']:35s} {r['occurrences']:4d} fields  types={r['types']}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 4 — Data Variety (Analysis)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        schema = load_schema(conn)

    label_freq = analyze_label_frequency(schema)
    inconsistent = analyze_label_type_inconsistency(schema)
    shared, seen_sets = analyze_shared_sets(schema)
    boolean_patterns = analyze_boolean_patterns(seen_sets)
    canonical = analyze_canonical_positions(schema)

    summary = {
        "unique_labels": len(label_freq),
        "set_fields_with_values": sum(1 for r in schema
                                      if r["datatype_code"] == "S" and r["set_values"]),
        "shared_sets_count": len(shared),
        "label_type_inconsistencies": len(inconsistent),
        "boolean_patterns": boolean_patterns,
        "top_labels": label_freq[:60],
        "top_inconsistencies": inconsistent[:40],
        "top_shared_sets": shared[:30],
    }
    render_terminal(summary)

    write_label_frequency_csv(label_freq, OUTPUT_DIR / "label_frequency.csv")
    write_inconsistency_csv(inconsistent, OUTPUT_DIR / "label_type_inconsistency.csv")
    (OUTPUT_DIR / "shared_sets.json").write_text(json.dumps(shared, indent=2, default=str))
    (OUTPUT_DIR / "canonical_positions.json").write_text(json.dumps(canonical, indent=2, default=str))
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(summary, OUTPUT_DIR / "phase4-variety-report.md")

    console.print()
    for name in [
        "label_frequency.csv", "label_type_inconsistency.csv",
        "shared_sets.json", "canonical_positions.json",
        "summary.json", "phase4-variety-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 4 analysis complete")
    console.print("\nNext: run [bold]phase4-viz.py[/bold] to generate PNG visualizations.")


if __name__ == "__main__":
    main()
