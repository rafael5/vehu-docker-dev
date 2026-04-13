#!/usr/bin/env python3
# ruff: noqa: E501
"""
viz_library.py — FileMan Visualization Library
===============================================
Generates self-contained D3 HTML files for exploring the FileMan database
from multiple visual angles.  All output opens directly in a browser.

Each visualization asks a different question about the data:

  heatmap     Which packages rely on which field types?
              (variety × package matrix — shows structural differences
               between clinical domains)

  correlogram Do file-level attributes correlate?
              (scatter-matrix of field_count / entry_count / pointer_count
               / set_count / multiple_count — reveals design patterns)

  wordcloud   What field labels dominate VistA?
              (label frequency cloud — shows shared vocabulary; color
               encodes the dominant type for each label)

  dendrogram  How are files organized within packages?
              (radial tree: packages → files, sized by field_count —
               reveals package depth and file distribution)

  sankey      How do packages depend on each other via pointers?
              (cross-package pointer flow — shows which packages are hubs,
               which are sources, which are leaf consumers)

  bundle      Which files are tightly coupled vs loosely coupled?
              (hierarchical edge bundling: files in a circle grouped by
               package; pointer edges bundled — reveals coupling clusters)

Usage (inside container or any Python ≥3.10 env, no extra packages needed):

  python scripts/viz_library.py heatmap \\
      --input ~/data/vista-fm-browser/output/all_fields.json \\
      --output ~/data/vista-fm-browser/output/viz_heatmap.html

  python scripts/viz_library.py correlogram \\
      --input ~/data/vista-fm-browser/output/inventory.json \\
      --schema ~/data/vista-fm-browser/output/all_fields.json \\
      --volume ~/data/vista-fm-browser/output/file_volume.json \\
      --output ~/data/vista-fm-browser/output/viz_correlogram.html

  python scripts/viz_library.py wordcloud \\
      --input ~/data/vista-fm-browser/output/all_fields.json \\
      --output ~/data/vista-fm-browser/output/viz_wordcloud.html

  python scripts/viz_library.py dendrogram \\
      --input ~/data/vista-fm-browser/output/inventory.json \\
      --output ~/data/vista-fm-browser/output/viz_dendrogram.html

  python scripts/viz_library.py sankey \\
      --input ~/data/vista-fm-browser/output/all_fields.json \\
      --inventory ~/data/vista-fm-browser/output/inventory.json \\
      --output ~/data/vista-fm-browser/output/viz_sankey.html

  python scripts/viz_library.py bundle \\
      --input ~/data/vista-fm-browser/output/all_fields.json \\
      --inventory ~/data/vista-fm-browser/output/inventory.json \\
      --output ~/data/vista-fm-browser/output/viz_bundle.html

Then open the HTML in a browser on the host:
  firefox ~/data/vista-fm-browser/output/viz_heatmap.html &

External D3 dependencies (loaded from CDN — requires internet access):
  D3 v7:       https://d3js.org/d3.v7.min.js
  d3-cloud:    https://cdn.jsdelivr.net/npm/d3-cloud@1.2.7/build/d3.layout.cloud.min.js
  d3-sankey:   https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── Shared color palette ──────────────────────────────────────────────────────
# Clinical domains share a color family so related packages cluster visually.

DOMAIN_COLORS: dict[str, str] = {
    "Registration/ADT": "#4e79a7",
    "Scheduling": "#76b7d4",
    "Laboratory": "#f28e2b",
    "Radiology": "#ffbe7d",
    "Pharmacy": "#59a14f",
    "Nutrition": "#8cd17d",
    "Orders/CPRS": "#e15759",
    "Mental Health": "#b07aa1",
    "Nursing": "#d4a6c8",
    "Surgery": "#ff9da7",
    "Billing/Finance": "#f1ce63",
    "Kernel/System": "#9c755f",
    "Infrastructure": "#bab0ac",
    "Other": "#79706e",
}

_FIELD_TYPE_COLORS: dict[str, str] = {
    "F": "#4e79a7",  # Free Text — blue
    "P": "#e15759",  # Pointer — red
    "S": "#59a14f",  # Set of Codes — green
    "D": "#f28e2b",  # Date/Time — orange
    "N": "#76b7d4",  # Numeric — sky blue
    "M": "#b07aa1",  # Multiple — purple
    "W": "#9c755f",  # Word Processing — brown
    "C": "#f1ce63",  # Computed — gold
    "K": "#ff9da7",  # MUMPS — rose
    "V": "#8cd17d",  # Variable Pointer — lime
    "DC": "#ffbe7d",  # Computed Date — peach
    "?": "#79706e",  # Unknown — slate
}

_PKG_DOMAIN_MAP: list[tuple[str, str]] = sorted(
    [
        ("PSRX", "Pharmacy"),
        ("PSS", "Pharmacy"),
        ("PSO", "Pharmacy"),
        ("PSJ", "Pharmacy"),
        ("PSH", "Pharmacy"),
        ("PSD", "Pharmacy"),
        ("PS", "Pharmacy"),
        ("PRSP", "Nutrition"),
        ("FH", "Nutrition"),
        ("GMRC", "Orders/CPRS"),
        ("GMTS", "Orders/CPRS"),
        ("CPRS", "Orders/CPRS"),
        ("TIU", "Orders/CPRS"),
        ("OR", "Orders/CPRS"),
        ("OE", "Orders/CPRS"),
        ("GMRY", "Nursing"),
        ("NUR", "Nursing"),
        ("SDAM", "Scheduling"),
        ("SD", "Scheduling"),
        ("SC", "Scheduling"),
        ("VDEF", "Infrastructure"),
        ("XDR", "Infrastructure"),
        ("HL", "Infrastructure"),
        ("XWB", "Kernel/System"),
        ("XTV", "Kernel/System"),
        ("XT", "Kernel/System"),
        ("XQ", "Kernel/System"),
        ("XU", "Kernel/System"),
        ("DI", "Kernel/System"),
        ("DD", "Kernel/System"),
        ("MAG", "Radiology"),
        ("RA", "Radiology"),
        ("DRG", "Billing/Finance"),
        ("IB", "Billing/Finance"),
        ("FB", "Billing/Finance"),
        ("MAS", "Registration/ADT"),
        ("ADT", "Registration/ADT"),
        ("DPT", "Registration/ADT"),
        ("DG", "Registration/ADT"),
        ("PX", "Registration/ADT"),
        ("LA", "Laboratory"),
        ("CH", "Laboratory"),
        ("MI", "Laboratory"),
        ("LR", "Laboratory"),
        ("SR", "Surgery"),
        ("YS", "Mental Health"),
    ],
    key=lambda t: -len(t[0]),
)


def pkg_domain(pkg_name: str | None, prefix: str | None = None) -> str:
    for candidate in filter(None, [prefix, pkg_name]):
        up = candidate.upper()
        for key, domain in _PKG_DOMAIN_MAP:
            if up.startswith(key):
                return domain
    return "Other"


# ── Template injection ────────────────────────────────────────────────────────


def _inject(template: str, **kwargs) -> str:
    """Replace __KEY__ markers with JSON or string values.  Avoids f-string
    brace-escaping hell when templates contain heavy JavaScript."""
    result = template
    for key, value in kwargs.items():
        marker = f"__{key.upper()}__"
        if isinstance(value, (dict, list)):
            result = result.replace(
                marker, json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            )
        else:
            result = result.replace(marker, str(value))
    return result


# ── Data loaders ──────────────────────────────────────────────────────────────


def _jload(path: Path) -> list | dict:
    return json.loads(path.read_text())


def _inventory_maps(
    inv_path: Path,
) -> tuple[
    dict[float, str],  # file_number → pkg_name
    dict[float, str],  # file_number → prefix
    dict[float, str],  # file_number → label
    dict[float, int],  # file_number → field_count
]:
    inv = _jload(inv_path)
    f2pkg: dict[float, str] = {}
    f2prefix: dict[float, str] = {}
    f2label: dict[float, str] = {}
    f2fields: dict[float, int] = {}
    for f in inv.get("files", []):
        fn = float(f["file_number"])
        f2pkg[fn] = f.get("package_name") or "(unpackaged)"
        f2prefix[fn] = f.get("package_prefix") or ""
        f2label[fn] = f.get("label", str(fn))
        f2fields[fn] = f.get("field_count", 0)
    return f2pkg, f2prefix, f2label, f2fields


# ── Common HTML header/footer ─────────────────────────────────────────────────

_COMMON_HEAD = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#111827;color:#e5e7eb;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  overflow:hidden;display:flex;flex-direction:column;height:100vh}
#hdr{background:#1f2937;border-bottom:1px solid #374151;
  padding:8px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0}
#hdr-title{font-size:14px;font-weight:600;color:#f3f4f6}
#hdr-sub{font-size:11px;color:#6b7280}
#chart{flex:1;overflow:hidden;position:relative}
svg{display:block}
.tooltip{position:fixed;background:rgba(17,24,39,.96);border:1px solid #374151;
  border-radius:6px;padding:8px 12px;font-size:12px;line-height:1.6;
  pointer-events:none;display:none;max-width:300px;z-index:100;
  box-shadow:0 4px 16px rgba(0,0,0,.5)}
.tooltip b{color:#f3f4f6}
</style></head><body>
<div id="hdr">
  <div id="hdr-title">__TITLE__</div>
  <div id="hdr-sub">__SUBTITLE__</div>
</div>
<div id="chart"></div>
<div class="tooltip" id="tip"></div>"""

