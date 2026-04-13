#!/usr/bin/env python3
# ruff: noqa: E501
"""
to_treemap.py — Convert vista-fm-browser analysis outputs to a D3 zoomable treemap.

The generated HTML is self-contained (D3 loaded from CDN, data embedded inline)
and opens directly in any browser.  Each node is clickable — click to drill into
children, click the breadcrumb to navigate back up.

Supported modes (pick the one whose data fits the hierarchical shape):

  inventory   inventory.json  → packages → files
              sized by field_count; color by clinical domain
              ✓ best overall first view: 15-minute scope survey result

  volume      file_volume.json → volume tier → files
              sized by entry_count (log-scaled labels); color by clinical domain
              requires --inventory for package grouping (optional, falls back to tiers)

  schema      all_fields.json → packages → files → field-type buckets
              sized by field count; color by clinical domain
              ✓ shows the full DD shape at one glance

  coverage    phase6_coverage_multi.csv (or .json)
              → files → coverage tier (High/Medium/Low) → fields
              sized by 1-per-field; colored by coverage tier (green/orange/red)

  candidates  normalization_candidates.json → rule type → candidates
              sized by priority score; colored by rule type

Usage:
  # Inside the VEHU container (or any Python 3.10+ env with stdlib only):
  python scripts/to_treemap.py \\
      --mode inventory \\
      --input ~/data/vista-fm-browser/output/inventory.json \\
      --output ~/data/vista-fm-browser/output/treemap_inventory.html

  python scripts/to_treemap.py \\
      --mode volume \\
      --input  ~/data/vista-fm-browser/output/file_volume.json \\
      --inventory ~/data/vista-fm-browser/output/inventory.json \\
      --output ~/data/vista-fm-browser/output/treemap_volume.html

  python scripts/to_treemap.py \\
      --mode schema \\
      --input ~/data/vista-fm-browser/output/all_fields.json \\
      --output ~/data/vista-fm-browser/output/treemap_schema.html

  python scripts/to_treemap.py \\
      --mode coverage \\
      --input ~/data/vista-fm-browser/output/phase6_coverage_multi.csv \\
      --output ~/data/vista-fm-browser/output/treemap_coverage.html

  python scripts/to_treemap.py \\
      --mode candidates \\
      --input ~/data/vista-fm-browser/output/normalization_candidates.json \\
      --output ~/data/vista-fm-browser/output/treemap_candidates.html

Then open the HTML in a browser on the host:
  firefox ~/data/vista-fm-browser/output/treemap_inventory.html &
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# ── VistA clinical domain → hex color ────────────────────────────────────────
# Color families are chosen so related domains share a hue:
#   Blues:   patient / registration / scheduling  (admin workflow)
#   Greens:  pharmacy / nutrition               (medications & food)
#   Oranges: laboratory / radiology             (diagnostics)
#   Reds:    orders / CPRS                      (clinical decisions)
#   Purples: mental health / nursing            (behavioral & bedside)
#   Gold:    billing / finance                  (revenue cycle)
#   Browns:  kernel / system / infrastructure  (plumbing)

DOMAIN_COLORS: dict[str, str] = {
    "Registration/ADT": "#4e79a7",  # steel blue
    "Scheduling": "#76b7d4",  # sky blue
    "Laboratory": "#f28e2b",  # amber
    "Radiology": "#ffbe7d",  # peach
    "Pharmacy": "#59a14f",  # forest green
    "Nutrition": "#8cd17d",  # lime
    "Orders/CPRS": "#e15759",  # tomato
    "Mental Health": "#b07aa1",  # mauve
    "Nursing": "#d4a6c8",  # lavender
    "Surgery": "#ff9da7",  # rose
    "Billing/Finance": "#f1ce63",  # gold
    "Kernel/System": "#9c755f",  # walnut
    "Infrastructure": "#bab0ac",  # silver
    "Other": "#79706e",  # slate
}

# Package namespace prefix → clinical domain
# Sorted longest-first so prefix matching uses the most specific key.
_PKG_DOMAIN_MAP: list[tuple[str, str]] = sorted(
    [
        ("DG", "Registration/ADT"),
        ("DPT", "Registration/ADT"),
        ("ADT", "Registration/ADT"),
        ("MAS", "Registration/ADT"),
        ("PX", "Registration/ADT"),  # PCE
        ("SD", "Scheduling"),
        ("SC", "Scheduling"),
        ("SDAM", "Scheduling"),
        ("LR", "Laboratory"),
        ("LA", "Laboratory"),
        ("CH", "Laboratory"),
        ("MI", "Laboratory"),
        ("RA", "Radiology"),
        ("MAG", "Radiology"),
        ("PS", "Pharmacy"),
        ("PSS", "Pharmacy"),
        ("PSO", "Pharmacy"),
        ("PSJ", "Pharmacy"),
        ("PSH", "Pharmacy"),
        ("PSD", "Pharmacy"),
        ("PSRX", "Pharmacy"),
        ("PRSP", "Nutrition"),
        ("FH", "Nutrition"),
        ("OR", "Orders/CPRS"),
        ("OE", "Orders/CPRS"),
        ("GMRC", "Orders/CPRS"),
        ("GMTS", "Orders/CPRS"),
        ("TIU", "Orders/CPRS"),
        ("CPRS", "Orders/CPRS"),
        ("YS", "Mental Health"),
        ("GMRY", "Nursing"),
        ("NUR", "Nursing"),
        ("SR", "Surgery"),
        ("IB", "Billing/Finance"),
        ("FB", "Billing/Finance"),
        ("DRG", "Billing/Finance"),
        ("XU", "Kernel/System"),
        ("XQ", "Kernel/System"),
        ("XT", "Kernel/System"),
        ("XWB", "Kernel/System"),
        ("DI", "Kernel/System"),
        ("DD", "Kernel/System"),
        ("XTV", "Kernel/System"),
        ("HL", "Infrastructure"),
        ("XDR", "Infrastructure"),
        ("VDEF", "Infrastructure"),
    ],
    key=lambda x: -len(x[0]),  # longest-prefix-first
)


def pkg_domain(pkg_name: str | None, prefix: str | None = None) -> str:
    """Resolve a VistA package name / prefix to a clinical domain."""
    for candidate in [prefix, pkg_name]:
        if not candidate:
            continue
        up = candidate.upper()
        for key, domain in _PKG_DOMAIN_MAP:
            if up.startswith(key):
                return domain
    return "Other"


# ── Data-to-hierarchy converters ──────────────────────────────────────────────


def _load_inventory(inventory_path: Path | None) -> dict[float, tuple[str, str]]:
    """Return {file_number: (pkg_name, prefix)} from an inventory.json."""
    if not inventory_path or not inventory_path.exists():
        return {}
    inv = json.loads(inventory_path.read_text())
    return {
        f["file_number"]: (
            f.get("package_name") or "(unpackaged)",
            f.get("package_prefix") or "",
        )
        for f in inv.get("files", [])
    }


def build_inventory(input_path: Path, **_kw) -> tuple[dict, str]:
    """
    inventory.json → packages → files (sized by field_count).

    Color: clinical domain derived from package prefix.
    """
    data = json.loads(input_path.read_text())
    pkg_meta = {p["name"]: p for p in data.get("packages", [])}

    # group files by package
    files_by_pkg: dict[str, list[dict]] = defaultdict(list)
    for f in data["files"]:
        pkg = f.get("package_name") or "(unpackaged)"
        files_by_pkg[pkg].append(f)

    children = []
    for pkg_name, files in sorted(
        files_by_pkg.items(),
        key=lambda kv: -sum(f["field_count"] for f in kv[1]),
    ):
        prefix = pkg_meta.get(pkg_name, {}).get("prefix", "")
        domain = pkg_domain(pkg_name, prefix)
        total_fields = sum(f["field_count"] for f in files)
        file_nodes = [
            {
                "name": f"{f['label']} (#{f['file_number']:.0f})",
                "value": max(f["field_count"], 1),
                "domain": domain,
                "tooltip": (
                    f"<b>{f['label']}</b><br>"
                    f"File #: {f['file_number']:.0f}<br>"
                    f"Package: {pkg_name} [{prefix}]<br>"
                    f"Fields: {f['field_count']:,}<br>"
                    f"Global: {f['global_root']}"
                ),
            }
            for f in sorted(files, key=lambda x: -x["field_count"])
        ]
        children.append(
            {
                "name": pkg_name,
                "domain": domain,
                "children": file_nodes,
                "tooltip": (
                    f"<b>{pkg_name}</b> [{prefix}]<br>"
                    f"Domain: {domain}<br>"
                    f"Files: {len(files):,}<br>"
                    f"Total fields: {total_fields:,}"
                ),
            }
        )

    return (
        {"name": "VistA FileMan — File Inventory", "children": children},
        "fields",
    )


def build_volume(
    input_path: Path,
    inventory_path: Path | None = None,
    **_kw,
) -> tuple[dict, str]:
    """
    file_volume.json → packages → files (sized by entry_count).

    Falls back to volume-tier grouping when inventory is not supplied.
    Color: clinical domain (with inventory) or volume tier (without).
    """
    volume_list: list[dict] = json.loads(input_path.read_text())
    pkg_by_file = _load_inventory(inventory_path)

    TIER_THRESHOLDS = [
        ("Massive (>100K)", 100_000),
        ("Large (10K–100K)", 10_000),
        ("Medium (1K–10K)", 1_000),
        ("Small (100–1K)", 100),
        ("Tiny (<100)", 1),
    ]
    # Colors for tier-based fallback (when no inventory supplied)
    TIER_DOMAINS = {
        "Massive (>100K)": "Orders/CPRS",
        "Large (10K–100K)": "Registration/ADT",
        "Medium (1K–10K)": "Laboratory",
        "Small (100–1K)": "Scheduling",
        "Tiny (<100)": "Infrastructure",
    }

    if pkg_by_file:
        # Group by package
        pkg_files: dict[str, list[dict]] = defaultdict(list)
        for entry in volume_list:
            fnum = float(entry["file_number"])
            count = entry["entry_count"]
            if count == 0:
                continue
            pkg_name, prefix = pkg_by_file.get(fnum, ("(unpackaged)", ""))
            pkg_files[pkg_name].append(
                {
                    "name": f"{entry['label']} (#{fnum:.0f})",
                    "value": count,
                    "domain": pkg_domain(pkg_name, prefix),
                    "tooltip": (
                        f"<b>{entry['label']}</b><br>"
                        f"File #: {fnum:.0f}<br>"
                        f"Package: {pkg_name} [{prefix}]<br>"
                        f"Entries: {count:,}"
                    ),
                }
            )
        children = []
        for pkg_name, nodes in sorted(
            pkg_files.items(), key=lambda kv: -sum(n["value"] for n in kv[1])
        ):
            prefix = nodes[0]["domain"] if nodes else "Other"
            domain = nodes[0]["domain"] if nodes else "Other"
            total = sum(n["value"] for n in nodes)
            children.append(
                {
                    "name": pkg_name,
                    "domain": domain,
                    "children": sorted(nodes, key=lambda x: -x["value"]),
                    "tooltip": (
                        f"<b>{pkg_name}</b><br>"
                        f"Files with data: {len(nodes):,}<br>"
                        f"Total entries: {total:,}"
                    ),
                }
            )
    else:
        # Tier-based grouping
        tiers: dict[str, list[dict]] = defaultdict(list)
        for entry in volume_list:
            count = entry["entry_count"]
            if count == 0:
                continue
            fnum = float(entry["file_number"])
            tier_name = "Tiny (<100)"
            for tname, tmin in TIER_THRESHOLDS:
                if count >= tmin:
                    tier_name = tname
                    break
            domain = TIER_DOMAINS[tier_name]
            tiers[tier_name].append(
                {
                    "name": f"{entry['label']} (#{fnum:.0f})",
                    "value": count,
                    "domain": domain,
                    "tooltip": (
                        f"<b>{entry['label']}</b><br>"
                        f"File #: {fnum:.0f}<br>"
                        f"Entries: {count:,}"
                    ),
                }
            )
        children = [
            {
                "name": tname,
                "domain": TIER_DOMAINS[tname],
                "children": sorted(tiers[tname], key=lambda x: -x["value"]),
                "tooltip": f"<b>{tname}</b><br>Files: {len(tiers[tname]):,}",
            }
            for tname, _ in TIER_THRESHOLDS
            if tiers.get(tname)
        ]

    return (
        {"name": "VistA FileMan — File Volume", "children": children},
        "entries",
    )


def build_schema(input_path: Path, **_kw) -> tuple[dict, str]:
    """
    all_fields.json → packages → files → field-type buckets (sized by field count).

    Color: clinical domain.  The type breakdown inside each file shows the
    type composition at a glance.
    """
    fields: list[dict] = json.loads(input_path.read_text())

    TYPE_NAMES = {
        "F": "Free Text",
        "N": "Numeric",
        "D": "Date/Time",
        "S": "Set of Codes",
        "P": "Pointer",
        "M": "Multiple",
        "W": "Word Proc",
        "C": "Computed",
        "K": "MUMPS",
        "V": "Variable Ptr",
        "DC": "Computed Date",
    }

    # pkg → file_key → type_code → count
    pkg_file_type: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for r in fields:
        pkg = r.get("package") or "(unpackaged)"
        fkey = f"{r['file_label']} (#{r['file_number']:.0f})"
        dtype = r.get("datatype_code") or "?"
        pkg_file_type[pkg][fkey][dtype] += 1
        # Infer prefix from the first segment of the package namespace in the field
        # (we don't have prefix here, so leave blank; domain lookup uses pkg name)

    children = []
    for pkg_name, files in sorted(
        pkg_file_type.items(),
        key=lambda kv: -sum(sum(t.values()) for t in kv[1].values()),
    ):
        domain = pkg_domain(pkg_name)
        file_nodes = []
        for fkey, type_counts in sorted(
            files.items(), key=lambda kv: -sum(kv[1].values())
        ):
            total = sum(type_counts.values())
            type_nodes = [
                {
                    "name": f"{TYPE_NAMES.get(tc, tc)} ({cnt})",
                    "value": cnt,
                    "domain": domain,
                    "tooltip": (
                        f"<b>{fkey}</b><br>"
                        f"Type: {TYPE_NAMES.get(tc, tc)}<br>"
                        f"Fields: {cnt:,}"
                    ),
                }
                for tc, cnt in sorted(type_counts.items(), key=lambda x: -x[1])
            ]
            file_nodes.append(
                {
                    "name": fkey,
                    "domain": domain,
                    "children": type_nodes,
                    "tooltip": (
                        f"<b>{fkey}</b><br>"
                        f"Package: {pkg_name}<br>"
                        f"Total fields: {total:,}"
                    ),
                }
            )
        pkg_total = sum(sum(t.values()) for t in files.values())
        children.append(
            {
                "name": pkg_name,
                "domain": domain,
                "children": file_nodes,
                "tooltip": (
                    f"<b>{pkg_name}</b><br>"
                    f"Domain: {domain}<br>"
                    f"Files: {len(files):,}<br>"
                    f"Total fields: {pkg_total:,}"
                ),
            }
        )

    return (
        {"name": "VistA FileMan — Schema (all fields)", "children": children},
        "fields",
    )


def build_coverage(input_path: Path, **_kw) -> tuple[dict, str]:
    """
    phase6_coverage_multi.csv (or .json)
    → files → coverage tier → fields (1 per field, colored by tier).

    Green = high coverage (≥80%), Orange = medium (20–80%), Red = low (<20%).
    """
    TIER_ORDER = ["High (≥80%)", "Medium (20–80%)", "Low (<20%)"]
    TIER_DOMAINS = {
        "High (≥80%)": "Pharmacy",  # green
        "Medium (20–80%)": "Laboratory",  # orange
        "Low (<20%)": "Orders/CPRS",  # red
    }

    def tier_for(pct: float) -> str:
        if pct >= 80:
            return "High (≥80%)"
        if pct >= 20:
            return "Medium (20–80%)"
        return "Low (<20%)"

    file_tiers: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )

    if input_path.suffix.lower() == ".csv":
        with open(input_path, newline="") as fh:
            for row in csv.DictReader(fh):
                fname = row.get("file", "?")
                field = row.get("field", "?")
                pct = float(row.get("pct", 0))
                tier = tier_for(pct)
                file_tiers[fname][tier].append(
                    {
                        "name": f"{field} ({pct:.0f}%)",
                        "value": 1,
                        "domain": TIER_DOMAINS[tier],
                        "tooltip": (
                            f"<b>{field}</b><br>File: {fname}<br>Coverage: {pct:.1f}%"
                        ),
                    }
                )
    else:
        rows = json.loads(input_path.read_text())
        for row in rows:
            fname = row.get("file", "?")
            field = row.get("field", "?")
            pct = float(row.get("pct", 0))
            tier = tier_for(pct)
            file_tiers[fname][tier].append(
                {
                    "name": f"{field} ({pct:.0f}%)",
                    "value": 1,
                    "domain": TIER_DOMAINS[tier],
                    "tooltip": (
                        f"<b>{field}</b><br>File: {fname}<br>Coverage: {pct:.1f}%"
                    ),
                }
            )

    file_nodes = []
    for fname, tiers in sorted(file_tiers.items()):
        tier_nodes = [
            {
                "name": f"{tn} ({len(tiers.get(tn, []))})",
                "domain": TIER_DOMAINS[tn],
                "children": tiers[tn],
                "tooltip": (
                    f"<b>{tn}</b><br>File: {fname}<br>Fields: {len(tiers.get(tn, []))}"
                ),
            }
            for tn in TIER_ORDER
            if tiers.get(tn)
        ]
        if not tier_nodes:
            continue
        total = sum(len(v) for v in tiers.values())
        dominant = max(tiers.items(), key=lambda kv: len(kv[1]))[0]
        file_nodes.append(
            {
                "name": fname,
                "domain": TIER_DOMAINS[dominant],
                "children": tier_nodes,
                "tooltip": (f"<b>{fname}</b><br>Total fields: {total}"),
            }
        )

    return (
        {"name": "Field Coverage Analysis", "children": file_nodes},
        "fields",
    )


def build_candidates(input_path: Path, **_kw) -> tuple[dict, str]:
    """
    normalization_candidates.json → rule type → candidates (sized by priority).

    Color: one color per rule type.
    """
    candidates: list[dict] = json.loads(input_path.read_text())

    RULE_LABELS = {
        "label_type_conflict": "Label-Type Conflict",
        "hub_file_reference": "Hub File Reference",
        "date_as_free_text": "Date as Free Text",
        "pointer_to_empty_file": "Pointer → Empty File",
    }
    RULE_DOMAINS = {
        "label_type_conflict": "Orders/CPRS",
        "hub_file_reference": "Registration/ADT",
        "date_as_free_text": "Laboratory",
        "pointer_to_empty_file": "Infrastructure",
    }

    rule_items: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        rule = c.get("rule", "?")
        priority = max(c.get("priority", 1), 1)
        domain = RULE_DOMAINS.get(rule, "Other")

        if rule == "label_type_conflict":
            name = c.get("label", "?")
            detail = (
                f"Types: {c.get('types', {})}<br>"
                f"Occurrences: {c.get('occurrences', '?')}"
            )
        elif rule == "hub_file_reference":
            name = c.get("label", f"File #{c.get('file', '?')}")
            detail = f"{c.get('source_files', '?')} files reference it"
        elif rule == "date_as_free_text":
            name = c.get("field_label", "?")
            detail = (
                f"File: {c.get('file_label', '?')}<br>Package: {c.get('package', '?')}"
            )
        else:
            name = c.get("field_label", "?")
            detail = f"→ empty File #{c.get('target_file', '?')}"

        rule_items[rule].append(
            {
                "name": name,
                "value": priority,
                "domain": domain,
                "tooltip": (
                    f"<b>{name}</b><br>"
                    f"Rule: {RULE_LABELS.get(rule, rule)}<br>"
                    f"{detail}<br>"
                    f"Priority: {priority}"
                ),
            }
        )

    children = [
        {
            "name": RULE_LABELS.get(rule, rule),
            "domain": RULE_DOMAINS.get(rule, "Other"),
            "children": sorted(items, key=lambda x: -x["value"]),
            "tooltip": (
                f"<b>{RULE_LABELS.get(rule, rule)}</b><br>Candidates: {len(items):,}"
            ),
        }
        for rule, items in sorted(rule_items.items(), key=lambda kv: -len(kv[1]))
        if items
    ]

    return (
        {"name": "Normalization Candidates", "children": children},
        "priority",
    )


# ── HTML template ─────────────────────────────────────────────────────────────

# D3 v7 zoomable treemap:
#   • Full hierarchy computed from root on page load.
#   • Clicking a node re-renders its subtree to fill the viewport (drill down).
#   • Breadcrumb trail — click any ancestor to jump back up.
#   • Tooltip with HTML content on hover.
#   • Legend for the domain color palette.
#   • Labels auto-hide when the tile is too small to fit them.

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #111827;
    color: #e5e7eb;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}

  /* ── header ── */
  #header {{
    background: #1f2937;
    border-bottom: 1px solid #374151;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
  }}
  #title {{ font-size: 14px; font-weight: 600; color: #f3f4f6; white-space: nowrap; }}
  #breadcrumb {{ display: flex; align-items: center; gap: 4px; font-size: 12px;
                 flex-wrap: wrap; }}
  .crumb {{
    cursor: pointer; color: #60a5fa; padding: 2px 6px;
    border-radius: 4px; transition: background 0.15s;
  }}
  .crumb:hover {{ background: #374151; }}
  .crumb-sep {{ color: #6b7280; }}
  .crumb.current {{ color: #d1d5db; cursor: default; font-weight: 500; }}
  .crumb.current:hover {{ background: transparent; }}
  #hint {{ margin-left: auto; font-size: 11px; color: #6b7280; white-space: nowrap; }}

  /* ── legend ── */
  #legend {{
    background: #1f2937;
    border-bottom: 1px solid #374151;
    padding: 5px 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    flex-shrink: 0;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 11px;
                  color: #9ca3af; }}
  .legend-swatch {{ width: 11px; height: 11px; border-radius: 2px; flex-shrink: 0; }}

  /* ── treemap svg ── */
  #chart {{ flex: 1; overflow: hidden; position: relative; }}
  svg {{ display: block; width: 100%; height: 100%; }}

  /* ── cells ── */
  .cell {{ cursor: pointer; }}
  .cell rect {{
    stroke: #111827; stroke-width: 1.5px;
    transition: opacity 0.15s;
  }}
  .cell:hover rect {{ opacity: 0.75; }}
  .cell text {{ pointer-events: none; user-select: none; }}

  /* ── tooltip ── */
  #tooltip {{
    position: fixed;
    background: rgba(17,24,39,0.96);
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    line-height: 1.6;
    pointer-events: none;
    display: none;
    max-width: 280px;
    z-index: 100;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  }}
  #tooltip b {{ color: #f3f4f6; }}
</style>
</head>
<body>

<div id="header">
  <div id="title">{title}</div>
  <div id="breadcrumb"></div>
  <div id="hint">click tile to drill down · click breadcrumb to go back</div>
</div>

<div id="legend"></div>
<div id="tooltip"></div>
<div id="chart"><svg id="svg"></svg></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
// ── embedded data ─────────────────────────────────────────────────────────────
const DATA         = {data_json};
const DOMAIN_COLORS = {domain_colors_json};
const VALUE_LABEL  = "{value_label}";

// ── state ─────────────────────────────────────────────────────────────────────
const chartEl  = document.getElementById("chart");
const svg      = d3.select("#svg");
const tooltip  = document.getElementById("tooltip");
let rootHier, history;

// ── color helpers ─────────────────────────────────────────────────────────────
function getColor(d) {{
  // Walk ancestors until a domain is found
  let node = d;
  while (node) {{
    const dom = node.data && node.data.domain;
    if (dom && DOMAIN_COLORS[dom]) return DOMAIN_COLORS[dom];
    node = node.parent;
  }}
  return "#6b7280";
}}

function lighten(hex, factor) {{
  // Slightly lighten a hex color for parent tiles
  const r = parseInt(hex.slice(1,3), 16);
  const g = parseInt(hex.slice(3,5), 16);
  const b = parseInt(hex.slice(5,7), 16);
  const mix = v => Math.round(v + (255 - v) * factor);
  return `rgb(${{mix(r)}},${{mix(g)}},${{mix(b)}})`;
}}

// ── treemap layout ────────────────────────────────────────────────────────────
function makeTreemap(w, h) {{
  return d3.treemap()
    .size([w, h])
    .paddingOuter(3)
    .paddingTop(20)
    .paddingInner(2)
    .round(true);
}}

function buildHierarchy(data) {{
  return d3.hierarchy(data)
    .sum(d => d.children ? 0 : Math.max(d.value || 1, 1))
    .sort((a, b) => b.value - a.value);
}}

// ── legend ────────────────────────────────────────────────────────────────────
function buildLegend() {{
  const legEl = document.getElementById("legend");
  Object.entries(DOMAIN_COLORS).forEach(([name, color]) => {{
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML =
      `<div class="legend-swatch" style="background:${{color}}"></div>` +
      `<span>${{name}}</span>`;
    legEl.appendChild(item);
  }});
}}

// ── breadcrumb ────────────────────────────────────────────────────────────────
function renderBreadcrumb() {{
  const bc = document.getElementById("breadcrumb");
  bc.innerHTML = "";
  history.forEach((node, i) => {{
    if (i > 0) {{
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "›";
      bc.appendChild(sep);
    }}
    const crumb = document.createElement("span");
    crumb.className = "crumb" + (i === history.length - 1 ? " current" : "");
    crumb.textContent = node.data.name.length > 28
      ? node.data.name.slice(0, 26) + "…"
      : node.data.name;
    if (i < history.length - 1) {{
      crumb.addEventListener("click", () => {{
        history = history.slice(0, i + 1);
        render(node);
      }});
    }}
    bc.appendChild(crumb);
  }});
}}

// ── render ────────────────────────────────────────────────────────────────────
function render(focused) {{
  const W = chartEl.clientWidth;
  const H = chartEl.clientHeight;
  svg.attr("viewBox", `0 0 ${{W}} ${{H}}`);

  // Scale from focused node's coordinate space to viewport
  const xScale = d3.scaleLinear()
    .domain([focused.x0, focused.x1]).range([0, W]);
  const yScale = d3.scaleLinear()
    .domain([focused.y0, focused.y1]).range([0, H]);

  // Collect nodes to display: children of focused (one level down)
  const nodes = (focused.children || [focused]).concat(
    // Also show grandchildren so tiles don't appear flat/empty
    (focused.children || []).flatMap(c => c.children || [])
  );

  // Remove old cells
  svg.selectAll(".cell").remove();

  const fmt = d3.format(",d");

  const cell = svg.selectAll(".cell")
    .data(focused.children || [focused])
    .join("g")
    .attr("class", "cell")
    .attr("transform", d => `translate(${{xScale(d.x0)}},${{yScale(d.y0)}})`);

  const tw = d => Math.max(0, xScale(d.x1) - xScale(d.x0) - 1);
  const th = d => Math.max(0, yScale(d.y1) - yScale(d.y0) - 1);

  // Background rect (lighter for parent tiles)
  cell.append("rect")
    .attr("width",  tw)
    .attr("height", th)
    .attr("fill",   d => d.children ? lighten(getColor(d), 0.18) : getColor(d))
    .attr("fill-opacity", 0.88);

  // Stripe for parent tiles to signal "drill in"
  cell.filter(d => !!d.children)
    .append("rect")
    .attr("width",  tw)
    .attr("height", 3)
    .attr("fill",   d => getColor(d))
    .attr("fill-opacity", 0.9);

  // Primary label (name)
  cell.append("text")
    .attr("x", 5)
    .attr("y", 14)
    .attr("fill", "#f3f4f6")
    .attr("font-size", d => {{
      const w = xScale(d.x1) - xScale(d.x0);
      return Math.min(12, Math.max(8, Math.sqrt(w) * 0.8)) + "px";
    }})
    .attr("font-weight", d => d.children ? "600" : "400")
    .text(d => {{
      const w = xScale(d.x1) - xScale(d.x0);
      if (w < 30) return "";
      const name = d.data.name;
      const maxChars = Math.floor(w / 6.5);
      return name.length > maxChars ? name.slice(0, maxChars - 1) + "…" : name;
    }});

  // Value sub-label
  cell.append("text")
    .attr("x", 5)
    .attr("y", 27)
    .attr("fill", "rgba(255,255,255,0.55)")
    .attr("font-size", "9px")
    .text(d => {{
      const w = xScale(d.x1) - xScale(d.x0);
      const h = yScale(d.y1) - yScale(d.y0);
      if (w < 55 || h < 30) return "";
      return fmt(d.value) + " " + VALUE_LABEL;
    }});

  // Child-count hint for parent tiles
  cell.filter(d => !!d.children)
    .append("text")
    .attr("x", d => xScale(d.x1) - xScale(d.x0) - 5)
    .attr("y", 13)
    .attr("text-anchor", "end")
    .attr("fill", "rgba(255,255,255,0.45)")
    .attr("font-size", "9px")
    .text(d => {{
      const w = xScale(d.x1) - xScale(d.x0);
      return w > 60 ? (d.children.length + " ▸") : "";
    }});

  // Click: drill down into children
  cell.on("click", (event, d) => {{
    if (d.children && d.children.length) {{
      history.push(d);
      renderBreadcrumb();
      render(d);
    }}
  }});

  // Tooltip
  cell
    .on("mousemove", (event, d) => {{
      tooltip.style.display = "block";
      tooltip.style.left = (event.clientX + 14) + "px";
      tooltip.style.top  = (event.clientY - 10) + "px";
      tooltip.innerHTML  = d.data.tooltip || `<b>${{d.data.name}}</b>`;
    }})
    .on("mouseleave", () => {{ tooltip.style.display = "none"; }});

  renderBreadcrumb();
}}

// ── init ──────────────────────────────────────────────────────────────────────
function init() {{
  const W = chartEl.clientWidth;
  const H = chartEl.clientHeight;

  const hier  = buildHierarchy(DATA);
  rootHier    = makeTreemap(W, H)(hier);
  history     = [rootHier];

  buildLegend();
  render(rootHier);
}}

// Resize support
window.addEventListener("resize", () => {{
  const W = chartEl.clientWidth;
  const H = chartEl.clientHeight;
  const hier   = buildHierarchy(DATA);
  rootHier     = makeTreemap(W, H)(hier);
  // Rebuild history with updated layout coordinates
  history = [rootHier];
  render(rootHier);
}});

init();
</script>
</body>
</html>
"""


