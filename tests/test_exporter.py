"""
TDD tests for exporter.py.
"""

import csv
import json
from pathlib import Path

import pytest

from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.exporter import Exporter
from vista_fm_browser.file_reader import FileReader


@pytest.fixture
def exporter(fake_patient_conn, tmp_path):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    return Exporter(dd, reader, output_dir=tmp_path)


# ------------------------------------------------------------------
# export_data_dictionary
# ------------------------------------------------------------------


def test_export_dd_creates_files_json(exporter, tmp_path):
    exporter.export_data_dictionary()
    assert (tmp_path / "dd_files.json").exists()


def test_export_dd_creates_fields_csv(exporter, tmp_path):
    exporter.export_data_dictionary()
    assert (tmp_path / "dd_fields.csv").exists()


def test_export_dd_files_json_content(exporter, tmp_path):
    exporter.export_data_dictionary()
    data = json.loads((tmp_path / "dd_files.json").read_text())
    labels = [d["label"] for d in data]
    assert "PATIENT" in labels
    assert "DRUG" in labels


def test_export_dd_fields_csv_has_rows(exporter, tmp_path):
    exporter.export_data_dictionary()
    rows = list(csv.DictReader((tmp_path / "dd_fields.csv").open()))
    assert len(rows) > 0
    assert "label" in rows[0]
    assert "datatype_name" in rows[0]


# ------------------------------------------------------------------
# export_file_schema
# ------------------------------------------------------------------


def test_export_file_schema_creates_csv(exporter, tmp_path):
    out = exporter.export_file_schema(2)
    assert out.exists()
    assert "2" in out.name


def test_export_file_schema_unknown_raises(exporter):
    with pytest.raises(ValueError, match="999"):
        exporter.export_file_schema(999)


# ------------------------------------------------------------------
# export_file
# ------------------------------------------------------------------


def test_export_file_creates_csv(exporter, tmp_path):
    out = exporter.export_file(2)
    assert out.exists()


def test_export_file_has_correct_row_count(exporter, tmp_path):
    out = exporter.export_file(2)
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 3  # 3 entries in FAKE_PATIENT_GLOBAL


def test_export_file_limit(exporter, tmp_path):
    out = exporter.export_file(2, limit=2)
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 2


def test_export_file_has_ien_column(exporter, tmp_path):
    out = exporter.export_file(2)
    rows = list(csv.DictReader(out.open()))
    assert "ien" in rows[0]


def test_export_file_unknown_raises(exporter):
    with pytest.raises(ValueError, match="999"):
        exporter.export_file(999)


# ------------------------------------------------------------------
# export_file_json
# ------------------------------------------------------------------


def test_export_file_json_creates_file(exporter, tmp_path):
    out = exporter.export_file_json(2)
    assert out.exists()
    assert out.suffix == ".json"


def test_export_file_json_content(exporter, tmp_path):
    out = exporter.export_file_json(2)
    data = json.loads(out.read_text())
    assert len(data) == 3
    assert "ien" in data[0]


# ------------------------------------------------------------------
# export_summary
# ------------------------------------------------------------------


def test_export_summary_creates_csv(exporter, tmp_path):
    out = exporter.export_summary()
    assert out.exists()
    assert out.name == "summary.csv"


def test_export_summary_has_both_files(exporter, tmp_path):
    out = exporter.export_summary()
    rows = list(csv.DictReader(out.open()))
    labels = [r["label"] for r in rows]
    assert "PATIENT" in labels
    assert "DRUG" in labels