_COMMON_FOOT = "</body></html>"


# ══════════════════════════════════════════════════════════════════════════════
# 1. HEATMAP — package × field type count matrix
# ══════════════════════════════════════════════════════════════════════════════

_HEATMAP_JS = """
<script src="https://d3js.org/d3.v7.min.js"></script><script>
const D=__DATA__, TIP=document.getElementById("tip");
const el=document.getElementById("chart");
const W=el.clientWidth, H=el.clientHeight;
const mg={top:30,right:180,bottom:120,left:220};
const iw=W-mg.left-mg.right, ih=H-mg.top-mg.bottom;

const svg=d3.select("#chart").append("svg").attr("width",W).attr("height",H)
  .append("g").attr("transform",`translate(${mg.left},${mg.top})`);

const x=d3.scaleBand().domain(D.types).range([0,iw]).padding(0.08);
const y=d3.scaleBand().domain(D.packages).range([0,ih]).padding(0.06);
const maxV=d3.max(D.cells,d=>d.count)||1;

// Per-type sequential color scale using the type's own color
function cellColor(type,count){
  if(count===0) return "#1f2937";
  const base=D.type_colors[type]||"#4e79a7";
  const r=parseInt(base.slice(1,3),16),g=parseInt(base.slice(3,5),16),b=parseInt(base.slice(5,7),16);
  const t=0.15+0.85*(count/maxV);
  return `rgb(${Math.round(r*t+30*(1-t))},${Math.round(g*t+30*(1-t))},${Math.round(b*t+30*(1-t))})`;
}

// X axis (types)
svg.append("g").attr("transform",`translate(0,${ih})`)
  .call(d3.axisBottom(x).tickSize(0))
  .call(g=>{g.select(".domain").remove();
    g.selectAll("text").attr("y",10).style("fill","#9ca3af").style("font-size","11px")
     .text(t=>D.type_names[t]||t).attr("transform","rotate(-35)").style("text-anchor","end");});

// Y axis (packages)
svg.append("g").call(d3.axisLeft(y).tickSize(0))
  .call(g=>{g.select(".domain").remove();
    g.selectAll("text").style("fill",d=>{
      const dom=D.pkg_domains[d]||"Other";
      return D.domain_colors[dom]||"#9ca3af";
    }).style("font-size","10px");});

// Column totals at top
svg.selectAll(".col-tot").data(D.types).join("text").attr("class","col-tot")
  .attr("x",t=>x(t)+x.bandwidth()/2).attr("y",-10)
  .attr("text-anchor","middle").style("font-size","9px").style("fill","#6b7280")
  .text(t=>{
    const tot=D.cells.filter(c=>c.type===t).reduce((s,c)=>s+c.count,0);
    return d3.format(",d")(tot);
  });

// Cells
svg.selectAll(".cell").data(D.cells).join("rect").attr("class","cell")
  .attr("x",d=>x(d.type)).attr("y",d=>y(d.package))
  .attr("width",x.bandwidth()).attr("height",y.bandwidth())
  .attr("rx",2).attr("fill",d=>cellColor(d.type,d.count))
  .style("stroke","#111827").style("stroke-width",0.5)
  .on("mousemove",(ev,d)=>{
    TIP.style.display="block";
    TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
    TIP.innerHTML=`<b>${d.package}</b><br>Type: ${D.type_names[d.type]||d.type}<br>Fields: ${d3.format(",d")(d.count)}`;
  }).on("mouseleave",()=>TIP.style.display="none");

// Cell labels
svg.selectAll(".clbl").data(D.cells.filter(d=>d.count>0)).join("text").attr("class","clbl")
  .attr("x",d=>x(d.type)+x.bandwidth()/2).attr("y",d=>y(d.package)+y.bandwidth()/2)
  .attr("dominant-baseline","middle").attr("text-anchor","middle")
  .style("font-size",()=>Math.min(10,x.bandwidth()*0.45)+"px")
  .style("fill",d=>d.count>maxV*0.55?"#f3f4f6":"rgba(255,255,255,0.5)")
  .style("pointer-events","none")
  .text(d=>{const bw=x.bandwidth();return bw>30?d3.format(",d")(d.count):"";});

// Row totals on right
svg.selectAll(".row-tot").data(D.packages).join("text").attr("class","row-tot")
  .attr("x",iw+8).attr("y",p=>y(p)+y.bandwidth()/2)
  .attr("dominant-baseline","middle").style("font-size","10px").style("fill","#6b7280")
  .text(p=>{
    const tot=D.cells.filter(c=>c.package===p).reduce((s,c)=>s+c.count,0);
    return d3.format(",d")(tot);
  });

// Legend (type colors)
const leg=svg.append("g").attr("transform",`translate(${iw+60},0)`);
D.types.forEach((t,i)=>{
  const g=leg.append("g").attr("transform",`translate(0,${i*18})`);
  g.append("rect").attr("width",12).attr("height",12).attr("rx",2)
    .attr("fill",D.type_colors[t]||"#888");
  g.append("text").attr("x",16).attr("y",9).style("font-size","10px")
    .style("fill","#9ca3af").text(D.type_names[t]||t);
});
</script>"""