# ── CLI ───────────────────────────────────────────────────────────────────────

MODES = {
    "inventory": build_inventory,
    "volume": build_volume,
    "schema": build_schema,
    "coverage": build_coverage,
    "candidates": build_candidates,
}

MODE_HELP = {
    "inventory": "inventory.json → packages → files (sized by field_count)",
    "volume": "file_volume.json → packages/tiers → files (sized by entry_count)",
    "schema": "all_fields.json → packages → files → field types",
    "coverage": "phase6_coverage_multi.csv/json → files → fields by coverage tier",
    "candidates": "normalization_candidates.json → rules → candidates",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        "-m",
        required=True,
        choices=list(MODES),
        help="How to interpret the input: "
        + " | ".join(f"{k} ({v})" for k, v in MODE_HELP.items()),
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Input JSON or CSV file to convert.",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help="(volume mode only) inventory.json for package grouping.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output HTML file path.  Defaults to <input_stem>_treemap.html.",
    )
    parser.add_argument(
        "--title",
        "-t",
        default=None,
        help="Override the page title shown in the header.",
    )

    args = parser.parse_args(argv)

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    output_path = args.output
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_treemap.html"
    output_path = output_path.expanduser().resolve()

    print(f"Mode:   {args.mode}")
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")

    builder = MODES[args.mode]
    tree, value_label = builder(
        input_path=input_path,
        inventory_path=args.inventory.expanduser().resolve()
        if args.inventory
        else None,
    )

    title = args.title or tree.get("name", "Vista FileMan Treemap")

    # Filter domain_colors to only those actually used in the tree
    used_domains: set[str] = set()

    def collect_domains(node: dict) -> None:
        if node.get("domain"):
            used_domains.add(node["domain"])
        for child in node.get("children", []):
            collect_domains(child)

    collect_domains(tree)
    active_colors = {k: v for k, v in DOMAIN_COLORS.items() if k in used_domains}

    html = _HTML_TEMPLATE.format(
        title=title,
        data_json=json.dumps(tree, ensure_ascii=False, separators=(",", ":")),
        domain_colors_json=json.dumps(
            active_colors, ensure_ascii=False, separators=(",", ":")
        ),
        value_label=value_label,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    node_count = sum(1 for _ in _walk(tree))
    print(f"Done.   {node_count:,} nodes → {output_path.stat().st_size // 1024} KB")
    return 0


def _walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


if __name__ == "__main__":
    raise SystemExit(main())
