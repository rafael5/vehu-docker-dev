"""
FileMan file data reader.

Reads actual data entries from a FileMan file global.
Uses the FileDef from data_dictionary.py to decode field values.

FileMan data storage layout:
    ^GLOBAL(ien, 0)       → zero-node: pipe-delimited fields in storage order
    ^GLOBAL(ien, node)    → additional nodes for fields stored on non-zero nodes
    ^GLOBAL("B", value, ien) → B cross-reference (name index)
    ^GLOBAL("D", date, ien)  → D cross-reference (date index)

Zero-node field layout is defined by the data dictionary INPUT TRANSFORM
and STORAGE node.  For most files the first ~10 fields are packed into
piece positions 1-N of the zero node.

This module does a best-effort decode: it reads all nodes for each entry
and maps field values using the data dictionary.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from .connection import YdbConnection
from .data_dictionary import DataDictionary, FileDef

log = logging.getLogger(__name__)


@dataclass
class FileEntry:
    """A single entry (row) from a FileMan file."""

    ien: str                                     # internal entry number (string)
    file_number: float
    raw_nodes: dict[str, str] = field(default_factory=dict)   # node → raw string
    fields: dict[float, Any] = field(default_factory=dict)    # field# → decoded value


class FileReader:
    """Reads entries from a FileMan file.

    Usage::

        with YdbConnection.connect() as conn:
            dd = DataDictionary(conn)
            reader = FileReader(conn, dd)
            for entry in reader.iter_entries(2):   # PATIENT file
                print(entry.fields)
    """

    def __init__(self, conn: YdbConnection, dd: DataDictionary) -> None:
        self._conn = conn
        self._dd = dd

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def iter_entries(
        self, file_number: float, limit: int | None = None
    ) -> "Iterator[FileEntry]":
        """Yield FileEntry objects for every entry in the file.

        Parameters
        ----------
        file_number:
            FileMan file number (e.g. 2 for PATIENT).
        limit:
            If set, stop after this many entries.
        """
        from collections.abc import Iterator  # noqa: PLC0415

        file_def = self._dd.get_file(file_number)
        if file_def is None:
            log.warning("File %s not found in data dictionary", file_number)
            return
        global_root = _strip_root(file_def.global_root)
        count = 0
        for ien in self._conn.subscripts(global_root, [""]):
            if ien.startswith('"'):
                continue  # skip cross-reference nodes like "B", "D"
            try:
                float(ien)
            except ValueError:
                continue
            entry = self._read_entry(global_root, ien, file_number, file_def)
            yield entry
            count += 1
            if limit is not None and count >= limit:
                break

    def get_entry(self, file_number: float, ien: str) -> FileEntry | None:
        """Return a single entry by IEN, or None if it does not exist."""
        file_def = self._dd.get_file(file_number)
        if file_def is None:
            return None
        global_root = _strip_root(file_def.global_root)
        if not self._conn.node_exists(global_root, [ien]):
            return None
        return self._read_entry(global_root, ien, file_number, file_def)

    def count_entries(self, file_number: float) -> int:
        """Count entries in a file without loading them."""
        file_def = self._dd.get_file(file_number)
        if file_def is None:
            return 0
        global_root = _strip_root(file_def.global_root)
        count = 0
        for ien in self._conn.subscripts(global_root, [""]):
            if ien.startswith('"'):
                continue
            try:
                float(ien)
                count += 1
            except ValueError:
                continue
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_entry(
        self,
        global_root: str,
        ien: str,
        file_number: float,
        file_def: FileDef,
    ) -> FileEntry:
        """Read all nodes for one IEN and decode field values."""
        raw_nodes: dict[str, str] = {}

        # Read nodes 0 through 9 (covers the vast majority of fields)
        for node in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            val = self._conn.get(global_root, [ien, node])
            if val:
                raw_nodes[node] = val

        entry = FileEntry(
            ien=ien,
            file_number=file_number,
            raw_nodes=raw_nodes,
        )
        # Best-effort field decode: pieces of zero-node map to field .01, .02, ...
        # A full implementation needs the DD storage node / piece mapping.
        # For now, expose raw zero-node pieces as approximate field values.
        zero = raw_nodes.get("0", "")
        if zero:
            pieces = zero.split("^")
            for i, piece in enumerate(pieces):
                approx_field = round(0.01 * (i + 1), 2)
                entry.fields[approx_field] = piece

        return entry


def _strip_root(global_root: str) -> str:
    """Convert FileMan global root to a bare caret-name for yottadb calls.

    e.g. "^DPT(" → "^DPT"   "^PS(50," → "^PS"
    """
    root = global_root.rstrip("(").rstrip(",")
    if not root.startswith("^"):
        root = "^" + root
    return root
