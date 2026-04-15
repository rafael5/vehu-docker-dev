"""Package attribution heuristics for unowned FileMan files.

Phase 1 leaves ~58% of files without an owning package because the PACKAGE
file (^DIC(9.4)) FILE multiple is incomplete for many VistA installations.
This module attributes those files to packages by combining three signals:

Heuristic C — Namespace prefix match
    Each file's global root carries a namespace prefix (e.g. ^PSDRUG( → PS).
    Match against the longest package prefix that is a prefix of the
    namespace. PS → PHARMACY, MAG → IMAGING, IBE → IB (INTEGRATED BILLING).

Heuristic A1 — Empirical number-range match
    From already-attributed files, compute each package's (min, max, density)
    file-number envelope. Attribute an unowned file whose number falls inside
    exactly one package's envelope.

Heuristic A2 — Canonical number-range fallback
    For files in the well-known VistA number ranges (e.g. 2.x = REGISTRATION
    patient files, 50.x = PHARMACY) apply a small curated mapping as a last
    resort.

Confidence levels:
    high   prefix match exact (namespace == package prefix)
    med    longest-prefix match (namespace starts with package prefix)
    med    empirical range with ≥3 anchor files in that package
    low    empirical range with 1–2 anchors OR canonical-table match
"""

from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Canonical VistA file-number ranges (A2 fallback).
# Sourced from VA Infrastructure / Standards and Terminology docs; only
# well-documented ranges are listed to keep the fallback conservative.
# Each entry: (min, max, package_name, prefix)
# ---------------------------------------------------------------------------

CANONICAL_RANGES: list[tuple[float, float, str, str]] = [
    (0.0, 1.9, "VA FILEMAN", "DI"),
    (3.0, 3.9, "MAILMAN", "XM"),
    (3.5, 3.59, "DEVICE HANDLER", "%Z"),
    (4.0, 4.999, "KERNEL", "XU"),
    (8.0, 8.9, "MENTAL HEALTH", "YS"),
    (9.2, 9.899, "KERNEL", "XU"),
    (10.0, 19.999, "KERNEL", "XU"),
    (40.0, 46.999, "SCHEDULING", "SD"),
    (50.0, 59.999, "PHARMACY", "PS"),
    (60.0, 69.999, "LAB SERVICE", "LR"),
    (70.0, 74.999, "RADIOLOGY/NUCLEAR MEDICINE", "RA"),
    (80.0, 81.999, "PCE/CPT", "PX"),
    (100.0, 101.999, "ORDER ENTRY/RESULTS REPORTING", "OR"),
    (120.5, 120.89, "VITALS", "GMRV"),
    (200.0, 200.999, "KERNEL", "XU"),  # NEW PERSON
]


@dataclass
class Attribution:
    file_number: float
    label: str
    global_root: str
    candidate_package: str | None = None
    candidate_prefix: str | None = None
    method: str = ""  # "prefix" | "range_empirical" | "range_canonical" | ""
    confidence: str = ""  # "high" | "med" | "low" | ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def namespace_from_global(global_root: str) -> str:
    """Extract the VistA namespace (uppercase letters + digits) from a global.

    ``^PSDRUG(`` → ``"PSDRUG"``
    ``^DIC(9.4,`` → ``"DIC"``
    ``^DD("IX",`` → ``"DD"``
    Returns empty string on unparseable input.
    """
    s = (global_root or "").lstrip("^")
    if not s:
        return ""
    # Take characters up to the first paren, comma, or quote; then keep only
    # alphanumerics (drops %, _).
    import re
    m = re.match(r'([A-Za-z%][A-Za-z0-9%]*)', s)
    return m.group(1) if m else ""


def longest_prefix_match(
    namespace: str,
    packages: list[tuple[str, str]],  # [(prefix, name)]
) -> tuple[str, str] | None:
    """Return the (prefix, name) of the longest package prefix that is
    a prefix of `namespace`. Returns None if no prefix matches."""
    if not namespace:
        return None
    best: tuple[str, str] | None = None
    best_len = 0
    for pref, name in packages:
        if not pref:
            continue
        if namespace.startswith(pref) and len(pref) > best_len:
            best = (pref, name)
            best_len = len(pref)
    return best


