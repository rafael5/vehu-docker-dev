"""
TDD tests for file_reader.py.
"""

from vista_fm_browser.data_dictionary import DataDictionary
from vista_fm_browser.file_reader import FileReader, _strip_root

# ------------------------------------------------------------------
# _strip_root
# ------------------------------------------------------------------


def test_strip_root_standard():
    assert _strip_root("^DPT(") == ("^DPT", [])


def test_strip_root_subfile():
    # ^PS(50, — file 50 DRUG — data lives under ^PS(50, ien, ...)
    assert _strip_root("^PS(50,") == ("^PS", ["50"])


def test_strip_root_no_caret():
    assert _strip_root("DPT(") == ("^DPT", [])


def test_strip_root_already_clean():
    assert _strip_root("^DPT") == ("^DPT", [])


def test_strip_root_nested_dic_file4():
    # File 4 INSTITUTION — data lives under ^DIC(4, ien, ...)
    assert _strip_root("^DIC(4,") == ("^DIC", ["4"])


def test_strip_root_nested_decimal_file():
    # File 4.005 — data lives under ^DIC(4.005, ien, ...)
    assert _strip_root("^DIC(4.005,") == ("^DIC", ["4.005"])


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


def test_get_entry_unknown_file(fake_patient_conn):
    """get_entry with unknown file number returns None (file_def is None branch)."""
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    assert reader.get_entry(999, "1") is None


def test_count_entries_unknown_file(fake_patient_conn):
    """count_entries with unknown file number returns 0 (file_def is None branch)."""
    dd = DataDictionary(fake_patient_conn)
    reader = FileReader(fake_patient_conn, dd)
    assert reader.count_entries(999) == 0


def test_iter_entries_skips_cross_ref_iens(fake_cross_ref_conn):
    """iter_entries skips IENs that start with '"' (cross-reference nodes)."""
    dd = DataDictionary(fake_cross_ref_conn)
    reader = FileReader(fake_cross_ref_conn, dd)
    entries = list(reader.iter_entries(2))
    iens = {e.ien for e in entries}
    assert '"B"' not in iens
    assert "1" in iens


def test_count_entries_skips_cross_ref_iens(fake_cross_ref_conn):
    """count_entries skips IENs that start with '"'."""
    dd = DataDictionary(fake_cross_ref_conn)
    reader = FileReader(fake_cross_ref_conn, dd)
    assert reader.count_entries(2) == 1


# ------------------------------------------------------------------
# Nested globals — regression guard for B3 (_strip_root bug).
# File 4 INSTITUTION lives at ^DIC(4, ien, 0); naive _strip_root would
# walk the ^DIC file registry and report the wrong count.
# ------------------------------------------------------------------


def test_count_entries_nested_global(fake_nested_global_conn):
    """File 4 has 5 real entries (IENs 1-5) plus the 0 header → 6.

    A naive _strip_root would walk ^DIC top-level and count file-registry
    subscripts ("1" and "4" → 2). The correct walk is ^DIC(4, ...).
    """
    dd = DataDictionary(fake_nested_global_conn)
    reader = FileReader(fake_nested_global_conn, dd)
    assert reader.count_entries(4) == 6


def test_iter_entries_nested_global(fake_nested_global_conn):
    """Iteration under a nested global yields the file's own IENs."""
    dd = DataDictionary(fake_nested_global_conn)
    reader = FileReader(fake_nested_global_conn, dd)
    entries = list(reader.iter_entries(4))
    iens = {e.ien for e in entries}
    assert iens == {"0", "1", "2", "3", "4", "5"}
    # Zero nodes must be the file-4 entry data, not the registry metadata.
    entry1 = next(e for e in entries if e.ien == "1")
    assert entry1.raw_nodes["0"].startswith("WASHINGTON DC VAMC")


def test_get_entry_nested_global(fake_nested_global_conn):
    """get_entry resolves against the nested subtree, not the registry."""
    dd = DataDictionary(fake_nested_global_conn)
    reader = FileReader(fake_nested_global_conn, dd)
    entry = reader.get_entry(4, "3")
    assert entry is not None
    assert entry.raw_nodes["0"].startswith("BOSTON VAMC")
