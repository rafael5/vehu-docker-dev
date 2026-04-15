"""
VA FileMan data dictionary reader.

Reads the FileMan data dictionary from the ^DD global and returns structured
Python objects.  Also reads the INDEX (#.11) file for cross-reference metadata.
All knowledge of ^DD and ^.11 global layouts is encapsulated here.

^DD layout (FileMan 22.2):
    ^DD(file#, 0)                   → "FIELD^NL^{num_fields}^{last_mod}"
                                      NOTE: constant marker — per-file label
                                      and global root live in ^DIC, not ^DD.
    ^DIC(file#, 0)                  → "LABEL^{file#}I[flags]"
    ^DIC(file#, 0, "GL")            → global root (e.g. "^DPT(")
    ^DD(file#, field#, 0)           → "LABEL^TYPE^CONTEXT^STORAGE_LOC^INPUT_TRANSFORM"
                                      CONTEXT is context-sensitive by TYPE:
                                        S-type → "code:label;code:label;"
                                        P-type → target global root (redundant)
                                        other  → typically empty
    ^DD(file#, field#, 1)           → INPUT TRANSFORM (M code)
    ^DD(file#, field#, 3)           → HELP-PROMPT text
    ^DD(file#, field#, 21, n, 0)    → DESCRIPTION (word processing, line n)
    ^DD(file#, field#, "DT")        → date field last edited (FM format)
    ^DD(file#, field#, "V", code)   → set-of-codes: code → label
    ^DD("B", file_label, file#)     → file name index

Type codes in the 0-node's second piece:
    F         = FREE TEXT
    N         = NUMERIC
    D         = DATE/TIME
    S         = SET OF CODES
    P<file#>  = POINTER TO FILE (e.g. "P2" = pointer to PATIENT #2)
    M         = MULTIPLE (subfile)
    C         = COMPUTED
    K         = MUMPS
    V         = VARIABLE POINTER
    W         = WORD PROCESSING
    DC        = COMPUTED DATE

INDEX file (#.11) — new-style cross-references (FileMan 22.0+):
    Global location: ^DD("IX",...)  (from ^DIC(.11,0,"GL") = '^DD("IX",')
    ^DD("IX", ien, 0)  → "file#^name^type^..."
    Each IEN is one cross-reference entry. File# is the FileMan file number.
    type is "REGULAR" or "MUMPS".
"""

import logging
from dataclasses import dataclass, field

from .connection import YdbConnection
from .fm_datetime import fm_date_display

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
    set_values: dict[str, str] = field(
        default_factory=dict
    )  # code → label (for S type)
    pointer_file: float | None = None  # for P type


@dataclass
class FieldAttributes:
    """Extended field attributes including all readable ^DD nodes.

    A superset of FieldDef that adds the extended nodes not needed for
    basic browsing but useful for analytics and schema documentation.
    """

    file_number: float
    field_number: float
    label: str
    datatype_code: str
    datatype_name: str
    title: str = ""
    set_values: dict[str, str] = field(default_factory=dict)
    pointer_file: float | None = None
    # Extended nodes
    input_transform: str = ""  # ^DD(file, field, 1) — M validation code
    help_prompt: str = ""  # ^DD(file, field, 3) — short help text
    description: list[str] = field(default_factory=list)  # ^DD(file, field, 21, n, 0)
    last_edited: str = ""  # ^DD(file, field, "DT") — FM date string
    global_subscript: str = ""  # storage location from 0-node piece 3 (e.g. "0;1")


@dataclass
class CrossRefInfo:
    """One cross-reference entry from the INDEX (#.11) file.

    ^.11(ien, 0) = "file#^name^type^..."
    """

    ien: str
    file_number: float
    name: str  # cross-reference name, e.g. "B", "AC", "ADFN"
    xref_type: str  # "REGULAR" or "MUMPS"
    description: str = ""


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


# Canonical single-letter FileMan data-type codes (in search order).
# These are the "base" types — real FileMan type strings often have
# required/audit prefix flags and modifier suffixes wrapped around them.
_BASE_TYPE_CODES = set("FNDSPCWVKMBA")

# Prefix flags that may appear before the base type code.
#   R  = required
#   *  = audit trail enabled
_PREFIX_FLAGS = set("R*")