def prep_heatmap(schema_path: Path, top_n: int = 35) -> dict:
    fields: list[dict] = _jload(schema_path)

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
    TYPES_ORDERED = ["F", "P", "S", "D", "N", "M", "W", "C", "K", "V", "DC"]

    # pkg → type → count
    pkg_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in fields:
        pkg = r.get("package") or "(unpackaged)"
        dtype = r.get("datatype_code") or "?"
        pkg_type[pkg][dtype] += 1

    # Top N packages by total field count
    ranked = sorted(pkg_type.items(), key=lambda kv: -sum(kv[1].values()))[:top_n]
    packages = [p for p, _ in ranked]

    # Types present in data
    all_types = [t for t in TYPES_ORDERED if any(t in v for _, v in pkg_type.items())]

    cells = [
        {"package": p, "type": t, "count": pkg_type[p].get(t, 0)}
        for p in packages
        for t in all_types
    ]

    pkg_domains = {p: pkg_domain(p) for p in packages}

    return {
        "packages": packages,
        "types": all_types,
        "type_names": TYPE_NAMES,
        "type_colors": _FIELD_TYPE_COLORS,
        "domain_colors": DOMAIN_COLORS,
        "pkg_domains": pkg_domains,
        "cells": cells,
    }


def build_heatmap(schema_path: Path, output_path: Path, top_n: int = 35) -> None:
    data = prep_heatmap(schema_path, top_n)
    n_pkg = len(data["packages"])
    subtitle = (
        f"Top {n_pkg} packages × {len(data['types'])} field types  "
        f"· {sum(c['count'] for c in data['cells']):,} total fields"
    )
    html = _inject(
        _COMMON_HEAD + _HEATMAP_JS + _COMMON_FOOT,
        title="FileMan — Field Type Heatmap",
        subtitle=subtitle,
        data=data,
    )
    output_path.write_text(html)


# ══════════════════════════════════════════════════════════════════════════════
# 2. CORRELOGRAM — scatter-matrix of per-file numeric attributes
# ══════════════════════════════════════════════════════════════════════════════

_CORRELOGRAM_JS = """
<script src="https://d3js.org/d3.v7.min.js"></script><script>
const D=__DATA__, TIP=document.getElementById("tip");
const VARS=D.variables, N=VARS.length;
const el=document.getElementById("chart");
const SIZE=Math.min((el.clientWidth-40)/N,(el.clientHeight-60)/N);
const PAD=4, INNER=SIZE-2*PAD;

const svg=d3.select("#chart").append("svg")
  .attr("width",SIZE*N+40).attr("height",SIZE*N+40)
  .append("g").attr("transform","translate(20,20)");

// Scales per variable
const scales={};
VARS.forEach(v=>{
  const vals=D.points.map(p=>p[v]).filter(x=>x!=null&&isFinite(x));
  scales[v]=d3.scaleLinear().domain(d3.extent(vals)).range([INNER,0]).nice();
});

const colorScale=d3.scaleOrdinal()
  .domain(Object.keys(D.domain_colors)).range(Object.values(D.domain_colors));

// Cell grid
VARS.forEach((yv,row)=>{
  VARS.forEach((xv,col)=>{
    const g=svg.append("g").attr("transform",`translate(${col*SIZE+PAD},${row*SIZE+PAD})`);

    // Background
    g.append("rect").attr("width",INNER).attr("height",INNER)
      .attr("rx",3).attr("fill","#1f2937").attr("stroke","#374151").attr("stroke-width",0.5);

    if(col===row){
      // Diagonal: histogram
      const vals=D.points.map(p=>p[xv]).filter(x=>x!=null&&isFinite(x));
      const bins=d3.bin().thresholds(15)(vals);
      const hy=d3.scaleLinear().domain([0,d3.max(bins,b=>b.length)]).range([INNER,0]);
      const hx=d3.scaleLinear().domain([bins[0].x0,bins[bins.length-1].x1]).range([0,INNER]);
      g.selectAll("rect").data(bins).join("rect")
        .attr("x",b=>hx(b.x0)).attr("width",b=>Math.max(0,hx(b.x1)-hx(b.x0)-1))
        .attr("y",b=>hy(b.length)).attr("height",b=>INNER-hy(b.length))
        .attr("fill",D.domain_colors["Registration/ADT"]||"#4e79a7").attr("fill-opacity",0.7);
      g.append("text").attr("x",INNER/2).attr("y",INNER-4)
        .attr("text-anchor","middle").style("font-size","9px").style("fill","#6b7280")
        .text(D.var_labels[xv]||xv);
    } else {
      // Off-diagonal: scatter plot
      const xScale=d3.scaleLinear().domain(scales[xv].domain()).range([0,INNER]);
      const yScl=d3.scaleLinear().domain(scales[yv].domain()).range([INNER,0]);

      // Compute Pearson r
      const pts=D.points.filter(p=>p[xv]!=null&&p[yv]!=null&&isFinite(p[xv])&&isFinite(p[yv]));
      const mx=d3.mean(pts,p=>p[xv]), my=d3.mean(pts,p=>p[yv]);
      const num=d3.sum(pts,p=>(p[xv]-mx)*(p[yv]-my));
      const den=Math.sqrt(d3.sum(pts,p=>(p[xv]-mx)**2)*d3.sum(pts,p=>(p[yv]-my)**2));
      const r=den>0?num/den:0;
      const rColor=r>0?"#59a14f":r<0?"#e15759":"#6b7280";

      g.append("text").attr("x",2).attr("y",10)
        .style("font-size","8px").style("fill",rColor).style("font-weight","600")
        .text(`r=${r.toFixed(2)}`);

      g.selectAll("circle").data(pts).join("circle")
        .attr("cx",p=>xScale(p[xv])).attr("cy",p=>yScl(p[yv])).attr("r",2)
        .attr("fill",p=>colorScale(p.domain)||"#4e79a7").attr("fill-opacity",0.55)
        .on("mousemove",(ev,p)=>{
          TIP.style.display="block";
          TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
          TIP.innerHTML=`<b>${p.label}</b><br>${D.var_labels[xv]||xv}: ${d3.format(",d")(p[xv])}<br>${D.var_labels[yv]||yv}: ${d3.format(",d")(p[yv])}<br>Domain: ${p.domain}`;
        }).on("mouseleave",()=>TIP.style.display="none");
    }

    // Axis labels on edges
    if(row===0){
      g.append("text").attr("x",INNER/2).attr("y",-2)
        .attr("text-anchor","middle").style("font-size","8px").style("fill","#4b5563")
        .text(D.var_labels[xv]||xv);
    }
    if(col===0){
      g.append("text").attr("transform",`rotate(-90)`).attr("x",-INNER/2).attr("y",-2)
        .attr("text-anchor","middle").style("font-size","8px").style("fill","#4b5563")
        .text(D.var_labels[yv]||yv);
    }
  });
});

// Domain legend
const legG=svg.append("g").attr("transform",`translate(${SIZE*N+6},0)`);
Object.entries(D.domain_colors).forEach(([dom,col],i)=>{
  const g=legG.append("g").attr("transform",`translate(0,${i*16})`);
  g.append("circle").attr("r",5).attr("cx",5).attr("cy",5).attr("fill",col);
  g.append("text").attr("x",14).attr("y",9).style("font-size","9px").style("fill","#6b7280")
    .text(dom.length>16?dom.slice(0,15)+"…":dom);
});
</script>"""


