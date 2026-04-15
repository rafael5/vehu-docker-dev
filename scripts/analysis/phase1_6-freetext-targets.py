"""
Phase 1.6 — Free-Text Normalization Targets (feeds phase 7)
===========================================================
Goal: for each phase-3 hub file, enumerate its FREE TEXT fields and rank
them as candidates for phase-7 normalization.

A "hub file" is a file with many inbound pointers (see output/phase3/
hub_files.csv). Free-text fields on hubs are the highest-leverage targets
because text-as-string values on widely-referenced files propagate
ambiguity throughout the corpus.

Heuristics used to score a candidate:
    - Has input transform (^DD(file,field,1) non-empty) → transform
      suggests structured content hiding in text (often a pattern-matcher).
    - Has description (^DD(file,field,21,...)) → human-documented intent.
    - Name contains date/code/id/number hints → likely structured.

Inputs:
    output/phase3/hub_files.csv
Outputs (output/phase1_6/):
    freetext_candidates.csv
    freetext_summary.json
    phase1_6-freetext-report.md

Requires VEHU container (YDB connection).
"""

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from vista_fm_browser.connection import YdbConnection  # noqa: E402
from vista_fm_browser.data_dictionary import DataDictionary  # noqa: E402
from vista_fm_browser.type_codes import decompose  # noqa: E402

HUBS_CSV = REPO / "output" / "phase3" / "hub_files.csv"
OUTPUT_DIR = REPO / "output" / "phase1_6"

# Hints that a FREE TEXT field likely carries structured content worth
# normalizing. Case-insensitive substring match on field label.
STRUCTURED_HINTS = {
    "date", "time", "code", "id", "number", "ssn", "phone", "zip",
    "address", "postal", "icd", "cpt", "ndc", "account",
}


def load_hub_files() -> list[dict]:
    if not HUBS_CSV.exists():
        raise SystemExit(f"Phase-3 hub_files.csv not found: {HUBS_CSV}")
    with HUBS_CSV.open() as f:
        return list(csv.DictReader(f))


def score_candidate(
    field_label: str, input_transform: str, description_lines: list[str]
) -> tuple[int, list[str]]:
    """Return (score, reasons) for a FREE TEXT field candidate."""
    score = 0
    reasons: list[str] = []
    lbl_low = field_label.lower()
    for hint in STRUCTURED_HINTS:
        if hint in lbl_low:
            score += 2
            reasons.append(f"label contains '{hint}'")
            break  # only count once
    if input_transform:
        score += 2
        reasons.append("has input transform")
    if description_lines:
        score += 1
        reasons.append("has description")
    return score, reasons


def _fm_sub(num: float) -> str:
    """Format a FileMan-canonical subscript: int if integer, else plain decimal."""
    if num == int(num):
        return str(int(num))
    return str(num)


def collect_freetext_fields(
    conn: YdbConnection, hub_files: list[dict]
) -> list[dict]:
    """Return one row per FREE TEXT field on each hub file."""
    dd = DataDictionary(conn)
    candidates: list[dict] = []
    for h in hub_files:
        file_num = float(h["file_number"])
        fd = dd.get_file(file_num)
        if fd is None:
            continue
        fn_str = _fm_sub(file_num)
        for fld in fd.fields.values():
            ts = decompose(fld.raw_type)
            if ts.base != "F":
                continue
            # Read ^DD(f,fld,1) directly — FieldAttributes falls back to
            # title when node 1 is empty, which inflates transform-present.
            fld_str = _fm_sub(fld.field_number)
            input_transform = conn.get("^DD", [fn_str, fld_str, "1"]) or ""
            description: list[str] = []
            for n in conn.subscripts("^DD", [fn_str, fld_str, "21", ""]):
                line = conn.get("^DD", [fn_str, fld_str, "21", n, "0"])
                if line:
                    description.append(line)
            score, reasons = score_candidate(
                fld.label, input_transform, description
            )
            candidates.append({
                "hub_file_number": file_num,
                "hub_file_label": h["label"],
                "hub_package": h["package"],
                "hub_inbound_count": int(h["inbound_count"]),
                "field_number": fld.field_number,
                "field_label": fld.label,
                "raw_type": fld.raw_type,
                "modifiers": ",".join(sorted(ts.modifiers)),
                "required": ts.required,
                "has_input_transform": bool(input_transform),
                "has_description": bool(description),
                "score": score,
                "reasons": "; ".join(reasons),
            })
    return candidates


