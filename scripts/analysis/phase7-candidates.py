"""
Phase 7 — Normalization Candidate Identification (Analysis)
=============================================================
Goal: Apply rules to schema + volume data to produce a ranked list of
normalization targets.

This is analysis-only. Visualization is handled by phase7-viz.py.

Prerequisites:
    phase3-topology.py → phase3/all_fields.json     (required)
    phase2-volume.py   → phase2/file_volume.json    (enables orphan-pointer rule)

Outputs (all in ~/data/vista-fm-browser/phase7/):
    normalization_candidates.json  — full ranked list (consumed by phase8)
    normalization_candidates.csv   — flat version
    summary.json                   — counts by rule (consumed by viz + report)
    phase7-candidates-report.md    — executive report

Run inside the VEHU container:
    python scripts/analysis/phase7-candidates.py
"""

import collections
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from vista_fm_browser.connection import YdbConnection
from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.inventory import FileInventory

log = logging.getLogger(__name__)
console = Console()

OUTPUT_DIR = Path("~/data/vista-fm-browser/phase7/").expanduser()
PHASE2_DIR = Path("~/data/vista-fm-browser/phase2/").expanduser()
PHASE3_DIR = Path("~/data/vista-fm-browser/phase3/").expanduser()


def load_schema(conn: YdbConnection) -> list[dict]:
    cache = PHASE3_DIR / "all_fields.json"
    if cache.exists():
        console.print(f"[dim]Loading cached schema from {cache}[/dim]")
        return json.loads(cache.read_text())
    console.print("\n[bold]Building full schema...[/bold]")
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


def load_volume_map() -> dict[float, int]:
    vol_path = PHASE2_DIR / "file_volume.json"
    if not vol_path.exists():
        console.print(
            "[yellow]phase2/file_volume.json missing — skipping "
            "pointer_to_empty_file rule. Run phase2-volume.py first.[/yellow]"
        )
        return {}
    data = json.loads(vol_path.read_text())
    return {float(r["file_number"]): int(r["entry_count"]) for r in data}


def apply_rules(schema: list[dict], volume_map: dict[float, int]) -> list[dict]:
    candidates: list[dict] = []

    # Rule 1: Same label, different types (≥5 occurrences)
    label_groups: dict[str, list] = {}
    for r in schema:
        label_groups.setdefault(r["field_label"].strip().upper(), []).append(r)
    for label, rows in label_groups.items():
        types = set(r["datatype_code"] for r in rows)
        if len(rows) >= 5 and len(types) > 1:
            dist = collections.Counter(r["datatype_code"] for r in rows)
            candidates.append({
                "rule": "label_type_conflict", "label": label,
                "occurrences": len(rows), "types": dict(dist),
                "recommended_type": dist.most_common(1)[0][0],
                "priority": len(rows),
            })

    # Rule 2: Hub file (≥10 source files reference it)
    inbound: dict[float, set] = {}
    for r in schema:
        if r["datatype_code"] == "P" and r["pointer_file"]:
            inbound.setdefault(r["pointer_file"], set()).add(r["file_number"])
    label_by_file = {r["file_number"]: r["file_label"] for r in schema}
    for tgt, srcs in inbound.items():
        if len(srcs) >= 10:
            candidates.append({
                "rule": "hub_file_reference", "file": tgt,
                "label": label_by_file.get(tgt, "?"),
                "source_files": len(srcs), "priority": len(srcs),
            })

    # Rule 3: DATE field stored as FREE TEXT
    for r in schema:
        if "DATE" in r["field_label"].upper() and r["datatype_code"] == "F":
            candidates.append({
                "rule": "date_as_free_text",
                "file": r["file_number"], "file_label": r["file_label"],
                "field": r["field_number"], "field_label": r["field_label"],
                "package": r["package"], "priority": 5,
            })

    # Rule 4: Pointer to empty file
    if volume_map:
        for r in schema:
            if r["datatype_code"] == "P" and r["pointer_file"]:
                if volume_map.get(r["pointer_file"], -1) == 0:
                    candidates.append({
                        "rule": "pointer_to_empty_file",
                        "file": r["file_number"], "file_label": r["file_label"],
                        "field": r["field_number"], "field_label": r["field_label"],
                        "target_file": r["pointer_file"], "priority": 3,
                    })

    candidates.sort(key=lambda x: -x["priority"])
    return candidates


