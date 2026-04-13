"""
VA FileMan data dictionary reader.

Reads the FileMan data dictionary from the ^DD global and returns structured
Python dicts.  All knowledge of ^DD global layout is encapsulated here.

^DD layout (FileMan 22.2):
    ^DD(file#, 0)                  → "FILE_NAME^GLOBAL_ROOT^..."  (file header)
    ^DD(file#, field#, 0)          → "FIELD_NAME^DATATYPE^..."    (field header)
    ^DD(file#, field#, "DT")       → last-edited date
    ^DD(file#, "B", name, field#)  → name → field# index
    ^DD(file#, field#, "V", ...)   → set-of-codes values (if DATATYPE == "S")
    ^DD("B", file_name, file#)     → file name index

FileMan zero-node pipe-delimited layout for file header (^DD(file#, 0)):
    piece 1  = file label
    piece 2  = global root  (e.g. "^DPT(")
    piece 3  = date/time of last edit
    piece 4  = number of entries

FileMan zero-node for field header (^DD(file#, field#, 0)):
    piece 1  = field label
    piece 2  = data type code  (F=free text, N=numeric, D=date, P=pointer,
                                S=set of codes, M=multiple, C=computed, ...)
    piece 3  = ?
    piece 4  = field title (long label)
"""

import logging
from dataclasses import dataclass, field

from .connection import YdbConnection

log = logging.getLogger(__name__)

# Data type codes → human-readable names
DATATYPE_NAMES: dict[str, str] = {
    "F": "FREE TEXT",
    "N": "NUMERIC",
    "D": "DATE/TIME",
    "P": "POINTER",
    "S": "SET OF CODES",
    "M": "MULTIPLE",
    "C": "COMPUTED",
    "DC": "COMPUTED DATE",
    "K": "MUMPS",
    "V": "VARIABLE POINTER",
    "W": "WORD PROCESSING",
    "A": "ADDRESS",
    "B": "BOOLEAN",
}


@dataclass
class FieldDef:
    """Definition of a single FileMan field."""

    file_number: float
    field_number: float
    label: str
    datatype_code: str
    datatype_name: str
    title: str = ""
    set_values: dict[str, str] = field(default_factory=dict)  # code → label (for S type)
    pointer_file: float | None = None  # for P type


@dataclass
class FileDef:
    """Definition of a FileMan file (header + fields)."""

    file_number: float
    label: str
    global_root: str
    fields: dict[float, FieldDef] = field(default_factory=dict)

    @property
    def field_count(self) -> int:
        return len(self.fields)


def _parse_zero_node(zero_node: str) -> list[str]:
    """Split a FileMan zero-node string on ^ and return all pieces."""
    return zero_node.split("^")


class DataDictionary:
    """Reads and caches the FileMan data dictionary from ^DD.

    Usage::

        with YdbConnection.connect() as conn:
            dd = DataDictionary(conn)
            files = dd.list_files()
            file_def = dd.get_file(2)   # PATIENT file
    """

    def __init__(self, conn: YdbConnection) -> None:
        self._conn = conn
        self._file_cache: dict[float, FileDef] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_files(self) -> list[tuple[float, str]]:
        """Return (file_number, label) for every FileMan file in ^DD.

        Sorted ascending by file number.
        """
        results: list[tuple[float, str]] = []
        for raw_num in self._conn.subscripts("^DD", [""]):
            try:
                file_num = float(raw_num)
            except ValueError:
                continue  # skip non-numeric nodes like "B"
            zero = self._conn.get("^DD", [raw_num, 0])
            if not zero:
                continue
            label = _parse_zero_node(zero)[0]
            results.append((file_num, label))
        results.sort(key=lambda t: t[0])
        log.debug("list_files: found %d files", len(results))
        return results

    def get_file(self, file_number: float) -> FileDef | None:
        """Return full FileDef for the given file number, or None if not found."""
        if file_number in self._file_cache:
            return self._file_cache[file_number]

        fn_str = _fmt_file_num(file_number)
        zero = self._conn.get("^DD", [fn_str, 0])
        if not zero:
            return None

        parts = _parse_zero_node(zero)
        label = parts[0] if len(parts) > 0 else ""
        global_root = parts[1] if len(parts) > 1 else ""

        file_def = FileDef(
            file_number=file_number,
            label=label,
            global_root=global_root,
        )
        file_def.fields = self._read_fields(fn_str, file_number)
        self._file_cache[file_number] = file_def
        return file_def

    def search_files(self, query: str) -> list[tuple[float, str]]:
        """Return files whose label contains query (case-insensitive)."""
        q = query.upper()
        return [(n, lbl) for n, lbl in self.list_files() if q in lbl.upper()]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_fields(
        self, fn_str: str, file_number: float
    ) -> dict[float, FieldDef]:
        fields: dict[float, FieldDef] = {}
        for raw_fld in self._conn.subscripts("^DD", [fn_str, ""]):
            try:
                fld_num = float(raw_fld)
            except ValueError:
                continue
            zero = self._conn.get("^DD", [fn_str, raw_fld, 0])
            if not zero:
                continue
            fld = _parse_field_zero(file_number, fld_num, zero)
            if fld.datatype_code == "S":
                fld.set_values = self._read_set_values(fn_str, raw_fld)
            fields[fld_num] = fld
        return fields

    def _read_set_values(self, fn_str: str, fld_str: str) -> dict[str, str]:
        """Read set-of-codes values from ^DD(file,field,"V",...)."""
        values: dict[str, str] = {}
        for code in self._conn.subscripts("^DD", [fn_str, fld_str, "V", ""]):
            label = self._conn.get("^DD", [fn_str, fld_str, "V", code])
            values[code] = label
        return values


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _fmt_file_num(file_number: float) -> str:
    """Format a file number as FileMan stores it (integer if whole, else float)."""
    if file_number == int(file_number):
        return str(int(file_number))
    return str(file_number)


def _parse_field_zero(
    file_number: float, field_number: float, zero_node: str
) -> FieldDef:
    """Parse a field zero-node string into a FieldDef."""
    parts = _parse_zero_node(zero_node)
    label = parts[0] if len(parts) > 0 else ""
    datatype_code = parts[1] if len(parts) > 1 else ""
    title = parts[3] if len(parts) > 3 else ""
    datatype_name = DATATYPE_NAMES.get(datatype_code, datatype_code or "UNKNOWN")
    return FieldDef(
        file_number=file_number,
        field_number=field_number,
        label=label,
        datatype_code=datatype_code,
        datatype_name=datatype_name,
        title=title,
    )