def prep_correlogram(
    inv_path: Path,
    schema_path: Path | None = None,
    volume_path: Path | None = None,
) -> dict:
    f2pkg, f2prefix, f2label, f2fields = _inventory_maps(inv_path)

    # Entry counts
    f2entries: dict[float, int] = {}
    if volume_path and volume_path.exists():
        for row in _jload(volume_path):
            f2entries[float(row["file_number"])] = row["entry_count"]

    # Type counts per file from schema
    f2pointer: dict[float, int] = defaultdict(int)
    f2set: dict[float, int] = defaultdict(int)
    f2multiple: dict[float, int] = defaultdict(int)
    if schema_path and schema_path.exists():
        for r in _jload(schema_path):
            fn = float(r["file_number"])
            t = r.get("datatype_code", "")
            if t == "P":
                f2pointer[fn] += 1
            elif t == "S":
                f2set[fn] += 1
            elif t == "M":
                f2multiple[fn] += 1

    # Build point list
    points = []
    for fn, fc in f2fields.items():
        if fc == 0:
            continue
        pkg = f2pkg.get(fn, "(unpackaged)")
        prefix = f2prefix.get(fn, "")
        dom = pkg_domain(pkg, prefix)
        points.append(
            {
                "label": f2label.get(fn, str(fn)),
                "domain": dom,
                "field_count": fc,
                "entry_count": f2entries.get(fn, 0),
                "pointer_count": f2pointer.get(fn, 0),
                "set_count": f2set.get(fn, 0),
                "multiple_count": f2multiple.get(fn, 0),
            }
        )

    used_domains = sorted({p["domain"] for p in points})
    active_colors = {d: DOMAIN_COLORS[d] for d in used_domains if d in DOMAIN_COLORS}

    return {
        "variables": [
            "field_count",
            "pointer_count",
            "set_count",
            "multiple_count",
            "entry_count",
        ],
        "var_labels": {
            "field_count": "Fields",
            "entry_count": "Entries (log)",
            "pointer_count": "Pointer fields",
            "set_count": "Set-of-codes fields",
            "multiple_count": "Multiple (sub-file) fields",
        },
        "domain_colors": active_colors,
        "points": points,
    }


def build_correlogram(
    inv_path: Path,
    output_path: Path,
    schema_path: Path | None = None,
    volume_path: Path | None = None,
) -> None:
    data = prep_correlogram(inv_path, schema_path, volume_path)
    subtitle = (
        f"{len(data['points']):,} files · "
        f"{len(data['variables'])} attributes · "
        f"click scatter cells for detail"
    )
    html = _inject(
        _COMMON_HEAD + _CORRELOGRAM_JS + _COMMON_FOOT,
        title="FileMan — File Attribute Correlogram",
        subtitle=subtitle,
        data=data,
    )
    output_path.write_text(html)


# ══════════════════════════════════════════════════════════════════════════════
# 3. WORDCLOUD — field label frequency
# ══════════════════════════════════════════════════════════════════════════════

_WORDCLOUD_JS = """
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-cloud@1.2.7/build/d3.layout.cloud.min.js"></script>
<script>
const D=__DATA__, TIP=document.getElementById("tip");
const el=document.getElementById("chart");
const W=el.clientWidth, H=el.clientHeight;

const colorOf=w=>{
  const c=D.type_colors[w.dominant_type];
  if(!c) return "#6b7280";
  // Desaturate slightly for readability
  const r=parseInt(c.slice(1,3),16),g=parseInt(c.slice(3,5),16),b=parseInt(c.slice(5,7),16);
  const avg=(r+g+b)/3, f=0.6;
  return `rgb(${Math.round(r*f+avg*(1-f))},${Math.round(g*f+avg*(1-f))},${Math.round(b*f+avg*(1-f))})`;
};

// Size scale: map raw count to font size
const maxCount=d3.max(D.words,w=>w.count)||1;
const sizeScale=d3.scaleLinear().domain([1,maxCount]).range([10,80]).clamp(true);

const words=D.words.map(w=>({...w,size:sizeScale(w.count)}));

const layout=d3.layout.cloud()
  .size([W,H])
  .words(words)
  .padding(4)
  .rotate(()=>~~(Math.random()*5)*18-36)
  .font("'Segoe UI', sans-serif")
  .fontWeight(w=>w.count>maxCount*0.1?"700":"400")
  .fontSize(w=>w.size)
  .on("end",draw);

layout.start();

function draw(placedWords){
  const svg=d3.select("#chart").append("svg").attr("width",W).attr("height",H);
  const g=svg.append("g").attr("transform",`translate(${W/2},${H/2})`);

  g.selectAll("text")
    .data(placedWords)
    .join("text")
      .style("font-size",w=>w.size+"px")
      .style("font-family","'Segoe UI', sans-serif")
      .style("font-weight",w=>w.count>maxCount*0.1?"700":"400")
      .style("fill",colorOf)
      .attr("text-anchor","middle")
      .attr("transform",w=>`translate(${w.x},${w.y})rotate(${w.rotate})`)
      .text(w=>w.text)
      .on("mousemove",(ev,w)=>{
        TIP.style.display="block";
        TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
        const tname=D.type_names[w.dominant_type]||w.dominant_type||"?";
        const consistency=w.type_count===1?"consistent":"mixed ("+w.type_count+" types)";
        TIP.innerHTML=`<b>${w.text}</b><br>Occurrences: ${d3.format(",d")(w.count)}<br>Dominant type: ${tname}<br>Type consistency: ${consistency}`;
      })
      .on("mouseleave",()=>TIP.style.display="none");
}

// Legend: type colors
const legSvg=d3.select("#chart").append("svg")
  .style("position","absolute").style("bottom","8px").style("right","8px")
  .attr("width",160).attr("height",Object.keys(D.type_names).length*16+4);
Object.entries(D.type_names).forEach(([code,name],i)=>{
  const g=legSvg.append("g").attr("transform",`translate(4,${i*16+8})`);
  g.append("rect").attr("width",10).attr("height",10).attr("rx",2)
    .attr("fill",D.type_colors[code]||"#6b7280");
  g.append("text").attr("x",14).attr("y",8).style("font-size","9px").style("fill","#6b7280")
    .text(`${code} ${name}`);
});
</script>"""


def prep_wordcloud(schema_path: Path, top_n: int = 200) -> dict:
    fields: list[dict] = _jload(schema_path)

    label_types: dict[str, Counter] = defaultdict(Counter)
    for r in fields:
        lbl = (r.get("field_label") or "").strip().upper()
        if not lbl or len(lbl) < 2:
            continue
        dtype = r.get("datatype_code") or "?"
        label_types[lbl][dtype] += 1

    words = []
    for lbl, type_counts in sorted(
        label_types.items(), key=lambda kv: -sum(kv[1].values())
    )[:top_n]:
        total = sum(type_counts.values())
        dominant_type, _ = type_counts.most_common(1)[0]
        words.append(
            {
                "text": lbl.title(),
                "count": total,
                "dominant_type": dominant_type,
                "type_count": len(type_counts),
            }
        )

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
    }
    return {
        "words": words,
        "type_names": TYPE_NAMES,
        "type_colors": _FIELD_TYPE_COLORS,
    }