def write_csv(candidates: list[dict], path: Path) -> None:
    cols = ["rule", "priority", "label", "file", "file_label", "field",
            "field_label", "package", "occurrences", "types", "source_files",
            "target_file", "recommended_type"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for c in candidates:
            row = dict(c)
            if isinstance(row.get("types"), dict):
                row["types"] = "|".join(f"{k}:{v}" for k, v in row["types"].items())
            w.writerow(row)


def build_summary(candidates: list[dict]) -> dict:
    by_rule = collections.Counter(c["rule"] for c in candidates)
    priorities = [c["priority"] for c in candidates]
    return {
        "total_candidates": len(candidates),
        "by_rule": dict(by_rule),
        "priority_max": max(priorities) if priorities else 0,
        "priority_median": sorted(priorities)[len(priorities) // 2] if priorities else 0,
        "top_25": candidates[:25],
    }


def write_report(summary: dict, path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Phase 7 — Normalization Candidates",
        "",
        f"_Generated {ts}_",
        "",
        "## Summary",
        "",
        f"- **Total candidates:** {summary['total_candidates']:,}",
        f"- **Max priority:** {summary['priority_max']}",
        f"- **Median priority:** {summary['priority_median']}",
        "",
        "### By Rule",
        "",
        "| Rule | Count |",
        "|:-----|------:|",
    ]
    for rule, count in sorted(summary["by_rule"].items(), key=lambda x: -x[1]):
        lines.append(f"| {rule} | {count:,} |")

    lines += [
        "",
        "## Top 25 Candidates",
        "",
        "| Rank | Priority | Rule | Target | Detail |",
        "|-----:|---------:|:-----|:-------|:-------|",
    ]
    for i, c in enumerate(summary["top_25"], 1):
        rule = c["rule"]
        if rule == "label_type_conflict":
            target = c.get("label", "")
            detail = ", ".join(f"{k}:{v}" for k, v in c.get("types", {}).items())
        elif rule == "hub_file_reference":
            target = f"File #{c.get('file', '')} {c.get('label', '')}"
            detail = f"{c.get('source_files', '')} refs"
        elif rule == "date_as_free_text":
            target = c.get("field_label", "")
            detail = f"File #{c.get('file', '')} [{c.get('package', '')}]"
        else:
            target = c.get("field_label", "")
            detail = f"→ empty File #{c.get('target_file', '')}"
        lines.append(f"| {i} | {c['priority']} | {rule} | {target} | {detail} |")

    lines += [
        "",
        "## Output Files",
        "",
        "- `normalization_candidates.json` / `.csv` — full ranked list",
        "- `summary.json` — counts by rule (consumed by viz + report)",
        "- `phase7_candidates.png` — bar + scatter visualization (phase7-viz.py)",
        "",
    ]
    path.write_text("\n".join(lines))


def render_terminal(candidates: list[dict]) -> None:
    t = Table(title=f"Top 30 Normalization Candidates (of {len(candidates)})")
    t.add_column("Priority", style="red", justify="right")
    t.add_column("Rule", style="yellow")
    t.add_column("Target", style="white")
    t.add_column("Detail", style="dim")
    for c in candidates[:30]:
        rule = c["rule"]
        if rule == "label_type_conflict":
            target, detail = c.get("label", ""), str(c.get("types", ""))
        elif rule == "hub_file_reference":
            target, detail = c.get("label", ""), f"{c.get('source_files', '')} refs"
        elif rule == "date_as_free_text":
            target = c.get("field_label", "")
            detail = f"File {c.get('file', '')} [{c.get('package', '')}]"
        else:
            target = c.get("field_label", "")
            detail = f"→ empty File {c.get('target_file', '')}"
        t.add_row(str(c["priority"]), rule, target, detail)
    console.print(t)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console.rule("[bold blue]Phase 7 — Normalization Candidates (Analysis)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with YdbConnection.connect() as conn:
        schema = load_schema(conn)

    volume_map = load_volume_map()
    candidates = apply_rules(schema, volume_map)
    summary = build_summary(candidates)
    render_terminal(candidates)

    (OUTPUT_DIR / "normalization_candidates.json").write_text(
        json.dumps(candidates, indent=2, default=str)
    )
    write_csv(candidates, OUTPUT_DIR / "normalization_candidates.csv")
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(summary, OUTPUT_DIR / "phase7-candidates-report.md")

    console.print()
    for name in [
        "normalization_candidates.json", "normalization_candidates.csv",
        "summary.json", "phase7-candidates-report.md",
    ]:
        console.print(f"  [green]wrote[/green] {OUTPUT_DIR / name}")
    console.rule("[bold green]Phase 7 analysis complete")
    console.print("\nNext: run [bold]phase7-viz.py[/bold] to generate PNG visualizations.")


if __name__ == "__main__":
    main()
