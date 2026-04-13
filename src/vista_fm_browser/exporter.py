"""
Export FileMan data to JSON and CSV files.

Writes structured exports of:
  - The full data dictionary (all files and fields)
  - Individual file contents (all entries)
  - Summary statistics

Output goes to ~/data/vista-fm-browser/output/ by default.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .data_dictionary import DataDictionary, FieldDef, FileDef
from .file_reader import FileEntry, FileReader

log = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path.home() / "data" / "vista-fm-browser" / "output"


class Exporter:
    """Export FileMan data to JSON / CSV.

    Usage::

        exp = Exporter(dd, reader, output_dir=Path("/tmp/export"))
        exp.export_data_dictionary()
        exp.export_file(2, limit=1000)
    """

    def __init__(
        self,
        dd: DataDictionary,
        reader: FileReader,
        output_dir: Path = DEFAULT_OUTPUT,
    ) -> None:
        self._dd = dd
        self._reader = reader
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Data dictionary exports
    # ------------------------------------------------------------------

    def export_data_dictionary(self) -> Path:
        """Write the full data dictionary to dd_files.json and dd_fields.csv.

        Returns the output directory path.
        """
        files_list = self._dd.list_files()
        log.info("Exporting data dictionary: %d files", len(files_list))

        # --- dd_files.json: one entry per file
        files_data: list[dict[str, Any]] = []
        fields_rows: list[dict[str, Any]] = []

        for file_num, _label in files_list:
            file_def = self._dd.get_file(file_num)
            if file_def is None:
                continue
            files_data.append(_file_def_to_dict(file_def))
            for fld in file_def.fields.values():
                fields_rows.append(_field_def_to_dict(fld))

        files_path = self.output_dir / "dd_files.json"
        files_path.write_text(
            json.dumps(files_data, indent=2, default=str), encoding="utf-8"
        )
        log.info("Wrote %s", files_path)

        fields_path = self.output_dir / "dd_fields.csv"
        _write_csv(fields_path, fields_rows)
        log.info("Wrote %s", fields_path)

        return self.output_dir

    def export_file_schema(self, file_number: float) -> Path:
        """Write a single file's field schema to fields_<file_number>.csv."""
        file_def = self._dd.get_file(file_number)
        if file_def is None:
            raise ValueError(f"File {file_number} not found in data dictionary")
        rows = [_field_def_to_dict(f) for f in file_def.fields.values()]
        out = self.output_dir / f"fields_{_fn(file_number)}.csv"
        _write_csv(out, rows)
        log.info("Wrote %s", out)
        return out

    # ------------------------------------------------------------------
    # File data exports
    # ------------------------------------------------------------------

    def export_file(self, file_number: float, limit: int | None = None) -> Path:
        """Write all entries from file_number to data_<file_number>.csv.

        Parameters
        ----------
        file_number:
            FileMan file number.
        limit:
            Optional cap on number of entries exported.
        """
        file_def = self._dd.get_file(file_number)
        if file_def is None:
            raise ValueError(f"File {file_number} not found in data dictionary")

        log.info(
            "Exporting file %s (%s)%s",
            file_number,
            file_def.label,
            f" limit={limit}" if limit else "",
        )

        rows: list[dict[str, Any]] = []
        for entry in self._reader.iter_entries(file_number, limit=limit):
            rows.append(_entry_to_dict(entry))

        out = self.output_dir / f"data_{_fn(file_number)}.csv"
        _write_csv(out, rows)
        log.info("Wrote %d entries to %s", len(rows), out)
        return out

    def export_file_json(self, file_number: float, limit: int | None = None) -> Path:
        """Write all entries from file_number to data_<file_number>.json."""
        file_def = self._dd.get_file(file_number)
        if file_def is None:
            raise ValueError(f"File {file_number} not found in data dictionary")

        entries = list(self._reader.iter_entries(file_number, limit=limit))
        data = [_entry_to_dict(e) for e in entries]
        out = self.output_dir / f"data_{_fn(file_number)}.json"
        out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        log.info("Wrote %d entries to %s", len(data), out)
        return out

    def export_summary(self) -> Path:
        """Write a summary CSV: file_number, label, global_root, field_count."""
        files_list = self._dd.list_files()
        rows = []
        for file_num, label in files_list:
            file_def = self._dd.get_file(file_num)
            rows.append(
                {
                    "file_number": file_num,
                    "label": label,
                    "global_root": file_def.global_root if file_def else "",
                    "field_count": file_def.field_count if file_def else 0,
                }
            )
        out = self.output_dir / "summary.csv"
        _write_csv(out, rows)
        log.info("Wrote summary: %d files → %s", len(rows), out)
        return out


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _file_def_to_dict(fd: FileDef) -> dict[str, Any]:
    return {
        "file_number": fd.file_number,
        "label": fd.label,
        "global_root": fd.global_root,
        "field_count": fd.field_count,
    }


def _field_def_to_dict(f: FieldDef) -> dict[str, Any]:
    return {
        "file_number": f.file_number,
        "field_number": f.field_number,
        "label": f.label,
        "datatype_code": f.datatype_code,
        "datatype_name": f.datatype_name,
        "title": f.title,
        "pointer_file": f.pointer_file,
        "set_values": json.dumps(f.set_values) if f.set_values else "",
    }


def _entry_to_dict(e: FileEntry) -> dict[str, Any]:
    row: dict[str, Any] = {"ien": e.ien, "file_number": e.file_number}
    row.update({f"field_{k}": v for k, v in e.fields.items()})
    return row


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fn(file_number: float) -> str:
    """File number as a safe filename component."""
    return str(file_number).replace(".", "_")
