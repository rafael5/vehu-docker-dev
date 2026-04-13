"""
Tests for FileInventory — reads File 1 (^DIC) and File 9.4 (PACKAGE) to
produce the complete file/package map for planning VistA data analysis.

Unit tests use YdbFake with FAKE_DIC + FAKE_DD fixture data.
Integration tests run inside the VEHU container against live ^DIC.

^DIC global layout (FileMan FILE file, #1):
    ^DIC(file#, 0)                    = "label^global_root^date^..."
    ^DIC("B", label, file#)           = B cross-reference

^DIC(9.4, ...) — PACKAGE file (#9.4):
    ^DIC(9.4, pkg_ien, 0)             = "name^prefix^version^..."
    ^DIC(9.4, pkg_ien, 11, ien, 0)    = "file_number"   (FILE multiple, field .01)
"""

import pytest

from vista_fm_browser.inventory import FileInventory

# ---------------------------------------------------------------------------
# Shared fixture data — mirrors real ^DIC structure
# ---------------------------------------------------------------------------

FAKE_DIC: dict = {
    "^DIC": {
        # File 2 — PATIENT (DG package, ien 1)
        ("2", "0"): "PATIENT^DPT(^3160101^",
        # File 44 — HOSPITAL LOCATION (SDAM scheduling, ien 2)
        ("44", "0"): "HOSPITAL LOCATION^SC(^3160101^",
        # File 50 — DRUG (PSS pharmacy, ien 3)
        ("50", "0"): "DRUG^PS(50,^3160101^",
        # File 200 — NEW PERSON (XU kernel, ien 4)
        ("200", "0"): "NEW PERSON^VA(200,^3160101^",
        # File 9.4 — PACKAGE (meta — the package file itself)
        ("9.4", "0"): "PACKAGE^DIC(9.4,^3160101^",
        # ---- Package file 9.4 entries ----
        # Package 1: REGISTRATION (DG)
        ("9.4", "1", "0"): "REGISTRATION^DG^22.0^",
        ("9.4", "1", "11", "1", "0"): "2",  # File 2 belongs to DG
        ("9.4", "1", "11", "2", "0"): "44",  # File 44 belongs to DG
        # Package 2: PHARMACY DATA MANAGEMENT (PSS)
        ("9.4", "2", "0"): "PHARMACY DATA MANAGEMENT^PSS^1.0^",
        ("9.4", "2", "11", "1", "0"): "50",  # File 50 belongs to PSS
        # Package 3: KERNEL (XU) — no FILE multiple entries in this fixture
        ("9.4", "3", "0"): "KERNEL^XU^8.0^",
        # B cross-reference entries (FileMan name index — skip in numeric scan)
        ('"B"', "PATIENT", "2"): "",
        ('"B"', "HOSPITAL LOCATION", "44"): "",
        ('"B"', "DRUG", "50"): "",
        ('"B"', "NEW PERSON", "200"): "",
    }
}

# ^DD data for field counts (mirrors FAKE_DD in conftest, kept local to avoid
# importing from the tests package which is not on sys.path as a package)
FAKE_DD_FOR_INVENTORY: dict = {
    "^DD": {
        # File 2 — PATIENT: 4 fields
        ("2", "0"): "PATIENT^DPT(^3160101^",
        ("2", ".01", "0"): "NAME^F^^PATIENT NAME",
        ("2", ".02", "0"): "SEX^S^^",
        ("2", ".03", "0"): "DATE OF BIRTH^D^^",
        ("2", "9999999", "0"): "INTEGRATION CONTROL NUMBER^N^^ICN",
        # File 50 — DRUG: 2 fields
        ("50", "0"): "DRUG^PS(50,^3160101^",
        ("50", ".01", "0"): "GENERIC NAME^F^^",
        ("50", "100", "0"): "PSNDF VA PRODUCT NAME ENTRY^P50.68^^",
        # File 44 and 200 intentionally have no DD entries
    }
}