def build_wordcloud(schema_path: Path, output_path: Path, top_n: int = 200) -> None:
    data = prep_wordcloud(schema_path, top_n)
    subtitle = (
        f"Top {len(data['words'])} field labels · "
        "size = frequency · color = dominant field type"
    )
    html = _inject(
        _COMMON_HEAD + _WORDCLOUD_JS + _COMMON_FOOT,
        title="FileMan — Field Label Wordcloud",
        subtitle=subtitle,
        data=data,
    )
    output_path.write_text(html)


# ══════════════════════════════════════════════════════════════════════════════
# 4. DENDROGRAM — radial package → file hierarchy
# ══════════════════════════════════════════════════════════════════════════════

_DENDROGRAM_JS = """
<script src="https://d3js.org/d3.v7.min.js"></script><script>
const D=__DATA__, TIP=document.getElementById("tip");
const el=document.getElementById("chart");
const W=el.clientWidth, H=el.clientHeight;
const cx=W/2, cy=H/2;
const R=Math.min(W,H)/2-120;

const svg=d3.select("#chart").append("svg").attr("width",W).attr("height",H);

// Zoom + pan
const zoomG=svg.append("g").attr("transform",`translate(${cx},${cy})`);
svg.call(d3.zoom().scaleExtent([0.3,6]).on("zoom",ev=>{
  zoomG.attr("transform",ev.transform.translate(cx,cy));
}));

// Cluster layout
const root=d3.hierarchy(D.tree)
  .sum(d=>d.value||1)
  .sort((a,b)=>b.value-a.value);

d3.cluster().size([2*Math.PI,R])(root);

const domColor=dom=>D.domain_colors[dom]||"#6b7280";
const nodeColor=d=>{
  let n=d;
  while(n){if(n.data.domain) return domColor(n.data.domain); n=n.parent;}
  return "#6b7280";
};

// Radial line
const radialLine=d3.linkRadial().angle(d=>d.x).radius(d=>d.y);

// Links
zoomG.append("g").attr("fill","none")
  .selectAll("path").data(root.links()).join("path")
    .attr("d",radialLine)
    .attr("stroke",d=>nodeColor(d.target))
    .attr("stroke-opacity",d=>d.target.depth===1?0.6:0.25)
    .attr("stroke-width",d=>d.target.depth===1?1.5:0.6);

// Nodes
const node=zoomG.append("g")
  .selectAll("g").data(root.descendants()).join("g")
    .attr("transform",d=>`rotate(${d.x*180/Math.PI-90}) translate(${d.y},0)`);

const rScale=d3.scaleSqrt().domain([0,d3.max(root.leaves(),d=>d.value)||1]).range([2,10]);

node.append("circle")
  .attr("r",d=>d.children?4:rScale(d.value||1))
  .attr("fill",nodeColor)
  .attr("fill-opacity",d=>d.depth===0?0:d.children?0.9:0.75)
  .attr("stroke",d=>d.children?"#1f2937":"none")
  .attr("stroke-width",1.5)
  .style("cursor","pointer")
  .on("mousemove",(ev,d)=>{
    TIP.style.display="block";
    TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
    TIP.innerHTML=d.data.tooltip||`<b>${d.data.name}</b>`;
  })
  .on("mouseleave",()=>TIP.style.display="none");

// Labels
node.append("text")
  .attr("dy","0.31em")
  .attr("x",d=>d.x<Math.PI===!d.children?6:-6)
  .attr("text-anchor",d=>d.x<Math.PI===!d.children?"start":"end")
  .attr("transform",d=>d.x>=Math.PI?"rotate(180)":null)
  .style("font-size",d=>d.depth===1?"10px":"8px")
  .style("font-weight",d=>d.depth===1?"600":"400")
  .style("fill",nodeColor)
  .style("pointer-events","none")
  .text(d=>{
    if(d.depth===0) return "";
    const name=d.data.name;
    if(d.depth===1) return name.length>22?name.slice(0,20)+"…":name;
    return name.length>20?name.slice(0,18)+"…":name;
  });

// Legend
const legG=svg.append("g").attr("transform","translate(12,28)");
Object.entries(D.domain_colors).forEach(([dom,col],i)=>{
  const g=legG.append("g").attr("transform",`translate(0,${i*16})`);
  g.append("circle").attr("r",5).attr("cx",5).attr("cy",5).attr("fill",col);
  g.append("text").attr("x",14).attr("y",9).style("font-size","9px")
    .style("fill","#6b7280").text(dom.length>18?dom.slice(0,17)+"…":dom);
});

// Hint
svg.append("text").attr("x",W-8).attr("y",H-6).attr("text-anchor","end")
  .style("font-size","10px").style("fill","#374151")
  .text("scroll to zoom · drag to pan");
</script>"""


def prep_dendrogram(inv_path: Path, max_files: int = 400) -> dict:
    f2pkg, f2prefix, f2label, f2fields = _inventory_maps(inv_path)

    # Group files by package
    pkg_files: dict[str, list[dict]] = defaultdict(list)
    for fn, fc in sorted(f2fields.items(), key=lambda kv: -kv[1]):
        pkg = f2pkg.get(fn, "(unpackaged)")
        pkg_files[pkg].append(
            {
                "file_number": fn,
                "label": f2label.get(fn, str(fn)),
                "field_count": fc,
            }
        )

    # Sort packages by total field count, take top packages until max_files
    pkg_ranked = sorted(
        pkg_files.items(), key=lambda kv: -sum(f["field_count"] for f in kv[1])
    )
    file_budget = max_files
    pkg_included = []
    for pkg_name, files in pkg_ranked:
        if file_budget <= 0:
            break
        take = files[:file_budget]
        pkg_included.append((pkg_name, take))
        file_budget -= len(take)

    children = []
    for pkg_name, files in pkg_included:
        prefix = f2prefix.get(next((f["file_number"] for f in files), -1.0), "")
        domain = pkg_domain(pkg_name, prefix)
        file_nodes = [
            {
                "name": f"{f['label']} (#{f['file_number']:.0f})",
                "value": max(f["field_count"], 1),
                "domain": domain,
                "tooltip": (
                    f"<b>{f['label']}</b><br>"
                    f"File #: {f['file_number']:.0f}<br>"
                    f"Package: {pkg_name}<br>"
                    f"Fields: {f['field_count']:,}"
                ),
            }
            for f in files
        ]
        total = sum(f["field_count"] for f in files)
        children.append(
            {
                "name": pkg_name,
                "domain": domain,
                "children": file_nodes,
                "tooltip": (
                    f"<b>{pkg_name}</b><br>"
                    f"Domain: {domain}<br>"
                    f"Files shown: {len(files)}<br>"
                    f"Total fields: {total:,}"
                ),
            }
        )

    used_domains = sorted({c["domain"] for c in children})
    active_colors = {d: DOMAIN_COLORS[d] for d in used_domains if d in DOMAIN_COLORS}

    return {
        "tree": {"name": "VistA", "children": children},
        "domain_colors": active_colors,
    }


