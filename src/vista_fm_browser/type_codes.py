"""FileMan type-string decomposition.

Parses raw FileMan type codes (piece 2 of a field's 0-node) into structured
`TypeSpec` objects that separate the base type, required/audit flags,
modifiers, numeric width/decimals, and pointer-target metadata.

Shape of a FileMan type string::

    [prefix flags] <base or decimal> [modifiers] [trailing flags]

Prefix flags
    R   required
    *   audited
    M   multiple-valued (precedes P for multi-pointers)

Base codes (single letter unless noted)
    F=FREE TEXT, N=NUMERIC, D=DATE/TIME, S=SET OF CODES, P=POINTER,
    V=VARIABLE POINTER, W=WORD PROCESSING, K=MUMPS, C=COMPUTED,
    B=BOOLEAN, A=ADDRESS, M=MULTIPLE, DC=COMPUTED DATE.
    A bare decimal number (e.g. "1.001") means multiple-valued sub-file.

Modifiers / trailing flags
    J<w>,<d>  numeric justification — width w, decimals d
    X         input transform present (or crossref flag on some codes)
    O         output transform present
    '         pointer or free-text "required in this context"
    (others)  preserved in `.modifiers` as single-letter flags

Example::

    >>> ts = decompose("NJ3,0")
    >>> ts.base, ts.numeric_width, ts.numeric_decimals
    ('N', 3, 0)
    >>> ts = decompose("*P356.8'")
    >>> ts.base, ts.pointer_file, ts.audited, ts.required
    ('P', 356.8, True, True)
"""

from dataclasses import dataclass, field


_PREFIX_FLAGS = set("R*")
_BASE_TYPE_CODES = set("FNDSPCWVKMBA")


@dataclass
class TypeSpec:
    """Structured decomposition of a raw FileMan type string."""

    raw: str
    base: str = ""
    required: bool = False
    audited: bool = False
    is_multiple: bool = False
    multiple_file: float | None = None
    pointer_file: float | None = None
    numeric_width: int | None = None
    numeric_decimals: int | None = None
    modifiers: set[str] = field(default_factory=set)


def decompose(raw: str) -> TypeSpec:
    """Parse a FileMan type string into a TypeSpec."""
    ts = TypeSpec(raw=raw)
    if not raw:
        return ts

    s = raw

    # Strip prefix flags (R, *) in any order.
    while s and s[0] in _PREFIX_FLAGS:
        if s[0] == "R":
            ts.required = True
        elif s[0] == "*":
            ts.audited = True
        s = s[1:]

    if not s:
        return ts

    # "DC" — two-character base (computed date).
    if s.startswith("DC"):
        ts.base = "DC"
        _collect_trailing_modifiers(ts, s[2:])
        return ts

    # Bare-decimal multiple (e.g. "1.001", "9999999.64").
    if s[0].isdigit():
        num_str, _ = _read_decimal(s)
        if num_str:
            try:
                ts.base = "M"
                ts.is_multiple = True
                ts.multiple_file = float(num_str)
                return ts
            except ValueError:
                pass

    # "M" prefix before a P marks a multiple-valued pointer (e.g. "MP920'").
    if s.startswith("M") and len(s) > 1 and s[1] in _BASE_TYPE_CODES:
        ts.is_multiple = True
        s = s[1:]

    # Find the first canonical base-type letter.
    idx = next((i for i, c in enumerate(s) if c in _BASE_TYPE_CODES), -1)
    if idx < 0:
        ts.base = s[:1]
        return ts

    ts.base = s[idx]
    tail = s[idx + 1:]

    # Pointer target: read leading digits/dot after P.
    if ts.base == "P":
        num_str, rest = _read_decimal(tail)
        if num_str:
            try:
                ts.pointer_file = float(num_str)
            except ValueError:
                pass
        _collect_trailing_modifiers(ts, rest)
        return ts

    # Numeric justification: J<w>,<d>.
    if ts.base == "N" and tail.startswith("J"):
        rest_after_j = tail[1:]
        w_str, after_w = _read_decimal(rest_after_j)
        if w_str and after_w.startswith(","):
            d_str, after_d = _read_decimal(after_w[1:])
            try:
                ts.numeric_width = int(w_str)
                ts.numeric_decimals = int(d_str) if d_str else 0
            except ValueError:
                pass
            ts.modifiers.add("J")
            _collect_trailing_modifiers(ts, after_d)
            return ts

    _collect_trailing_modifiers(ts, tail)
    return ts


def _read_decimal(s: str) -> tuple[str, str]:
    """Read a leading decimal (digits and one dot) and return (num, rest)."""
    num_chars: list[str] = []
    seen_dot = False
    i = 0
    for i, c in enumerate(s):
        if c.isdigit():
            num_chars.append(c)
        elif c == "." and not seen_dot:
            seen_dot = True
            num_chars.append(c)
        else:
            return "".join(num_chars), s[i:]
    return "".join(num_chars), ""


def _collect_trailing_modifiers(ts: TypeSpec, tail: str) -> None:
    """Fold trailing modifier characters into the TypeSpec."""
    for c in tail:
        if c == "'":
            ts.required = True
        elif c.isalpha():
            ts.modifiers.add(c)
        # digits, commas, spaces: skip silently
