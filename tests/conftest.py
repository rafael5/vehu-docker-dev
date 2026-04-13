"""
Test configuration and shared fixtures.

Unit tests use YdbFake — an in-memory fake that accepts the same interface as
YdbConnection.  This means unit tests run on the host with no YottaDB dependency.

Integration tests (marked @pytest.mark.integration) run only inside the VEHU
container where the real yottadb C extension is available.
"""

import sys
from pathlib import Path

# Make src/ importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


class YdbFake:
    """In-memory fake for YdbConnection.

    Stores globals as a nested dict:
        _data[global_name][tuple(subs)] = value

    Supports get(), subscripts(), node_exists() — same interface as YdbConnection.
    """

    def __init__(self, data: dict | None = None) -> None:
        # data: { "^DD": { ("200", "0"): "PATIENT^DPT^...", ... }, ... }
        self._data: dict[str, dict[tuple, str]] = {}
        if data:
            for gname, nodes in data.items():
                self._data[gname] = {
                    tuple(str(s) for s in k): v for k, v in nodes.items()
                }

    def get(self, global_name: str, subscripts: list) -> str:
        key = tuple(str(s) for s in subscripts)
        return self._data.get(global_name, {}).get(key, "")

    def subscripts(self, global_name: str, subscripts: list):
        """Yield all subscripts at the given level in sorted order."""
        prefix = tuple(str(s) for s in subscripts[:-1])
        nodes = self._data.get(global_name, {})
        seen: set[str] = set()
        for key in sorted(nodes.keys()):
            if len(key) > len(prefix) and key[: len(prefix)] == prefix:
                sub = key[len(prefix)]
                if sub not in seen:
                    seen.add(sub)
                    yield sub

    def node_exists(self, global_name: str, subscripts: list) -> bool:
        prefix = tuple(str(s) for s in subscripts)
        nodes = self._data.get(global_name, {})
        return any(key[: len(prefix)] == prefix for key in nodes)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


# ------------------------------------------------------------------
# Shared fake data
# ------------------------------------------------------------------

FAKE_DD = {
    "^DD": {
        # File 2 — PATIENT
        ("2", "0"): "PATIENT^DPT(^3160101^",
        ("2", ".01", "0"): "NAME^F^^PATIENT NAME",
        ("2", ".02", "0"): "SEX^S^^",
        ("2", ".02", "V", "M"): "MALE",
        ("2", ".02", "V", "F"): "FEMALE",
        ("2", ".03", "0"): "DATE OF BIRTH^D^^",
        ("2", "9999999", "0"): "INTEGRATION CONTROL NUMBER^N^^ICN",
        # File 50 — DRUG
        ("50", "0"): "DRUG^PS(50,^3160101^",
        ("50", ".01", "0"): "GENERIC NAME^F^^",
        ("50", "100", "0"): "PSNDF VA PRODUCT NAME ENTRY^P50.68^^",
    }
}

FAKE_PATIENT_GLOBAL = {
    "^DPT": {
        ("1", "0"): "TESTPATIENT,ONE^M^2450101^",
        ("2", "0"): "TESTPATIENT,TWO^F^2600615^",
        ("3", "0"): "TESTPATIENT,THREE^M^2380420^",
    }
}


def make_combined_fake() -> YdbFake:
    combined: dict = {}
    combined.update(FAKE_DD)
    combined.update(FAKE_PATIENT_GLOBAL)
    return YdbFake(combined)


@pytest.fixture
def fake_dd_conn() -> YdbFake:
    """YdbFake loaded with the data dictionary fixture only."""
    return YdbFake(FAKE_DD)


@pytest.fixture
def fake_patient_conn() -> YdbFake:
    """YdbFake with both DD and PATIENT data."""
    return make_combined_fake()


@pytest.fixture
def fake_cross_ref_conn() -> YdbFake:
    """YdbFake with DD + one patient entry and a B cross-reference node.

    Used to test that iter_entries / count_entries skips IENs starting with '"'.
    """
    data: dict = {}
    data.update(FAKE_DD)
    data["^DPT"] = {
        ("1", "0"): "TESTPATIENT,ONE^M^2450101^",
        ('"B"', "TESTPATIENT,ONE", "1"): "1",  # cross-reference node — must be skipped
    }
    return YdbFake(data)
