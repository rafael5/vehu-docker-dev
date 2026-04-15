"""Tests for attribution heuristics."""

from vista_fm_browser.attribution import (
    PackageRange,
    attribute_by_prefix,
    attribute_by_range_canonical,
    attribute_by_range_empirical,
    attribute_all,
    build_empirical_ranges,
    longest_prefix_match,
    namespace_from_global,
)


class TestNamespaceExtraction:
    def test_simple(self):
        assert namespace_from_global("^PSDRUG(") == "PSDRUG"

    def test_with_comma_inside(self):
        assert namespace_from_global("^DIC(9.4,") == "DIC"

    def test_dd_with_quoted_sub(self):
        assert namespace_from_global('^DD("IX",') == "DD"

    def test_empty(self):
        assert namespace_from_global("") == ""

    def test_no_caret(self):
        assert namespace_from_global("DPT(") == "DPT"


class TestLongestPrefixMatch:
    def test_exact(self):
        pkgs = [("PS", "PHARMACY"), ("PSO", "OUTPATIENT PHARMACY")]
        assert longest_prefix_match("PS", pkgs) == ("PS", "PHARMACY")

    def test_longest_wins(self):
        pkgs = [("PS", "PHARMACY"), ("PSO", "OUTPATIENT PHARMACY")]
        assert longest_prefix_match("PSODRUG", pkgs) == ("PSO", "OUTPATIENT PHARMACY")

    def test_no_match(self):
        assert longest_prefix_match("XYZ", [("PS", "PHARMACY")]) is None

    def test_empty_namespace(self):
        assert longest_prefix_match("", [("PS", "PHARMACY")]) is None


class TestPrefixAttribution:
    def test_high_confidence_exact(self):
        pkgs = [("PS", "PHARMACY")]
        a = attribute_by_prefix(50.0, "DRUG", "^PS(", pkgs)
        # namespace="PS" exactly matches prefix "PS" → high
        assert a is not None
        assert a.candidate_package == "PHARMACY"
        assert a.confidence == "high"

    def test_med_confidence_longer_namespace(self):
        pkgs = [("MAG", "IMAGING")]
        a = attribute_by_prefix(2005.0, "IMAGE", "^MAGV(", pkgs)
        assert a is not None
        assert a.candidate_package == "IMAGING"
        assert a.confidence == "med"

    def test_no_prefix_match(self):
        pkgs = [("PS", "PHARMACY")]
        assert attribute_by_prefix(9.8, "X", "^XUSEC(", pkgs) is None


class TestEmpiricalRanges:
    def test_build(self):
        files = [
            {"file_number": 50, "package_name": "PHARMACY", "package_prefix": "PS"},
            {"file_number": 55, "package_name": "PHARMACY", "package_prefix": "PS"},
            {"file_number": 57, "package_name": "PHARMACY", "package_prefix": "PS"},
            {"file_number": 2, "package_name": "REGISTRATION", "package_prefix": "DG"},
        ]
        ranges = build_empirical_ranges(files)
        ranges_by_name = {r.name: r for r in ranges}
        assert ranges_by_name["PHARMACY"].min_num == 50
        assert ranges_by_name["PHARMACY"].max_num == 57
        assert ranges_by_name["PHARMACY"].anchor_count == 3

    def test_empirical_hit_med(self):
        ranges = [PackageRange("PHARMACY", "PS", 50, 57, 3)]
        a = attribute_by_range_empirical(53, "X", "^PS(", ranges)
        assert a and a.candidate_package == "PHARMACY" and a.confidence == "med"

    def test_empirical_hit_low_few_anchors(self):
        ranges = [PackageRange("X", "X", 90, 92, 2)]
        a = attribute_by_range_empirical(91, "X", "^X(", ranges)
        assert a and a.confidence == "low"

    def test_empirical_miss(self):
        ranges = [PackageRange("PHARMACY", "PS", 50, 57, 3)]
        assert attribute_by_range_empirical(80, "X", "^X(", ranges) is None

    def test_empirical_ambiguous(self):
        ranges = [
            PackageRange("A", "A", 0, 100, 5),
            PackageRange("B", "B", 50, 200, 5),
        ]
        # 60 falls inside both → ambiguous → None
        assert attribute_by_range_empirical(60, "X", "^X(", ranges) is None


class TestCanonicalRange:
    def test_pharmacy_range(self):
        a = attribute_by_range_canonical(55.0, "X", "^PS(")
        assert a and a.candidate_package == "PHARMACY"
        assert a.confidence == "low"

    def test_registration_range(self):
        # 2.0–2.999 is PATIENT, not listed; skip
        pass

    def test_out_of_any_range(self):
        assert attribute_by_range_canonical(999999.0, "X", "^X(") is None


class TestOrchestration:
    def test_prefix_beats_range(self):
        unp = [{"file_number": 55, "label": "X", "global_root": "^PS("}]
        pkgs = [("PS", "PHARMACY")]
        ranges = [PackageRange("OTHER", "OT", 50, 60, 5)]
        out = attribute_all(unp, pkgs, ranges)
        assert out[0].method == "prefix"
        assert out[0].candidate_package == "PHARMACY"

    def test_falls_through_to_canonical(self):
        # Namespace won't match, no empirical range covers 55, canonical does
        unp = [{"file_number": 55, "label": "X", "global_root": "^ZZZ("}]
        out = attribute_all(unp, [("PS", "PHARMACY")], [])
        # Empirical empty → canonical kicks in → PHARMACY
        assert out[0].method == "range_canonical"

    def test_no_match_yields_blank(self):
        unp = [{"file_number": 999999, "label": "X", "global_root": "^ZZZ("}]
        out = attribute_all(unp, [], [])
        assert out[0].method == "" and out[0].candidate_package is None