# ---------------------------------------------------------------------------
# Heuristic C — prefix match
# ---------------------------------------------------------------------------


def attribute_by_prefix(
    file_number: float,
    label: str,
    global_root: str,
    package_prefixes: list[tuple[str, str]],
) -> Attribution | None:
    """Try to attribute one file by global-root namespace prefix."""
    ns = namespace_from_global(global_root)
    if not ns:
        return None
    match = longest_prefix_match(ns, package_prefixes)
    if match is None:
        return None
    prefix, pkg_name = match
    confidence = "high" if ns == prefix else "med"
    return Attribution(
        file_number=file_number,
        label=label,
        global_root=global_root,
        candidate_package=pkg_name,
        candidate_prefix=prefix,
        method="prefix",
        confidence=confidence,
        notes=f"ns={ns} matched prefix={prefix}",
    )


# ---------------------------------------------------------------------------
# Heuristic A1 — empirical range
# ---------------------------------------------------------------------------


@dataclass
class PackageRange:
    name: str
    prefix: str
    min_num: float
    max_num: float
    anchor_count: int


def build_empirical_ranges(
    attributed_files: list[dict],
) -> list[PackageRange]:
    """Build per-package (min, max, anchor_count) from attributed files.

    attributed_files: iterable of dicts with keys `file_number`,
    `package_name`, `package_prefix`.
    """
    by_pkg: dict[str, list[float]] = {}
    prefixes: dict[str, str] = {}
    for f in attributed_files:
        pkg = f.get("package_name")
        if not pkg:
            continue
        by_pkg.setdefault(pkg, []).append(float(f["file_number"]))
        prefixes.setdefault(pkg, f.get("package_prefix") or "")
    ranges = []
    for pkg, nums in by_pkg.items():
        ranges.append(
            PackageRange(
                name=pkg,
                prefix=prefixes.get(pkg, ""),
                min_num=min(nums),
                max_num=max(nums),
                anchor_count=len(nums),
            )
        )
    return ranges


def attribute_by_range_empirical(
    file_number: float,
    label: str,
    global_root: str,
    ranges: list[PackageRange],
) -> Attribution | None:
    """Attribute by exclusive inclusion in a package's empirical range."""
    hits = [r for r in ranges if r.min_num <= file_number <= r.max_num]
    if len(hits) != 1:
        return None  # zero hits → no match; multi hits → ambiguous
    r = hits[0]
    confidence = "med" if r.anchor_count >= 3 else "low"
    return Attribution(
        file_number=file_number,
        label=label,
        global_root=global_root,
        candidate_package=r.name,
        candidate_prefix=r.prefix,
        method="range_empirical",
        confidence=confidence,
        notes=f"range=[{r.min_num},{r.max_num}] anchors={r.anchor_count}",
    )


# ---------------------------------------------------------------------------
# Heuristic A2 — canonical fallback
# ---------------------------------------------------------------------------


def attribute_by_range_canonical(
    file_number: float,
    label: str,
    global_root: str,
) -> Attribution | None:
    """Attribute by well-known VistA number ranges."""
    for low, high, name, prefix in CANONICAL_RANGES:
        if low <= file_number <= high:
            return Attribution(
                file_number=file_number,
                label=label,
                global_root=global_root,
                candidate_package=name,
                candidate_prefix=prefix,
                method="range_canonical",
                confidence="low",
                notes=f"canonical [{low},{high}]",
            )
    return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def attribute_all(
    unpackaged_files: Iterable[dict],
    package_prefixes: list[tuple[str, str]],
    ranges: list[PackageRange],
) -> list[Attribution]:
    """Apply heuristics C → A1 → A2 in order; first hit wins."""
    out: list[Attribution] = []
    for f in unpackaged_files:
        fn = float(f["file_number"])
        lb = f.get("label", "")
        gr = f.get("global_root", "")
        a = (
            attribute_by_prefix(fn, lb, gr, package_prefixes)
            or attribute_by_range_empirical(fn, lb, gr, ranges)
            or attribute_by_range_canonical(fn, lb, gr)
            or Attribution(file_number=fn, label=lb, global_root=gr)
        )
        out.append(a)
    return out