def build_dendrogram(inv_path: Path, output_path: Path, max_files: int = 400) -> None:
    data = prep_dendrogram(inv_path, max_files)
    n_leaves = sum(len(c.get("children", [])) for c in data["tree"]["children"])
    n_pkgs = len(data["tree"]["children"])
    subtitle = f"{n_pkgs} packages · {n_leaves} files · scroll to zoom · drag to pan"
    html = _inject(
        _COMMON_HEAD + _DENDROGRAM_JS + _COMMON_FOOT,
        title="FileMan — Package / File Dendrogram",
        subtitle=subtitle,
        data=data,
    )
    output_path.write_text(html)


# ══════════════════════════════════════════════════════════════════════════════
# 5. SANKEY — cross-package pointer flow
# ══════════════════════════════════════════════════════════════════════════════

_SANKEY_JS = """
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
<script>
const D=__DATA__, TIP=document.getElementById("tip");
const el=document.getElementById("chart");
const W=el.clientWidth, H=el.clientHeight;
const mg={top:20,right:160,bottom:20,left:160};
const iw=W-mg.left-mg.right, ih=H-mg.top-mg.bottom;

const svg=d3.select("#chart").append("svg").attr("width",W).attr("height",H);
const g=svg.append("g").attr("transform",`translate(${mg.left},${mg.top})`);

const domColor=dom=>D.domain_colors[dom]||"#6b7280";

// Build sankey
const sankey=d3.sankey()
  .nodeId(d=>d.index)
  .nodeWidth(18)
  .nodePadding(10)
  .extent([[0,0],[iw,ih]])
  .nodeAlign(d3.sankeyJustify);

const {nodes,links}=sankey({
  nodes:D.nodes.map(d=>Object.assign({},d)),
  links:D.links.map(d=>Object.assign({},d)),
});

// Links
const linkG=g.append("g").attr("fill","none");
linkG.selectAll("path").data(links).join("path")
  .attr("d",d3.sankeyLinkHorizontal())
  .attr("stroke",l=>domColor(D.nodes[l.source.index].domain))
  .attr("stroke-width",l=>Math.max(1,l.width))
  .attr("stroke-opacity",0.35)
  .on("mousemove",(ev,l)=>{
    TIP.style.display="block";
    TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
    const sn=D.nodes[l.source.index], tn=D.nodes[l.target.index];
    TIP.innerHTML=`<b>${sn.name}</b> → <b>${tn.name}</b><br>Pointer fields: ${d3.format(",d")(l.value)}`;
  })
  .on("mouseleave",()=>TIP.style.display="none");

// Nodes
const nodeG=g.append("g");
nodeG.selectAll("rect").data(nodes).join("rect")
  .attr("x",d=>d.x0).attr("y",d=>d.y0)
  .attr("width",d=>d.x1-d.x0).attr("height",d=>Math.max(1,d.y1-d.y0))
  .attr("fill",d=>domColor(D.nodes[d.index].domain))
  .attr("rx",2).attr("fill-opacity",0.9)
  .on("mousemove",(ev,d)=>{
    TIP.style.display="block";
    TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
    const nd=D.nodes[d.index];
    TIP.innerHTML=`<b>${nd.name}</b><br>Domain: ${nd.domain}<br>Total flow: ${d3.format(",d")(d.value)} pointer fields`;
  })
  .on("mouseleave",()=>TIP.style.display="none");

// Node labels
nodeG.selectAll("text").data(nodes).join("text")
  .attr("x",d=>d.x0<iw/2?d.x1+6:d.x0-6)
  .attr("y",d=>(d.y1+d.y0)/2)
  .attr("dy","0.35em")
  .attr("text-anchor",d=>d.x0<iw/2?"start":"end")
  .style("font-size","10px")
  .style("fill",d=>domColor(D.nodes[d.index].domain))
  .style("pointer-events","none")
  .text(d=>{
    const n=D.nodes[d.index].name;
    return n.length>22?n.slice(0,20)+"…":n;
  });

// Legend
const legG=svg.append("g").attr("transform",`translate(${W-155},28)`);
Object.entries(D.domain_colors).forEach(([dom,col],i)=>{
  const g2=legG.append("g").attr("transform",`translate(0,${i*16})`);
  g2.append("rect").attr("width",10).attr("height",10).attr("rx",2).attr("fill",col);
  g2.append("text").attr("x",14).attr("y",8).style("font-size","9px").style("fill","#6b7280")
    .text(dom.length>18?dom.slice(0,17)+"…":dom);
});
</script>"""


def prep_sankey(
    schema_path: Path,
    inv_path: Path | None = None,
    min_flow: int = 3,
    top_n_pkgs: int = 20,
) -> dict:
    fields: list[dict] = _jload(schema_path)

    f2pkg: dict[float, str] = {}
    f2prefix: dict[float, str] = {}
    if inv_path and inv_path.exists():
        _m = _inventory_maps(inv_path)
        f2pkg, f2prefix = _m[0], _m[1]

    # Count pointer fields: src_pkg → tgt_pkg → count
    flow: dict[tuple[str, str], int] = Counter()
    for r in fields:
        if r.get("datatype_code") != "P":
            continue
        src_fn = float(r["file_number"])
        tgt_fn = r.get("pointer_file")
        if tgt_fn is None:
            continue
        src_pkg = f2pkg.get(src_fn) or r.get("package") or "(unpackaged)"
        tgt_pkg = f2pkg.get(float(tgt_fn), "(unpackaged)")
        if src_pkg == tgt_pkg:
            continue  # skip intra-package (too many)
        flow[(src_pkg, tgt_pkg)] += 1

    # Keep top packages by total flow
    pkg_volume: Counter[str] = Counter()
    for (s, t), v in flow.items():
        pkg_volume[s] += v
        pkg_volume[t] += v
    top_pkgs = {p for p, _ in pkg_volume.most_common(top_n_pkgs)}

    edges = [
        (s, t, v)
        for (s, t), v in flow.items()
        if v >= min_flow and s in top_pkgs and t in top_pkgs
    ]

    # Build node list
    all_pkgs = sorted({p for s, t, _ in edges for p in (s, t)})
    idx = {p: i for i, p in enumerate(all_pkgs)}

    nodes = [
        {
            "index": i,
            "name": p,
            "domain": pkg_domain(
                p,
                f2prefix.get(
                    next((fn for fn, pkg in f2pkg.items() if pkg == p), -1.0), ""
                ),
            ),
        }
        for i, p in enumerate(all_pkgs)
    ]
    links = [{"source": idx[s], "target": idx[t], "value": v} for s, t, v in edges]

    used_domains = sorted({n["domain"] for n in nodes})
    active_colors = {d: DOMAIN_COLORS[d] for d in used_domains if d in DOMAIN_COLORS}

    return {
        "nodes": nodes,
        "links": links,
        "domain_colors": active_colors,
    }


def build_sankey(
    schema_path: Path,
    output_path: Path,
    inv_path: Path | None = None,
    min_flow: int = 3,
    top_n_pkgs: int = 20,
) -> None:
    data = prep_sankey(schema_path, inv_path, min_flow, top_n_pkgs)
    subtitle = (
        f"{len(data['nodes'])} packages · {len(data['links'])} flows · "
        f"link width = number of cross-package pointer fields"
    )
    html = _inject(
        _COMMON_HEAD + _SANKEY_JS + _COMMON_FOOT,
        title="FileMan — Cross-Package Pointer Flow (Sankey)",
        subtitle=subtitle,
        data=data,
    )
    output_path.write_text(html)


