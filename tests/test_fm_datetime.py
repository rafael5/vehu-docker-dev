"""
Tests for fm_datetime — FileMan internal date/time conversion utilities.

FileMan stores dates as YYYMMDD.HHMMSS where YYY = actual_year - 1700.
Because dates are stored as floats, trailing zeros in the time fraction
are dropped (14:30:00 → .143, not .1430; 08:00:00 → .08, not .080000).
"""

from datetime import datetime

from vista_fm_browser.fm_datetime import dt_to_fm, fm_date_display, fm_to_dt

# ---------------------------------------------------------------------------
# fm_to_dt — happy path
# ---------------------------------------------------------------------------


class TestFmToDt:
    def test_simple_date(self):
        assert fm_to_dt("3160101") == datetime(2016, 1, 1)

    def test_pre_2000_date(self):
        # 245 + 1700 = 1945
        assert fm_to_dt("2450101") == datetime(1945, 1, 1)

    def test_date_with_truncated_time(self):
        # .143 → right-pad to "143000" → 14:30:00
        assert fm_to_dt("3160101.143") == datetime(2016, 1, 1, 14, 30, 0)

    def test_date_with_full_time(self):
        # .143015 → "143015" → 14:30:15
        assert fm_to_dt("3160101.143015") == datetime(2016, 1, 1, 14, 30, 15)

    def test_date_with_early_hour(self):
        # .08 → right-pad to "080000" → 08:00:00
        assert fm_to_dt("3160101.08") == datetime(2016, 1, 1, 8, 0, 0)

    def test_date_with_early_hour_and_minutes(self):
        # .083 → "083000" → 08:30:00
        assert fm_to_dt("3160101.083") == datetime(2016, 1, 1, 8, 30, 0)

    def test_fake_patient_dob_one(self):
        # TESTPATIENT,ONE DOB from conftest FAKE_PATIENT_GLOBAL
        assert fm_to_dt("2450101") == datetime(1945, 1, 1)

    def test_fake_patient_dob_two(self):
        # TESTPATIENT,TWO DOB
        assert fm_to_dt("2600615") == datetime(1960, 6, 15)

    def test_fake_patient_dob_three(self):
        # TESTPATIENT,THREE DOB
        assert fm_to_dt("2380420") == datetime(1938, 4, 20)

    def test_partial_date_month_zero_normalized(self):
        # Month 00 → treated as month 1
        result = fm_to_dt("3160001")
        assert result is not None
        assert result.year == 2016
        assert result.month == 1
        assert result.day == 1

    def test_partial_date_day_zero_normalized(self):
        result = fm_to_dt("3160100")
        assert result is not None
        assert result.month == 1
        assert result.day == 1

    def test_midnight_has_no_time_component(self):
        dt = fm_to_dt("3160101")
        assert dt is not None
        assert dt.hour == 0 and dt.minute == 0 and dt.second == 0

    def test_whitespace_stripped(self):
        assert fm_to_dt("  3160101  ") == datetime(2016, 1, 1)


# ---------------------------------------------------------------------------
# fm_to_dt — empty / sentinel / invalid
# ---------------------------------------------------------------------------


class TestFmToDtEdgeCases:
    def test_empty_string_returns_none(self):
        assert fm_to_dt("") is None

    def test_whitespace_only_returns_none(self):
        assert fm_to_dt("   ") is None

    def test_zero_returns_none(self):
        assert fm_to_dt("0") is None

    def test_invalid_string_returns_none(self):
        assert fm_to_dt("not-a-date") is None

    def test_partial_letters_returns_none(self):
        assert fm_to_dt("316ABC1") is None


# ---------------------------------------------------------------------------
# dt_to_fm — round-trip conversions
# ---------------------------------------------------------------------------


class TestDtToFm:
    def test_date_only(self):
        assert dt_to_fm(datetime(2016, 1, 1)) == "3160101"

    def test_pre_2000(self):
        assert dt_to_fm(datetime(1945, 1, 1)) == "2450101"

    def test_with_time_trailing_zeros_stripped(self):
        # 14:30:00 → "143000" → strip trailing zeros → "143"
        assert dt_to_fm(datetime(2016, 1, 1, 14, 30, 0)) == "3160101.143"

    def test_with_full_time_no_trailing_zeros(self):
        # 14:30:15 → "143015" → no trailing zeros
        assert dt_to_fm(datetime(2016, 1, 1, 14, 30, 15)) == "3160101.143015"

    def test_early_hour_trailing_zeros_stripped(self):
        # 08:00:00 → "080000" → strip → "08"
        assert dt_to_fm(datetime(2016, 1, 1, 8, 0, 0)) == "3160101.08"

    def test_midnight_has_no_decimal(self):
        result = dt_to_fm(datetime(2016, 6, 15))
        assert "." not in result

    def test_roundtrip_date_only(self):
        original = datetime(2016, 6, 15)
        assert fm_to_dt(dt_to_fm(original)) == original

    def test_roundtrip_with_time(self):
        original = datetime(2016, 6, 15, 14, 30, 15)
        assert fm_to_dt(dt_to_fm(original)) == original

    def test_roundtrip_early_hour(self):
        original = datetime(2016, 1, 1, 8, 30, 0)
        assert fm_to_dt(dt_to_fm(original)) == original


# ---------------------------------------------------------------------------
# fm_date_display — human-readable formatting
# ---------------------------------------------------------------------------


class TestFmDateDisplay:
    def test_date_only(self):
        assert fm_date_display("3160101") == "Jan 01, 2016"

    def test_month_abbreviations(self):
        months = [
            ("3160101", "Jan"),
            ("3160201", "Feb"),
            ("3160301", "Mar"),
            ("3160401", "Apr"),
            ("3160501", "May"),
            ("3160601", "Jun"),
            ("3160701", "Jul"),
            ("3160801", "Aug"),
            ("3160901", "Sep"),
            ("3161001", "Oct"),
            ("3161101", "Nov"),
            ("3161201", "Dec"),
        ]
        for fm, abbr in months:
            assert fm_date_display(fm).startswith(abbr), f"Expected {abbr} for {fm}"

    def test_with_time_component(self):
        assert fm_date_display("3160101.143") == "Jan 01, 2016 14:30:00"

    def test_include_time_false_suppresses_time(self):
        assert fm_date_display("3160101.143", include_time=False) == "Jan 01, 2016"

    def test_no_time_when_midnight(self):
        # Midnight has no time component → no time suffix even with include_time=True
        result = fm_date_display("3160101")
        assert "00:00:00" not in result

    def test_early_hour_with_time(self):
        assert fm_date_display("3160101.08") == "Jan 01, 2016 08:00:00"

    def test_empty_returns_empty_string(self):
        assert fm_date_display("") == ""

    def test_zero_returns_empty_string(self):
        assert fm_date_display("0") == ""

    def test_pre_2000_date(self):
        assert fm_date_display("2450101") == "Jan 01, 1945"

    def test_day_zero_padding(self):
        result = fm_date_display("3160102")
        assert "02" in result
