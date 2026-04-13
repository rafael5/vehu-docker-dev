"""
TDD tests for file_reader.py.
"""

import pytest

from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader, _strip_root


# ------------------------------------------------------------------
# _strip_root
# ------------------------------------------------------------------


def test_strip_root_standard():
    assert _strip_root("^DPT(") == "^DPT"


def test_strip_root_subfile():
    assert _strip_root("^PS(50,") == "^PS"


def test_strip_root_no_caret():
    assert _strip_root("DPT(") == "^DPT"


def test_strip_root_already_clean():
    assert _strip_root("^DPT") == "^DPT"


# ------------------------------------------------------------------
# FileReader.iter_entries
# ------------------------------------------------------------------


def test_iter_entries_yields_all(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entries = list(reader.iter_entries(2))
    assert len(entries) == 3


def test_iter_entries_limit(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entries = list(reader.iter_entries(2, limit=2))
    assert len(entries) == 2


def test_iter_entries_has_ien(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entries = list(reader.iter_entries(2))
    iens = {e.ien for e in entries}
    assert iens == {"1", "2", "3"}


def test_iter_entries_has_zero_node(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entries = list(reader.iter_entries(2))
    for entry in entries:
        assert "0" in entry.raw_nodes


def test_iter_entries_file_not_found(fake_dd_conn):
    """File with no data global — should yield nothing without raising."""
    dd = DataDictionary(fake_dd_conn)
    reader = FileReader(fake_dd_conn, dd)
    entries = list(reader.iter_entries(2))  # ^DPT not in fake
    assert entries == []


def test_iter_entries_unknown_file(fake_patient_conn):
    """Unknown file number — should yield nothing without raising."""
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entries = list(reader.iter_entries(999))
    assert entries == []


# ------------------------------------------------------------------
# FileReader.get_entry
# ------------------------------------------------------------------


def test_get_entry_exists(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entry = reader.get_entry(2, "1")
    assert entry is not None
    assert entry.ien == "1"


def test_get_entry_not_found(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    assert reader.get_entry(2, "9999") is None


def test_get_entry_zero_node_content(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    entry = reader.get_entry(2, "1")
    assert entry is not None
    assert "TESTPATIENT,ONE" in entry.raw_nodes["0"]


# ------------------------------------------------------------------
# FileReader.count_entries
# ------------------------------------------------------------------


def test_count_entries(fake_patient_conn):
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    assert reader.count_entries(2) == 3


def test_count_entries_no_data(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    reader = FileReader(fake_dd_conn, dd)
    assert reader.count_entries(2) == 0
