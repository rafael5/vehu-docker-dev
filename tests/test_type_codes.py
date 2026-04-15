"""Tests for type_codes.decompose — FileMan type-string parser."""

from vista_fm_browser.type_codes import TypeSpec, decompose


class TestBaseTypes:
    def test_free_text(self):
        ts = decompose("F")
        assert ts.base == "F"
        assert ts.modifiers == set()
        assert not ts.required
        assert not ts.audited

    def test_numeric(self):
        assert decompose("N").base == "N"

    def test_date(self):
        assert decompose("D").base == "D"

    def test_set(self):
        assert decompose("S").base == "S"

    def test_word_processing(self):
        assert decompose("W").base == "W"

    def test_mumps(self):
        assert decompose("K").base == "K"

    def test_variable_pointer(self):
        assert decompose("V").base == "V"

    def test_computed_date(self):
        assert decompose("DC").base == "DC"


class TestPrefixFlags:
    def test_required(self):
        ts = decompose("RF")
        assert ts.base == "F"
        assert ts.required is True

    def test_audited(self):
        ts = decompose("*F")
        assert ts.base == "F"
        assert ts.audited is True

    def test_required_and_audited(self):
        ts = decompose("R*F")
        assert ts.base == "F" and ts.required and ts.audited

    def test_audited_and_required(self):
        ts = decompose("*RF")
        assert ts.base == "F" and ts.required and ts.audited


class TestModifiers:
    def test_input_transform(self):
        assert "X" in decompose("FX").modifiers

    def test_output_transform(self):
        assert "O" in decompose("FO").modifiers

    def test_both_transforms(self):
        ts = decompose("FXO")
        assert ts.base == "F" and "X" in ts.modifiers and "O" in ts.modifiers

    def test_required_with_modifiers(self):
        ts = decompose("RFX")
        assert ts.base == "F" and ts.required and "X" in ts.modifiers

    def test_date_input_transform(self):
        ts = decompose("DX")
        assert ts.base == "D" and "X" in ts.modifiers


class TestNumericJustification:
    def test_nj3_0(self):
        ts = decompose("NJ3,0")
        assert ts.base == "N"
        assert "J" in ts.modifiers
        assert ts.numeric_width == 3
        assert ts.numeric_decimals == 0

    def test_nj8_2(self):
        ts = decompose("NJ8,2")
        assert ts.numeric_width == 8 and ts.numeric_decimals == 2

    def test_nj10_2(self):
        ts = decompose("NJ10,2")
        assert ts.numeric_width == 10 and ts.numeric_decimals == 2

    def test_nj5_0_with_output_flag(self):
        ts = decompose("NJ5,0O")
        assert ts.base == "N"
        assert ts.numeric_width == 5 and ts.numeric_decimals == 0
        assert "O" in ts.modifiers


class TestPointers:
    def test_pointer_simple(self):
        ts = decompose("P2")
        assert ts.base == "P" and ts.pointer_file == 2.0

    def test_pointer_decimal(self):
        ts = decompose("P50.68")
        assert ts.pointer_file == 50.68

    def test_pointer_required_trailing_apostrophe(self):
        ts = decompose("P200'")
        assert ts.base == "P" and ts.pointer_file == 200.0
        assert ts.required is True  # trailing ' = required

    def test_pointer_with_audit_prefix(self):
        ts = decompose("*P356.8'")
        assert ts.base == "P" and ts.pointer_file == 356.8
        assert ts.audited and ts.required

    def test_multiple_pointer(self):
        ts = decompose("MP920'")
        assert ts.base == "P" and ts.pointer_file == 920.0
        assert ts.is_multiple


class TestMultiples:
    def test_multiple_by_decimal(self):
        ts = decompose("1.001")
        assert ts.base == "M"
        assert ts.is_multiple
        assert ts.multiple_file == 1.001

    def test_multiple_large_number(self):
        ts = decompose("9999999.64")
        assert ts.multiple_file == 9999999.64


class TestEdgeCases:
    def test_empty(self):
        ts = decompose("")
        assert ts.base == ""

    def test_prefix_only(self):
        assert decompose("R").base == ""

    def test_unknown_code_preserved(self):
        ts = decompose("Q")
        assert ts.base == "Q"  # graceful fallback

    def test_raw_preserved(self):
        assert decompose("NJ3,0").raw == "NJ3,0"


class TestBackwardCompat:
    """TypeSpec must preserve the (base, pointer_file) semantics of the
    legacy _extract_type_code helper so existing callers keep working."""

    def test_as_tuple_matches_legacy_free_text(self):
        ts = decompose("RF")
        assert (ts.base, ts.pointer_file) == ("F", None)

    def test_as_tuple_matches_legacy_pointer(self):
        ts = decompose("*P356.8'")
        assert (ts.base, ts.pointer_file) == ("P", 356.8)

    def test_as_tuple_matches_legacy_multiple(self):
        ts = decompose("1.001")
        assert (ts.base, ts.pointer_file) == ("M", None)
