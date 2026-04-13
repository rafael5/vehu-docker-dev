"""
TDD tests for data_dictionary.py.

All tests use YdbFake — no YottaDB connection required.
"""

import conftest

from vista_fm_browser.data_dictionary import (
    CrossRefInfo,
    DataDictionary,
    FieldAttributes,
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


# ------------------------------------------------------------------
# Extended fake data for new method tests
# ------------------------------------------------------------------

FAKE_DD_EXTENDED = {
    "^DD": {
        # PATIENT file with extended nodes
        ("2", "0"): "PATIENT^DPT(^3160101^",
        ("2", ".01", "0"): "NAME^F^0;1^PATIENT NAME",
        ("2", ".01", "1"): "K:$L(X)>30 X",  # INPUT TRANSFORM
        ("2", ".01", "3"): "ENTER PATIENT NAME",  # HELP PROMPT
        ("2", ".01", "DT"): "3160101",  # DATE LAST EDITED
        ("2", ".02", "0"): "SEX^S^0;2^",
        ("2", ".02", "V", "M"): "MALE",
        ("2", ".02", "V", "F"): "FEMALE",
        ("2", ".03", "0"): "DATE OF BIRTH^D^0;3^",
        # DRUG file with pointer field
        ("50", "0"): "DRUG^PS(50,^3160101^",
        ("50", ".01", "0"): "GENERIC NAME^F^0;1^",
        ("50", "2", "0"): "VA PRODUCT NAME ENTRY^P50.68^0;2^",
    }
}

FAKE_INDEX = {
    "^.11": {
        # File 2 cross-references
        ("1", "0"): "2^B^REGULAR",
        ("2", "0"): "2^AC^MUMPS",
        # File 50 cross-references
        ("3", "0"): "50^B^REGULAR",
    }
}

FAKE_POINTER_TARGET = {
    "^DPT": {
        ("1", "0"): "SMITH,JOHN^M^2450101^",
        ("2", "0"): "JONES,JANE^F^2600615^",
    }
}


def _make_ext_conn():
    data: dict = {}
    data.update(FAKE_DD_EXTENDED)
    return conftest.YdbFake(data)


def _make_ext_with_index():
    data: dict = {}
    data.update(FAKE_DD_EXTENDED)
    data.update(FAKE_INDEX)
    return conftest.YdbFake(data)


def _make_ext_with_pointer_data():
    data: dict = {}
    data.update(FAKE_DD_EXTENDED)
    data.update(FAKE_POINTER_TARGET)
    return conftest.YdbFake(data)


# ------------------------------------------------------------------
# _parse_field_zero — pointer field extraction
# ------------------------------------------------------------------


def test_parse_field_zero_pointer_extracts_file_number():
    fld = _parse_field_zero(50, 2, "VA PRODUCT NAME ENTRY^P50.68^0;2^")
    assert fld.datatype_code == "P"
    assert fld.datatype_name == "POINTER"
    assert fld.pointer_file == 50.68


def test_parse_field_zero_pointer_integer_file():
    fld = _parse_field_zero(50, 3, "PATIENT^P2^0;3^")
    assert fld.datatype_code == "P"
    assert fld.pointer_file == 2.0


def test_parse_field_zero_pointer_normalizes_code_to_P():
    # Raw type "P50.68" should become just "P"
    fld = _parse_field_zero(50, 2, "SOMETHING^P50.68^^")
    assert fld.datatype_code == "P"


def test_parse_field_zero_non_pointer_unaffected():
    fld = _parse_field_zero(2, 0.01, "NAME^F^^PATIENT NAME")
    assert fld.datatype_code == "F"
    assert fld.pointer_file is None


# ------------------------------------------------------------------
# DataDictionary.get_field_attributes
# ------------------------------------------------------------------


class TestGetFieldAttributes:
    def test_returns_field_attributes_object(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(2, 0.01)
        assert isinstance(fa, FieldAttributes)

    def test_basic_label_and_type(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(2, 0.01)
        assert fa is not None
        assert fa.label == "NAME"
        assert fa.datatype_code == "F"

    def test_input_transform_read(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(2, 0.01)
        assert fa is not None
        assert fa.input_transform == "K:$L(X)>30 X"

    def test_help_prompt_read(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(2, 0.01)
        assert fa is not None
        assert fa.help_prompt == "ENTER PATIENT NAME"

    def test_last_edited_read(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(2, 0.01)
        assert fa is not None
        assert fa.last_edited == "3160101"

    def test_pointer_file_extracted(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(50, 2)
        assert fa is not None
        assert fa.datatype_code == "P"
        assert fa.pointer_file == 50.68

    def test_set_values_included(self):
        dd = DataDictionary(_make_ext_conn())
        fa = dd.get_field_attributes(2, 0.02)
        assert fa is not None
        assert fa.set_values == {"M": "MALE", "F": "FEMALE"}

    def test_missing_field_returns_none(self):
        dd = DataDictionary(_make_ext_conn())
        assert dd.get_field_attributes(2, 999) is None

    def test_missing_file_returns_none(self):
        dd = DataDictionary(_make_ext_conn())
        assert dd.get_field_attributes(999, 0.01) is None

    def test_nodes_default_to_empty_when_absent(self):
        dd = DataDictionary(_make_ext_conn())
        # DATE OF BIRTH field has no extended nodes in our fixture
        fa = dd.get_field_attributes(2, 0.03)
        assert fa is not None
        assert fa.input_transform == ""
        assert fa.help_prompt == ""


# ------------------------------------------------------------------
# DataDictionary.format_external
# ------------------------------------------------------------------


class TestFormatExternal:
    def _dd(self):
        return DataDictionary(_make_ext_conn())

    def test_free_text_returned_as_is(self):
        dd = self._dd()
        fa = dd.get_field_attributes(2, 0.01)
        assert fa is not None
        assert dd.format_external(fa, "SMITH,JOHN") == "SMITH,JOHN"

    def test_set_of_codes_resolved_to_label(self):
        dd = self._dd()
        fa = dd.get_field_attributes(2, 0.02)
        assert fa is not None
        assert dd.format_external(fa, "M") == "MALE"
        assert dd.format_external(fa, "F") == "FEMALE"

    def test_set_of_codes_unknown_code_returned_as_is(self):
        dd = self._dd()
        fa = dd.get_field_attributes(2, 0.02)
        assert fa is not None
        assert dd.format_external(fa, "X") == "X"

    def test_date_converted_to_display_format(self):
        dd = self._dd()
        fa = dd.get_field_attributes(2, 0.03)
        assert fa is not None
        result = dd.format_external(fa, "2450101")
        assert result == "Jan 01, 1945"

    def test_date_empty_returns_empty(self):
        dd = self._dd()
        fa = dd.get_field_attributes(2, 0.03)
        assert fa is not None
        assert dd.format_external(fa, "") == ""

    def test_pointer_without_resolve_returns_ien(self):
        dd = self._dd()
        fa = dd.get_field_attributes(50, 2)
        assert fa is not None
        result = dd.format_external(fa, "1")
        assert "1" in result  # IEN 1 appears in the result

    def test_pointer_with_resolve_looks_up_name(self):
        data: dict = {}
        data.update(FAKE_DD_EXTENDED)
        # Add a simple target file (pretend file 50.68 global is ^DPT)
        # We'll test pointer resolution for file 2 → pointing back at itself
        # For simplicity: add a pointer field pointing to PATIENT (file 2)
        data["^DD"][("50", "3", "0")] = "PATIENT POINTER^P2^0;3^"
        data["^DPT"] = {
            ("1", "0"): "SMITH,JOHN^M^2450101^",
        }
        dd = DataDictionary(conftest.YdbFake(data))
        fa = dd.get_field_attributes(50, 3)
        assert fa is not None
        result = dd.format_external(fa, "1", resolve_pointer=True)
        assert result == "SMITH,JOHN"

    def test_empty_internal_value_returns_empty(self):
        dd = self._dd()
        fa = dd.get_field_attributes(2, 0.01)
        assert fa is not None
        assert dd.format_external(fa, "") == ""


# ------------------------------------------------------------------
# DataDictionary.list_cross_refs
# ------------------------------------------------------------------


class TestListCrossRefs:
    def test_returns_list(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(2)
        assert isinstance(refs, list)

    def test_finds_refs_for_file(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(2)
        assert len(refs) == 2

    def test_ref_names(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(2)
        names = {r.name for r in refs}
        assert "B" in names
        assert "AC" in names

    def test_ref_types(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(2)
        by_name = {r.name: r for r in refs}
        assert by_name["B"].xref_type == "REGULAR"
        assert by_name["AC"].xref_type == "MUMPS"

    def test_ref_file_number(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(2)
        assert all(r.file_number == 2.0 for r in refs)

    def test_no_refs_for_unknown_file(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(999)
        assert refs == []

    def test_only_returns_refs_for_requested_file(self):
        dd = DataDictionary(_make_ext_with_index())
        refs_2 = dd.list_cross_refs(2)
        refs_50 = dd.list_cross_refs(50)
        names_2 = {r.name for r in refs_2}
        names_50 = {r.name for r in refs_50}
        assert names_2 != names_50 or not refs_2  # different files, different refs

    def test_returns_cross_ref_info_objects(self):
        dd = DataDictionary(_make_ext_with_index())
        refs = dd.list_cross_refs(2)
        assert all(isinstance(r, CrossRefInfo) for r in refs)
