"""
VistA FileMan file inventory reader.

Reads File 1 (^DIC) and the PACKAGE file (^DIC(9.4,...)) to produce a
complete, structured map of every FileMan file in the VistA instance,
organized by package.  This is the starting point for planning any
systematic analysis of VistA data.

^DIC global layout:
    ^DIC(file#, 0)                   = "label^{file#}I[flags]"
    ^DIC(file#, 0, "GL")             = global root (e.g. "^DPT(")
    ^DIC("B", label, file#)          = B cross-reference (name index)

^DIC(9.4, ...) — PACKAGE file (#9.4):
    ^DIC(9.4, pkg_ien, 0)            = "name^prefix^version^..."
    ^DIC(9.4, pkg_ien, 4, ien, 0)    = "file_number^..."  (FILE multiple, field #4)

Usage::

    with YdbConnection.connect() as conn:
        fi = FileInventory(conn)
        fi.load()                           # reads ^DIC + ^DIC(9.4,...)
        print(fi.summary())
        grouped = fi.files_by_package()
        for pkg_name, files in grouped.items():
            print(pkg_name, len(files))
        fi.export_json(Path("~/data/vista-fm-browser/output/"))
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .connection import YdbConnection

log = logging.getLogger(__name__)

UNPACKAGED = "(unpackaged)"


def _pick_owning_package(
    global_root: str, candidates: list["PackageInfo"]
) -> "PackageInfo | None":
    """Pick the best-matching package for a file from its candidates.

    The PACKAGE file (#9.4) FILE multiple is a "uses/writes" list — many
    packages may claim the same file. We prefer the package whose PREFIX
    matches the start of the file's global root namespace (e.g. file #50
    with global ^PSDRUG( matches prefix "PS" → PHARMACY). On ties, pick
    the longest matching prefix; on no match, fall back to lowest-IEN.
    """
    if not candidates:
        return None
    # Namespace = "PSDRUG" from "^PSDRUG(" (strip leading ^ and trailing paren/subs)
    ns = global_root.lstrip("^").split("(", 1)[0]
    best: PackageInfo | None = None
    best_len = -1
    for pkg in candidates:
        p = (pkg.prefix or "").strip()
        if p and ns.startswith(p) and len(p) > best_len:
            best, best_len = pkg, len(p)
    if best is not None:
        return best
    # No prefix matched — fall back to lowest-IEN (numeric order) claim.
    return min(candidates, key=lambda p: int(p.ien) if p.ien.isdigit() else 10**9)


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------


@dataclass
class PackageInfo:
    """One entry from the VistA PACKAGE file (#9.4)."""

    ien: str
    name: str
    prefix: str  # namespace prefix, e.g. "LR", "PS", "DG"
    version: str  # installed version string
    file_numbers: list[float] = field(default_factory=list)


@dataclass
class FileRecord:
    """One entry from the VistA FILE file (#1, stored in ^DIC)."""

    file_number: float
    label: str
    global_root: str  # e.g. "^DPT("  or  "^PS(50,"
    field_count: int  # number of fields in ^DD (0 if no DD entry)
    package_name: str | None = None
    package_prefix: str | None = None
    package_ien: str | None = None


# ------------------------------------------------------------------
# FileInventory
# ------------------------------------------------------------------


class FileInventory:
    """Reads and organises the complete FileMan file and package registry.

    After calling ``load()``, the inventory is available via:
        ``list_files()``          → all FileRecord objects
        ``list_packages()``       → all PackageInfo objects
        ``files_by_package()``    → dict[package_name, list[FileRecord]]
        ``summary()``             → counts and top packages
        ``to_dict()``             → JSON-serializable dict
        ``export_json(dir)``      → write inventory.json to a directory
    """

    def __init__(self, conn: YdbConnection) -> None:
        self._conn = conn
        self._files: list[FileRecord] = []
        self._packages: list[PackageInfo] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Read ^DIC and ^DIC(9.4,...) and build the inventory."""
        log.info("Loading FileMan file inventory from ^DIC ...")
        self._packages = self._read_packages()

        # Build file→[packages] lookup. Many packages can list the same
        # file in their FILE multiple — the multiple is really a "uses/writes"
        # list, not a sole-ownership marker. We pick the best match per-file
        # later using the global-root↔prefix heuristic in _pick_owning_package.
        pkgs_by_file: dict[float, list[PackageInfo]] = {}
        for pkg in self._packages:
            for fn in pkg.file_numbers:
                pkgs_by_file.setdefault(fn, []).append(pkg)

        self._files = self._read_files(pkgs_by_file)
        log.info(
            "Inventory loaded: %d files in %d packages",
            len(self._files),
            len(self._packages),
        )

    def list_files(self) -> list[FileRecord]:
        """Return all file records sorted by file number."""
        return list(self._files)

    def list_packages(self) -> list[PackageInfo]:
        """Return all package records sorted by name."""
        return sorted(self._packages, key=lambda p: p.name)

    def files_by_package(self) -> dict[str, list[FileRecord]]:
        """Return files grouped by package name.

        Files not assigned to any package appear under the key
        ``"(unpackaged)"``.
        """
        grouped: dict[str, list[FileRecord]] = {}
        for fr in self._files:
            key = fr.package_name or UNPACKAGED
            grouped.setdefault(key, []).append(fr)
        # Sort files within each group
        for files in grouped.values():
            files.sort(key=lambda f: f.file_number)
        return grouped

    def summary(self) -> dict:
        """Return a high-level summary dict suitable for JSON serialization."""
        grouped = self.files_by_package()
        rows: list[dict[str, str | int]] = [
            {"name": name, "file_count": len(files)}
            for name, files in grouped.items()
            if name != UNPACKAGED
        ]
        top = sorted(rows, key=lambda x: x["file_count"], reverse=True)
        unpackaged = grouped.get(UNPACKAGED, [])
        return {
            "total_files": len(self._files),
            "total_packages": len(self._packages),
            "unpackaged_files": len(unpackaged),
            "top_packages_by_file_count": top[:20],
        }

    def to_dict(self) -> dict:
        """Return the full inventory as a JSON-serializable dict."""
        return {
            "summary": self.summary(),
            "packages": [
                {
                    "ien": p.ien,
                    "name": p.name,
                    "prefix": p.prefix,
                    "version": p.version,
                    "file_count": len(p.file_numbers),
                    "file_numbers": sorted(p.file_numbers),
                }
                for p in self.list_packages()
            ],
            "files": [
                {
                    "file_number": f.file_number,
                    "label": f.label,
                    "global_root": f.global_root,
                    "field_count": f.field_count,
                    "package_name": f.package_name,
                    "package_prefix": f.package_prefix,
                }
                for f in self._files
            ],
        }

    def export_json(self, output_dir: Path) -> Path:
        """Write the full inventory to ``inventory.json`` in output_dir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "inventory.json"
        out.write_text(json.dumps(self.to_dict(), indent=2))
        log.info("Inventory written to %s", out)
        return out

    # ------------------------------------------------------------------
    # Internal readers
    # ------------------------------------------------------------------

    def _read_packages(self) -> list[PackageInfo]:
        """Read all entries from the PACKAGE file (^DIC(9.4,...))."""
        packages: list[PackageInfo] = []
        for pkg_ien in self._conn.subscripts("^DIC", ["9.4", ""]):
            zero = self._conn.get("^DIC", ["9.4", pkg_ien, "0"])
            if not zero:
                continue
            parts = zero.split("^")
            name = parts[0] if parts else ""
            prefix = parts[1] if len(parts) > 1 else ""
            version = parts[2] if len(parts) > 2 else ""
            file_numbers = self._read_package_files(pkg_ien)
            packages.append(
                PackageInfo(
                    ien=pkg_ien,
                    name=name,
                    prefix=prefix,
                    version=version,
                    file_numbers=file_numbers,
                )
            )
            log.debug("Package %s (%s): %d files", name, prefix, len(file_numbers))
        return packages

    def _read_package_files(self, pkg_ien: str) -> list[float]:
        """Read the FILE multiple (field #4, node 4) for one package."""
        file_numbers: list[float] = []
        for entry_ien in self._conn.subscripts("^DIC", ["9.4", pkg_ien, "4", ""]):
            zero = self._conn.get("^DIC", ["9.4", pkg_ien, "4", entry_ien, "0"])
            if not zero:
                continue
            raw = zero.split("^")[0].strip()
            try:
                file_numbers.append(float(raw))
            except ValueError:
                log.debug("Non-numeric file entry in package %s: %r", pkg_ien, raw)
        return file_numbers

    def _read_files(
        self, pkgs_by_file: dict[float, list[PackageInfo]]
    ) -> list[FileRecord]:
        """Read all file entries from ^DIC, skipping non-numeric nodes."""
        files: list[FileRecord] = []
        for raw_num in self._conn.subscripts("^DIC", [""]):
            try:
                file_num = float(raw_num)
            except ValueError:
                continue  # skip "B", "BB", "C", etc.

            zero = self._conn.get("^DIC", [raw_num, "0"])
            if not zero:
                continue

            parts = zero.split("^")
            label = parts[0] if parts else ""
            # Global root lives at ^DIC(file#,0,"GL"), not at piece 2 of the
            # zero node (piece 2 is the file number plus flags, e.g. "2I").
            raw_root = self._conn.get("^DIC", [raw_num, "0", "GL"])
            global_root = raw_root if raw_root.startswith("^") else f"^{raw_root}"

            field_count = self._count_fields(raw_num)
            pkg = _pick_owning_package(global_root, pkgs_by_file.get(file_num, []))

            files.append(
                FileRecord(
                    file_number=file_num,
                    label=label,
                    global_root=global_root,
                    field_count=field_count,
                    package_name=pkg.name if pkg else None,
                    package_prefix=pkg.prefix if pkg else None,
                    package_ien=pkg.ien if pkg else None,
                )
            )

        files.sort(key=lambda f: f.file_number)
        return files

    def _count_fields(self, file_num_str: str) -> int:
        """Count the numeric field subscripts in ^DD(file#,...).

        The "0" subscript is the file header node, not a field — skip it.
        Fields are numbered from .001 upward (.01, .02, 1, 2, etc.).
        """
        count = 0
        for sub in self._conn.subscripts("^DD", [file_num_str, ""]):
            try:
                fld = float(sub)
                if fld > 0:  # skip the "0" zero-node (file header)
                    count += 1
            except ValueError:
                pass
        return count