def write_candidates_csv(cands: list[dict], path: Path) -> None:
    if not cands:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cands[0].keys()))
        w.writeheader()
        w.writerows(cands)


def write_report(
    cands: list[dict], summary: dict, path: Path
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    top = sorted(cands, key=lambda c: (-c["score"], -c["hub_inbound_count"]))[:30]
    lines = [
        "# Phase 1.6 — Free-Text Normalization Targets",
        "",
        f"_Generated {ts}_",
        "",
        "Feeder report for phase 7. Ranks FREE TEXT fields on phase-3 hub",
        "files by a composite score (label hints + input transform + description).",
        "",
        "## Summary",
        "",
        f"- Hub files analyzed: **{summary['hubs_analyzed']}** "
        f"(from `output/phase3/hub_files.csv`)",
        f"- FREE TEXT fields on hubs: **{summary['freetext_total']:,}**",
        f"- Scored ≥3 (high-interest): **{summary['high_score']:,}**",
        f"- With input transform: **{summary['with_transform']:,}**",
        f"- With description: **{summary['with_description']:,}**",
        "",
        "## Top 30 candidates",
        "",
        "| Rank | File | Field | Score | Reasons |",
        "|-----:|:-----|:------|------:|:--------|",
    ]
    for i, c in enumerate(top, 1):
        lines.append(
            f"| {i} | {c['hub_file_label']} ({c['hub_file_number']}) "
            f"| {c['field_label']} ({c['field_number']}) "
            f"| {c['score']} | {c['reasons']} |"
        )
    lines += [
        "",
        "## Scoring rules",
        "",
        "- Label hint match (date/time/code/id/number/...): +2 (once)",
        "- Has input transform: +2 (VEHU instance has none populated — "
        "all scores reflect label+description only)",
        "- Has description: +1",
        "",
        "## VEHU data-quality note",
        "",
        "`^DD(file, field, 1)` — the INPUT TRANSFORM node — is empty for "
        "every FREE TEXT field on every hub file in this VEHU instance. "
        "This is expected for a dev/test VistA; production instances carry "
        "M-code input validators here that would dramatically sharpen "
        "scoring. When phase 7 runs against real VA data, re-run this "
        "script to pick up the transform signal.",
        "",
        "## Next step (phase 7)",
        "",
        "Phase 7 should use the CSV as its primary target list, sorted by "
        "`score` DESC then `hub_inbound_count` DESC. Per `DOWNSTREAM-RULES.md` "
        "rule 2, carry hub package + confidence context forward when "
        "reporting candidates.",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    hubs = load_hub_files()
    with YdbConnection.connect() as conn:
        cands = collect_freetext_fields(conn, hubs)
    score_dist = Counter(c["score"] for c in cands)
    summary = {
        "hubs_analyzed": len(hubs),
        "freetext_total": len(cands),
        "high_score": sum(1 for c in cands if c["score"] >= 3),
        "with_transform": sum(1 for c in cands if c["has_input_transform"]),
        "with_description": sum(1 for c in cands if c["has_description"]),
        "score_distribution": dict(sorted(score_dist.items())),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_candidates_csv(cands, OUTPUT_DIR / "freetext_candidates.csv")
    (OUTPUT_DIR / "freetext_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    write_report(cands, summary, OUTPUT_DIR / "phase1_6-freetext-report.md")
    print(f"Hubs analyzed: {summary['hubs_analyzed']}")
    print(f"FREE TEXT fields on hubs: {summary['freetext_total']:,}")
    print(f"High-score (>=3): {summary['high_score']:,}")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