# ══════════════════════════════════════════════════════════════════════════════
# 6. HIERARCHICAL EDGE BUNDLING — file pointer coupling
# ══════════════════════════════════════════════════════════════════════════════

_BUNDLE_JS = """
<script src="https://d3js.org/d3.v7.min.js"></script><script>
const D=__DATA__, TIP=document.getElementById("tip");
const el=document.getElementById("chart");
const W=el.clientWidth, H=el.clientHeight;
const R=Math.min(W,H)/2-100, LW=R*0.12;
const cx=W/2, cy=H/2;
const TENSION=0.85;

const svg=d3.select("#chart").append("svg").attr("width",W).attr("height",H);
const zoomG=svg.append("g").attr("transform",`translate(${cx},${cy})`);
svg.call(d3.zoom().scaleExtent([0.3,5]).on("zoom",ev=>{
  zoomG.attr("transform",ev.transform.translate(cx,cy));
}));

// Build hierarchy from flat node list grouped by package
const hierarchyData={name:"root",children:[]};
const pkgMap={};
D.nodes.forEach(n=>{
  if(!pkgMap[n.package]){
    pkgMap[n.package]={name:n.package,domain:n.domain,children:[]};
    hierarchyData.children.push(pkgMap[n.package]);
  }
  pkgMap[n.package].children.push({name:n.id,label:n.label,domain:n.domain,children:[]});
});

const root=d3.hierarchy(hierarchyData).sort((a,b)=>d3.ascending(a.data.name,b.data.name));
d3.cluster().size([2*Math.PI,R-LW])(root);

const leaves=root.leaves();
const nodeById=Object.fromEntries(leaves.map(l=>[l.data.name,l]));
const domColor=dom=>D.domain_colors[dom]||"#6b7280";

// Radial position helpers
const radialPoint=(ang,r)=>[Math.sin(ang)*r, -Math.cos(ang)*r];

// Package arcs
const pkgNodes=root.children||[];
const arc=d3.arc();
zoomG.append("g").attr("fill","none").attr("stroke-width",0)
  .selectAll("path")
  .data(pkgNodes)
  .join("path")
    .attr("d",d=>{
      const pkgLeaves=d.leaves();
      if(pkgLeaves.length<2) return null;
      const angles=pkgLeaves.map(l=>l.x).sort((a,b)=>a-b);
      const da=(angles[angles.length-1]-angles[0]);
      if(da>Math.PI*1.9) return null;
      const pad=0.01;
      return arc({
        innerRadius:R-LW+2, outerRadius:R+2,
        startAngle:angles[0]-pad, endAngle:angles[angles.length-1]+pad
      });
    })
    .attr("fill",d=>domColor(d.data.domain))
    .attr("fill-opacity",0.35)
    .on("mousemove",(ev,d)=>{
      TIP.style.display="block";
      TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
      TIP.innerHTML=`<b>${d.data.name}</b><br>Domain: ${d.data.domain}<br>Files: ${d.leaves().length}`;
    })
    .on("mouseleave",()=>TIP.style.display="none");

// Package labels
zoomG.selectAll(".pkg-lbl").data(pkgNodes).join("text").attr("class","pkg-lbl")
  .each(function(d){
    const pkgLeaves=d.leaves();
    if(!pkgLeaves.length) return;
    const midAng=(pkgLeaves[0].x+pkgLeaves[pkgLeaves.length-1].x)/2;
    const pos=radialPoint(midAng,R+10);
    d3.select(this)
      .attr("transform",`translate(${pos[0]},${pos[1]})`)
      .attr("text-anchor",Math.sin(midAng)>0?"start":"end")
      .style("font-size","9px").style("font-weight","600")
      .style("fill",domColor(d.data.domain)).style("pointer-events","none")
      .text(d.data.name.length>16?d.data.name.slice(0,14)+"…":d.data.name);
  });

// Bundled edges
const lineRadial=d3.lineRadial().curve(d3.curveBundle.beta(TENSION))
  .radius(d=>d.y).angle(d=>d.x);

const edgeG=zoomG.append("g").attr("fill","none");

let hoveredNode=null;
function renderEdges(highlightId=null){
  edgeG.selectAll("path").remove();
  D.links.forEach(lk=>{
    const src=nodeById[lk.source], tgt=nodeById[lk.target];
    if(!src||!tgt) return;
    const isHigh=highlightId&&(lk.source===highlightId||lk.target===highlightId);
    const path=src.path(tgt);
    edgeG.append("path")
      .datum(path)
      .attr("d",lineRadial)
      .attr("stroke",isHigh?domColor(src.data.domain):"#374151")
      .attr("stroke-opacity",isHigh?0.8:0.12)
      .attr("stroke-width",isHigh?1.5:0.6);
  });
}
renderEdges();

// Leaf nodes
const leafG=zoomG.append("g");
leafG.selectAll("circle").data(leaves).join("circle")
  .attr("transform",d=>`rotate(${d.x*180/Math.PI-90}) translate(${d.y},0)`)
  .attr("r",3).attr("fill",d=>domColor(d.data.domain)).attr("fill-opacity",0.8)
  .style("cursor","pointer")
  .on("mousemove",(ev,d)=>{
    TIP.style.display="block";
    TIP.style.left=(ev.clientX+14)+"px";TIP.style.top=(ev.clientY-10)+"px";
    const outgoing=D.links.filter(l=>l.source===d.data.name).length;
    const incoming=D.links.filter(l=>l.target===d.data.name).length;
    TIP.innerHTML=`<b>${d.data.label||d.data.name}</b><br>Package: ${d.data.domain}<br>Outgoing pointers: ${outgoing}<br>Incoming pointers: ${incoming}`;
  })
  .on("mouseleave",()=>TIP.style.display="none")
  .on("click",(ev,d)=>{
    if(hoveredNode===d.data.name){hoveredNode=null;renderEdges();}
    else{hoveredNode=d.data.name;renderEdges(hoveredNode);}
  });

// Leaf labels (only outer ring, angle-appropriate)
leafG.selectAll("text").data(leaves.filter(d=>{
  const outgoing=D.links.filter(l=>l.source===d.data.name).length;
  const incoming=D.links.filter(l=>l.target===d.data.name).length;
  return outgoing+incoming>=3;
})).join("text")
  .attr("dy","0.31em")
  .attr("transform",d=>{
    const deg=d.x*180/Math.PI-90;
    return `rotate(${deg}) translate(${d.y+8},0)${deg>90&&deg<270?"rotate(180)":""}`;
  })
  .attr("text-anchor",d=>{const deg=d.x*180/Math.PI-90; return deg>90&&deg<270?"end":"start";})
  .style("font-size","7px").style("fill",d=>domColor(d.data.domain))
  .style("pointer-events","none")
  .text(d=>{const lbl=d.data.label||d.data.name; return lbl.length>16?lbl.slice(0,14)+"…":lbl;});

// Domain legend
const legG=svg.append("g").attr("transform","translate(10,28)");
Object.entries(D.domain_colors).forEach(([dom,col],i)=>{
  const g2=legG.append("g").attr("transform",`translate(0,${i*16})`);
  g2.append("circle").attr("r",5).attr("cx",5).attr("cy",5).attr("fill",col);
  g2.append("text").attr("x",14).attr("y",9).style("font-size","9px").style("fill","#6b7280")
    .text(dom.length>18?dom.slice(0,17)+"…":dom);
});
svg.append("text").attr("x",W-8).attr("y",H-6).attr("text-anchor","end")
  .style("font-size","10px").style("fill","#374151")
  .text("click a node to highlight its connections · scroll to zoom");
</script>"""


