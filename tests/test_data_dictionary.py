"""
TDD tests for data_dictionary.py.

All tests use YdbFake — no YottaDB connection required.
"""

import pytest

from vista_fm_browser.data_dictionary import (
    DataDictionary,
    FileDef,
    FieldDef,
    _fmt_file_num,
    _parse_field_zero,
)


# ------------------------------------------------------------------
# _fmt_file_num
# ------------------------------------------------------------------


def test_fmt_file_num_integer():
    assert _fmt_file_num(2.0) == "2"


def test_fmt_file_num_decimal():
    assert _fmt_file_num(2.04) == "2.04"


def test_fmt_file_num_large():
    assert _fmt_file_num(8925.0) == "8925"


# ------------------------------------------------------------------
# _parse_field_zero
# ------------------------------------------------------------------


def test_parse_field_zero_free_text():
    fld = _parse_field_zero(2, 0.01, "NAME^F^^PATIENT NAME")
    assert fld.label == "NAME"
    assert fld.datatype_code == "F"
    assert fld.datatype_name == "FREE TEXT"
    assert fld.title == "PATIENT NAME"


def test_parse_field_zero_set_of_codes():
    fld = _parse_field_zero(2, 0.02, "SEX^S^^")
    assert fld.datatype_code == "S"
    assert fld.datatype_name == "SET OF CODES"


def test_parse_field_zero_date():
    fld = _parse_field_zero(2, 0.03, "DATE OF BIRTH^D^^")
    assert fld.datatype_code == "D"
    assert fld.datatype_name == "DATE/TIME"


def test_parse_field_zero_unknown_type():
    fld = _parse_field_zero(2, 99, "CUSTOM^X^^")
    assert fld.datatype_code == "X"
    assert fld.datatype_name == "X"  # falls back to the raw code


def test_parse_field_zero_empty():
    fld = _parse_field_zero(2, 0, "")
    assert fld.label == ""
    assert fld.datatype_code == ""


# ------------------------------------------------------------------
# DataDictionary.list_files
# ------------------------------------------------------------------


def test_list_files_returns_files(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    files = dd.list_files()
    assert len(files) == 2
    nums = [n for n, _ in files]
    assert 2.0 in nums
    assert 50.0 in nums


def test_list_files_sorted_ascending(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    files = dd.list_files()
    nums = [n for n, _ in files]
    assert nums == sorted(nums)


def test_list_files_labels(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    files = dd.list_files()
    label_map = {n: lbl for n, lbl in files}
    assert label_map[2.0] == "PATIENT"
    assert label_map[50.0] == "DRUG"


# ------------------------------------------------------------------
# DataDictionary.get_file
# ------------------------------------------------------------------


def test_get_file_patient(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    fd = dd.get_file(2)
    assert fd is not None
    assert fd.label == "PATIENT"
    assert fd.global_root == "DPT("
    assert fd.file_number == 2.0


def test_get_file_not_found(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    assert dd.get_file(999) is None


def test_get_file_caches_result(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    fd1 = dd.get_file(2)
    fd2 = dd.get_file(2)
    assert fd1 is fd2  # same object


def test_get_file_has_fields(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    fd = dd.get_file(2)
    assert fd is not None
    assert len(fd.fields) > 0


def test_get_file_field_labels(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    fd = dd.get_file(2)
    assert fd is not None
    labels = {f.label for f in fd.fields.values()}
    assert "NAME" in labels
    assert "SEX" in labels
    assert "DATE OF BIRTH" in labels


def test_get_file_set_of_codes_values(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    fd = dd.get_file(2)
    assert fd is not None
    sex_field = next(f for f in fd.fields.values() if f.label == "SEX")
    assert sex_field.set_values == {"M": "MALE", "F": "FEMALE"}


def test_get_file_field_count(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    fd = dd.get_file(2)
    assert fd is not None
    assert fd.field_count == len(fd.fields)


# ------------------------------------------------------------------
# DataDictionary.search_files
# ------------------------------------------------------------------


def test_search_files_match(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    results = dd.search_files("patient")
    assert len(results) == 1
    assert results[0][1] == "PATIENT"


def test_search_files_case_insensitive(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    assert dd.search_files("DRUG") == dd.search_files("drug")


def test_search_files_no_match(fake_dd_conn):
    dd = DataDictionary(fake_dd_conn)
    assert dd.search_files("ZZZNOTAFILE") == []