def _parse_set_values(context_piece: str) -> dict[str, str]:
    """Parse SET-of-codes values from piece 3 of a field's 0-node.

    Format: "code1:label1;code2:label2;..."
    Empty or malformed pieces return an empty dict.
    """
    if not context_piece:
        return {}
    values: dict[str, str] = {}
    for pair in context_piece.split(";"):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        code, label = pair.split(":", 1)
        values[code.strip()] = label.strip()
    return values


def _extract_type_code(raw: str) -> tuple[str, float | None]:
    """Parse a raw FileMan type string into (canonical_code, pointer_file).

    FileMan type strings have a structured format:
        [R][*]<BASE><modifiers>

    Where:
        R   — required flag (prefix)
        *   — audited flag (prefix)
        <BASE>   — single letter from _BASE_TYPE_CODES (or "DC" for computed date)
        <modifiers> — type-specific suffixes:
            P<file#>  — pointer target file number; optional trailing flags
                        like ' (required), O, X, I, U, a
            NJ<w>,<d> — numeric justification (width, decimals)
            FX, RF, etc. — free-text with transform, required free-text

    Examples:
        "F"        → ("F", None)
        "FX"       → ("F", None)
        "RF"       → ("F", None)
        "*P356.8'" → ("P", 356.8)
        "NJ3,0"    → ("N", None)
        "DC"       → ("DC", None)
        "P50.68"   → ("P", 50.68)
        "MP920'"   → ("P", 920)    # multiple-pointer: treat target file as pointer
        "V"        → ("V", None)
    """
    if not raw:
        return "", None

    # Strip prefix flags (R, *) in any order.
    s = raw
    while s and s[0] in _PREFIX_FLAGS:
        s = s[1:]
    if not s:
        return "", None

    # "DC" is a two-character base code (computed date).
    if s.startswith("DC"):
        return "DC", None

    # A bare decimal number (e.g. "1.001", "9999999.64") is a MULTIPLE field
    # referencing a sub-file by that file number. FileMan uses this form
    # instead of an "M" prefix for most sub-file references.
    if s and s[0].isdigit():
        try:
            return "M", float(s)
        except ValueError:
            pass  # fall through to base-letter scan

    # Find the first canonical base-type letter.
    idx = next((i for i, c in enumerate(s) if c in _BASE_TYPE_CODES), -1)
    if idx < 0:
        return s[:1], None
    base = s[idx]

    # Pointer types carry a target file number in the trailing characters.
    # "P50.68" → pointer_file=50.68; "P200'" → pointer_file=200 (strip flags).
    # This also covers compound prefixes like "MP920" (multiple-pointer).
    if base == "P":
        tail = s[idx + 1:]
        num_str = ""
        for c in tail:
            if c.isdigit() or c == ".":
                num_str += c
            else:
                break
        try:
            return "P", float(num_str) if num_str else None
        except ValueError:
            return "P", None

    return base, None


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
        """Return (file_number, label) for every FileMan file.

        Enumerates ^DIC (the FILE registry) rather than ^DD, since ^DD
        contains subfile entries that aren't top-level files. Sorted
        ascending by file number.
        """
        results: list[tuple[float, str]] = []
        for raw_num in self._conn.subscripts("^DIC", [""]):
            try:
                file_num = float(raw_num)
            except ValueError:
                continue  # skip "B", "C", etc.
            zero = self._conn.get("^DIC", [raw_num, "0"])
            if not zero:
                continue
            label = _parse_zero_node(zero)[0]
            results.append((file_num, label))
        results.sort(key=lambda t: t[0])
        log.debug("list_files: found %d files", len(results))
        return results

    def get_file(self, file_number: float) -> FileDef | None:
        """Return full FileDef for the given file number, or None if not found.

        Reads file header (label + global root) from ^DIC; reads fields from ^DD.
        """
        if file_number in self._file_cache:
            return self._file_cache[file_number]

        fn_str = _fmt_file_num(file_number)

        # File header (label, global root) lives in ^DIC — NOT ^DD.
        dic_zero = self._conn.get("^DIC", [fn_str, "0"])
        if not dic_zero:
            return None
        label = _parse_zero_node(dic_zero)[0]
        raw_gl = self._conn.get("^DIC", [fn_str, "0", "GL"])
        global_root = raw_gl if raw_gl.startswith("^") else (
            f"^{raw_gl}" if raw_gl else ""
        )

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

    def get_field_attributes(
        self, file_number: float, field_number: float
    ) -> FieldAttributes | None:
        """Return full FieldAttributes for one field, including extended ^DD nodes.

        Reads the 0-node (label, type, storage location, title) plus the
        extended nodes: INPUT TRANSFORM (node 1), HELP-PROMPT (node 3),
        DESCRIPTION (nodes 21,n,0), DATE LAST EDITED (node "DT"), and
        SET-OF-CODES values (node "V", code).

        Returns None if the file or field does not exist in ^DD.
        """
        fn_str = _fmt_file_num(file_number)
        fld_str = _fmt_field_num(field_number)

        zero = self._conn.get("^DD", [fn_str, fld_str, "0"])
        if not zero:
            return None

        parts = _parse_zero_node(zero)
        label = parts[0] if parts else ""
        raw_type = parts[1] if len(parts) > 1 else ""
        context_piece = parts[2] if len(parts) > 2 else ""
        global_subscript = parts[3] if len(parts) > 3 else ""
        title = parts[4] if len(parts) > 4 else ""

        datatype_code, pointer_file = _extract_type_code(raw_type)
        datatype_name = DATATYPE_NAMES.get(datatype_code, datatype_code or "UNKNOWN")

        # Extended nodes — use fld_str (MUMPS canonical) for all subscript lookups.
        # Input transform: some FileMan versions store it at ^DD(f,fld,1); VEHU
        # stores it inline in piece 5 of the 0-node. Prefer the explicit node.
        input_transform = self._conn.get("^DD", [fn_str, fld_str, "1"]) or title or ""
        help_prompt = self._conn.get("^DD", [fn_str, fld_str, "3"]) or ""
        last_edited = self._conn.get("^DD", [fn_str, fld_str, "DT"]) or ""

        # DESCRIPTION (word-processing, node 21)
        description: list[str] = []
        for n in self._conn.subscripts("^DD", [fn_str, fld_str, "21", ""]):
            line = self._conn.get("^DD", [fn_str, fld_str, "21", n, "0"])
            if line:
                description.append(line)

        # SET-OF-CODES values live in piece 3 of the 0-node ("code:label;...")
        set_values = _parse_set_values(context_piece) if datatype_code == "S" else {}

        return FieldAttributes(
            file_number=file_number,
            field_number=field_number,
            label=label,
            datatype_code=datatype_code,
            datatype_name=datatype_name,
            title=title,
            set_values=set_values,
            pointer_file=pointer_file,
            input_transform=input_transform,
            help_prompt=help_prompt,
            description=description,
            last_edited=last_edited,
            global_subscript=global_subscript,
        )

    def format_external(
        self,
        field_attrs: "FieldDef | FieldAttributes",
        internal_value: str,
        *,
        resolve_pointer: bool = False,
    ) -> str:
        """Convert a FileMan internal field value to its external display form.

        Parameters
        ----------
        field_attrs:
            FieldDef or FieldAttributes for the field being formatted.
        internal_value:
            The raw value as stored in the global (e.g. "M", "2450101", "1").
        resolve_pointer:
            If True and the field is a POINTER type, look up the .01 field
            of the pointed-to entry (one extra global read).  If False,
            returns "IEN:<value>" for pointer fields.

        Type handling:
            F (FREE TEXT)      → returned as-is
            N (NUMERIC)        → returned as-is
            D (DATE/TIME)      → converted via fm_date_display()
            S (SET OF CODES)   → code looked up in set_values dict
            P (POINTER)        → IEN resolved if resolve_pointer=True
            M (MULTIPLE)       → returns "[Multiple]"
            C (COMPUTED)       → returned as-is (not stored in globals)
            W (WORD PROCESSING)→ returns "[Word Processing]"
            others             → returned as-is
        """
        if not internal_value:
            return ""

        code = field_attrs.datatype_code

        if code == "D":
            return fm_date_display(internal_value)

        if code == "S":
            return field_attrs.set_values.get(internal_value, internal_value)

        if code == "P":
            if not resolve_pointer or field_attrs.pointer_file is None:
                return f"IEN:{internal_value}"
            return self._resolve_pointer(field_attrs.pointer_file, internal_value)

        if code == "M":
            return "[Multiple]"

        if code == "W":
            return "[Word Processing]"

        return internal_value

    def list_cross_refs(self, file_number: float) -> list[CrossRefInfo]:
        """Return all INDEX (#.11) cross-references defined for a file.

        The INDEX file (#.11) is stored at ^DD("IX",...) in real VistA
        (confirmed via ^DIC(.11,0,"GL") = '^DD("IX",'). Each entry's
        0-node is formatted as "file#^name^type^..."

        Traditional (old-style) cross-references defined directly in
        ^DD(file, field, 1) are not returned here.
        """
        fn_str = _fmt_file_num(file_number)
        results: list[CrossRefInfo] = []
        for ien in self._conn.subscripts("^DD", ["IX", ""]):
            try:
                float(ien)  # skip non-numeric nodes
            except ValueError:
                continue
            zero = self._conn.get("^DD", ["IX", ien, "0"])
            if not zero:
                continue
            parts = zero.split("^")
            if not parts:
                continue
            raw_file = parts[0].strip()
            if raw_file != fn_str:
                continue  # not our file
            name = parts[1] if len(parts) > 1 else ""
            xref_type = parts[2] if len(parts) > 2 else ""
            description = parts[3] if len(parts) > 3 else ""
            results.append(
                CrossRefInfo(
                    ien=ien,
                    file_number=file_number,
                    name=name,
                    xref_type=xref_type,
                    description=description,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_pointer(self, pointer_file: float, ien: str) -> str:
        """Look up the .01 (name) of IEN in the pointed-to file.

        Returns the first caret-piece of the zero-node (the .01 value),
        or the raw IEN string if the entry cannot be found.
        """
        file_def = self.get_file(pointer_file)
        if file_def is None:
            return ien
        # Normalise global root: "DPT(" → "^DPT", "^DPT(" → "^DPT"
        raw_root = file_def.global_root.split("(")[0]
        global_name = raw_root if raw_root.startswith("^") else f"^{raw_root}"
        zero = self._conn.get(global_name, [ien, "0"])
        if not zero:
            return ien
        return zero.split("^")[0]

    def _read_fields(self, fn_str: str, file_number: float) -> dict[float, FieldDef]:
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


def _fmt_field_num(field_number: float) -> str:
    """Format a field number in MUMPS canonical form.

    MUMPS drops the leading zero for decimals between 0 and 1:
        0.01  → ".01"
        0.02  → ".02"
        9999999.0 → "9999999"
        50.68 → "50.68"

    This matches how YottaDB stores field subscripts in ^DD.
    """
    if field_number == int(field_number):
        return str(int(field_number))
    s = str(field_number)
    if s.startswith("0."):
        return s[1:]  # "0.01" → ".01"
    return s


def _parse_field_zero(
    file_number: float, field_number: float, zero_node: str
) -> FieldDef:
    """Parse a field zero-node string into a FieldDef.

    Zero-node format: "LABEL^TYPE^STORAGE_LOC^TITLE"

    TYPE codes:
      Plain code ("F", "N", "S", "D", "C", "W", "K", "M")  → used as-is
      "P<file#>"  → POINTER type; file# extracted as pointer_file
      "DC"        → COMPUTED DATE (kept as "DC")
    """
    parts = _parse_zero_node(zero_node)
    label = parts[0] if len(parts) > 0 else ""
    raw_type = parts[1] if len(parts) > 1 else ""
    context_piece = parts[2] if len(parts) > 2 else ""
    title = parts[4] if len(parts) > 4 else ""

    datatype_code, pointer_file = _extract_type_code(raw_type)
    datatype_name = DATATYPE_NAMES.get(datatype_code, datatype_code or "UNKNOWN")
    set_values = _parse_set_values(context_piece) if datatype_code == "S" else {}
    return FieldDef(
        file_number=file_number,
        field_number=field_number,
        label=label,
        datatype_code=datatype_code,
        datatype_name=datatype_name,
        title=title,
        pointer_file=pointer_file,
        set_values=set_values,
    )