def prep_bundle(
    schema_path: Path,
    inv_path: Path | None = None,
    max_files: int = 150,
    min_edges: int = 2,
) -> dict:
    fields: list[dict] = _jload(schema_path)

    f2pkg: dict[float, str] = {}
    f2prefix: dict[float, str] = {}
    f2label: dict[float, str] = {}
    if inv_path and inv_path.exists():
        m = _inventory_maps(inv_path)
        f2pkg, f2prefix, f2label = m[0], m[1], m[2]

    # Count edges per file (in+out degree)
    file_degree: Counter[float] = Counter()
    raw_edges: list[tuple[float, float]] = []
    for r in fields:
        if r.get("datatype_code") != "P":
            continue
        src_fn = float(r["file_number"])
        tgt_fn = r.get("pointer_file")
        if tgt_fn is None:
            continue
        tgt_fn = float(tgt_fn)
        raw_edges.append((src_fn, tgt_fn))
        file_degree[src_fn] += 1
        file_degree[tgt_fn] += 1

    # Keep top files by degree
    top_files = {fn for fn, _ in file_degree.most_common(max_files)}

    edges = list(
        {(s, t) for s, t in raw_edges if s in top_files and t in top_files and s != t}
    )

    # Build node list
    all_file_nums = sorted(top_files)
    nodes = []
    for fn in all_file_nums:
        pkg = f2pkg.get(fn, "(unpackaged)")
        prefix = f2prefix.get(fn, "")
        dom = pkg_domain(pkg, prefix)
        nodes.append(
            {
                "id": str(fn),
                "label": f2label.get(fn, f"#{fn:.0f}"),
                "package": pkg,
                "domain": dom,
            }
        )

    links = [{"source": str(s), "target": str(t)} for s, t in edges]

    used_domains = sorted({n["domain"] for n in nodes})
    active_colors = {d: DOMAIN_COLORS[d] for d in used_domains if d in DOMAIN_COLORS}

    return {
        "nodes": nodes,
        "links": links,
        "domain_colors": active_colors,
    }


def build_bundle(
    schema_path: Path,
    output_path: Path,
    inv_path: Path | None = None,
    max_files: int = 150,
) -> None:
    data = prep_bundle(schema_path, inv_path, max_files)
    subtitle = (
        f"{len(data['nodes'])} files · {len(data['links'])} pointer edges · "
        "click a node to highlight its connections · scroll to zoom"
    )
    html = _inject(
        _COMMON_HEAD + _BUNDLE_JS + _COMMON_FOOT,
        title="FileMan — File Pointer Coupling (Edge Bundle)",
        subtitle=subtitle,
        data=data,
    )
    output_path.write_text(html)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def _out(input_path: Path, suffix: str) -> Path:
    return input_path.parent / f"viz_{suffix}.html"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # heatmap
    sh = sub.add_parser("heatmap", help="Package × field-type count heatmap")
    sh.add_argument("--input", "-i", type=Path, required=True, help="all_fields.json")
    sh.add_argument("--output", "-o", type=Path)
    sh.add_argument(
        "--top",
        type=int,
        default=35,
        metavar="N",
        help="Top N packages to show (default 35)",
    )

    # correlogram
    sc = sub.add_parser("correlogram", help="Scatter-matrix of per-file attributes")
    sc.add_argument("--input", "-i", type=Path, required=True, help="inventory.json")
    sc.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="all_fields.json (for pointer/set/multiple counts)",
    )
    sc.add_argument(
        "--volume", type=Path, default=None, help="file_volume.json (for entry counts)"
    )
    sc.add_argument("--output", "-o", type=Path)

    # wordcloud
    sw = sub.add_parser("wordcloud", help="Field label frequency wordcloud")
    sw.add_argument("--input", "-i", type=Path, required=True, help="all_fields.json")
    sw.add_argument("--output", "-o", type=Path)
    sw.add_argument(
        "--top",
        type=int,
        default=200,
        metavar="N",
        help="Top N labels to include (default 200)",
    )

    # dendrogram
    sd = sub.add_parser("dendrogram", help="Radial dendrogram: packages → files")
    sd.add_argument("--input", "-i", type=Path, required=True, help="inventory.json")
    sd.add_argument("--output", "-o", type=Path)
    sd.add_argument(
        "--max-files",
        type=int,
        default=400,
        metavar="N",
        help="Max files to display (default 400)",
    )

    # sankey
    sk = sub.add_parser("sankey", help="Cross-package pointer flow (Sankey diagram)")
    sk.add_argument("--input", "-i", type=Path, required=True, help="all_fields.json")
    sk.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help="inventory.json (for package grouping)",
    )
    sk.add_argument("--output", "-o", type=Path)
    sk.add_argument(
        "--min-flow",
        type=int,
        default=3,
        metavar="N",
        help="Min pointer fields for a link to appear (default 3)",
    )
    sk.add_argument(
        "--top-pkgs",
        type=int,
        default=20,
        metavar="N",
        help="Top N packages by flow volume (default 20)",
    )

    # bundle
    sb = sub.add_parser(
        "bundle", help="Hierarchical edge bundling: file pointer coupling"
    )
    sb.add_argument("--input", "-i", type=Path, required=True, help="all_fields.json")
    sb.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help="inventory.json (for package grouping)",
    )
    sb.add_argument("--output", "-o", type=Path)
    sb.add_argument(
        "--max-files",
        type=int,
        default=150,
        metavar="N",
        help="Max files to include (default 150)",
    )

    args = p.parse_args(argv)

    # Resolve paths
    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return 1

    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else _out(input_path, args.cmd)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Viz:    {args.cmd}")
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")

    if args.cmd == "heatmap":
        build_heatmap(input_path, output_path, top_n=args.top)

    elif args.cmd == "correlogram":
        schema = args.schema.expanduser().resolve() if args.schema else None
        volume = args.volume.expanduser().resolve() if args.volume else None
        build_correlogram(input_path, output_path, schema, volume)

    elif args.cmd == "wordcloud":
        build_wordcloud(input_path, output_path, top_n=args.top)

    elif args.cmd == "dendrogram":
        build_dendrogram(input_path, output_path, max_files=args.max_files)

    elif args.cmd == "sankey":
        inv = args.inventory.expanduser().resolve() if args.inventory else None
        build_sankey(input_path, output_path, inv, args.min_flow, args.top_pkgs)

    elif args.cmd == "bundle":
        inv = args.inventory.expanduser().resolve() if args.inventory else None
        build_bundle(input_path, output_path, inv, args.max_files)

    size_kb = output_path.stat().st_size // 1024
    print(f"Done.   {size_kb} KB → open in browser")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