def _make_inventory_conn():
    """YdbFake with ^DIC + ^DD data combined."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    # Use conftest's YdbFake directly via the conftest module already loaded
    import conftest

    from vista_fm_browser.connection import YdbConnection  # noqa: F401

    data: dict = {}
    data.update(FAKE_DIC)
    data.update(FAKE_DD_FOR_INVENTORY)
    return conftest.YdbFake(data)


@pytest.fixture
def inv_conn():
    return _make_inventory_conn()


@pytest.fixture
def inventory(inv_conn) -> FileInventory:
    fi = FileInventory(inv_conn)
    fi.load()
    return fi


# ---------------------------------------------------------------------------
# PackageInfo unit tests
# ---------------------------------------------------------------------------


class TestPackageReading:
    def test_package_count(self, inventory):
        pkgs = inventory.list_packages()
        assert len(pkgs) == 3

    def test_package_names(self, inventory):
        names = {p.name for p in inventory.list_packages()}
        assert "REGISTRATION" in names
        assert "PHARMACY DATA MANAGEMENT" in names
        assert "KERNEL" in names

    def test_package_prefix(self, inventory):
        pkgs = {p.name: p for p in inventory.list_packages()}
        assert pkgs["REGISTRATION"].prefix == "DG"
        assert pkgs["PHARMACY DATA MANAGEMENT"].prefix == "PSS"
        assert pkgs["KERNEL"].prefix == "XU"

    def test_package_version(self, inventory):
        pkgs = {p.name: p for p in inventory.list_packages()}
        assert pkgs["REGISTRATION"].version == "22.0"
        assert pkgs["KERNEL"].version == "8.0"

    def test_package_file_numbers(self, inventory):
        pkgs = {p.name: p for p in inventory.list_packages()}
        assert set(pkgs["REGISTRATION"].file_numbers) == {2.0, 44.0}
        assert set(pkgs["PHARMACY DATA MANAGEMENT"].file_numbers) == {50.0}

    def test_package_with_no_files(self, inventory):
        pkgs = {p.name: p for p in inventory.list_packages()}
        assert pkgs["KERNEL"].file_numbers == []


# ---------------------------------------------------------------------------
# FileRecord unit tests
# ---------------------------------------------------------------------------


class TestFileReading:
    def test_files_include_patient_and_drug(self, inventory):
        nums = {f.file_number for f in inventory.list_files()}
        assert 2.0 in nums
        assert 50.0 in nums

    def test_file_label(self, inventory):
        by_num = {f.file_number: f for f in inventory.list_files()}
        assert by_num[2.0].label == "PATIENT"
        assert by_num[50.0].label == "DRUG"
        assert by_num[200.0].label == "NEW PERSON"

    def test_file_global_root(self, inventory):
        by_num = {f.file_number: f for f in inventory.list_files()}
        assert by_num[2.0].global_root == "^DPT("
        assert by_num[50.0].global_root == "^PS(50,"

    def test_files_sorted_by_number(self, inventory):
        nums = [f.file_number for f in inventory.list_files()]
        assert nums == sorted(nums)

    def test_non_numeric_nodes_skipped(self, inventory):
        # "B" cross-reference and similar should not appear as file records
        labels = {f.label for f in inventory.list_files()}
        assert "B" not in labels

    def test_package_name_resolved(self, inventory):
        by_num = {f.file_number: f for f in inventory.list_files()}
        assert by_num[2.0].package_name == "REGISTRATION"
        assert by_num[50.0].package_name == "PHARMACY DATA MANAGEMENT"

    def test_package_prefix_resolved(self, inventory):
        by_num = {f.file_number: f for f in inventory.list_files()}
        assert by_num[2.0].package_prefix == "DG"
        assert by_num[44.0].package_prefix == "DG"

    def test_unpackaged_file_has_none_package(self, inventory):
        # File 200 is not in any package's FILE multiple in our fixture
        by_num = {f.file_number: f for f in inventory.list_files()}
        assert by_num[200.0].package_name is None

    def test_field_count_populated(self, inventory):
        # PATIENT file has fields .01, .02, .03, 9999999 in FAKE_DD
        by_num = {f.file_number: f for f in inventory.list_files()}
        patient = by_num[2.0]
        assert patient.field_count is not None
        assert patient.field_count == 4

    def test_field_count_none_when_no_dd(self, inventory):
        # File 44 has no ^DD entries in our fixture
        by_num = {f.file_number: f for f in inventory.list_files()}
        assert by_num[44.0].field_count == 0


# ---------------------------------------------------------------------------
# files_by_package tests
# ---------------------------------------------------------------------------


class TestFilesByPackage:
    def test_returns_dict_keyed_by_package_name(self, inventory):
        grouped = inventory.files_by_package()
        assert "REGISTRATION" in grouped
        assert "PHARMACY DATA MANAGEMENT" in grouped

    def test_registration_files(self, inventory):
        grouped = inventory.files_by_package()
        nums = {f.file_number for f in grouped["REGISTRATION"]}
        assert nums == {2.0, 44.0}

    def test_unpackaged_key(self, inventory):
        grouped = inventory.files_by_package()
        assert "(unpackaged)" in grouped
        unpackaged_nums = {f.file_number for f in grouped["(unpackaged)"]}
        assert 200.0 in unpackaged_nums


# ---------------------------------------------------------------------------
# summary() tests
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_has_total_files(self, inventory):
        s = inventory.summary()
        assert s["total_files"] >= 4

    def test_summary_has_total_packages(self, inventory):
        s = inventory.summary()
        assert s["total_packages"] == 3

    def test_summary_has_top_packages(self, inventory):
        s = inventory.summary()
        assert "top_packages_by_file_count" in s
        assert isinstance(s["top_packages_by_file_count"], list)

    def test_summary_top_package_is_registration(self, inventory):
        s = inventory.summary()
        top = s["top_packages_by_file_count"]
        assert top[0]["name"] == "REGISTRATION"
        assert top[0]["file_count"] == 2


# ---------------------------------------------------------------------------
# to_dict / serialization tests
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_has_files_and_packages(self, inventory):
        d = inventory.to_dict()
        assert "files" in d
        assert "packages" in d

    def test_to_dict_files_are_serializable(self, inventory):
        import json

        d = inventory.to_dict()
        # Should not raise
        json.dumps(d)

    def test_file_entry_has_required_keys(self, inventory):
        d = inventory.to_dict()
        patient = next(f for f in d["files"] if f["file_number"] == 2.0)
        assert patient["label"] == "PATIENT"
        assert patient["global_root"] == "^DPT("
        assert "package_name" in patient
        assert "field_count" in patient


# ---------------------------------------------------------------------------
# Integration tests — run inside VEHU container
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFileInventoryIntegration:
    """
    Run inside the container:
        source /etc/yottadb/env   (or ydb_env_set)
        pytest tests/ -m integration -v
    """

    def test_loads_without_error(self):
        from vista_fm_browser.connection import YdbConnection

        with YdbConnection.connect() as conn:
            fi = FileInventory(conn)
            fi.load()

    def test_finds_patient_file(self):
        from vista_fm_browser.connection import YdbConnection

        with YdbConnection.connect() as conn:
            fi = FileInventory(conn)
            fi.load()
            by_num = {f.file_number: f for f in fi.list_files()}
        assert 2.0 in by_num
        assert by_num[2.0].label == "PATIENT"

    def test_finds_multiple_packages(self):
        from vista_fm_browser.connection import YdbConnection

        with YdbConnection.connect() as conn:
            fi = FileInventory(conn)
            fi.load()
            pkgs = fi.list_packages()
        assert len(pkgs) > 10, "Expected many VistA packages"

    def test_total_file_count_plausible(self):
        from vista_fm_browser.connection import YdbConnection

        with YdbConnection.connect() as conn:
            fi = FileInventory(conn)
            fi.load()
            files = fi.list_files()
        # A full VistA instance has thousands of files
        assert len(files) > 100

    def test_summary_serializable(self):
        import json

        from vista_fm_browser.connection import YdbConnection

        with YdbConnection.connect() as conn:
            fi = FileInventory(conn)
            fi.load()
            s = fi.summary()
        json.dumps(s)  # must not raise
