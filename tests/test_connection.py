"""
TDD tests for connection.py.

Tests the YdbFake (from conftest) and the YdbConnection contract.
No real YottaDB connection is needed.
"""

import pytest

from vista_fm_browser.connection import YdbConnection

# ------------------------------------------------------------------
# FakeYdbModule — a minimal stand-in for the yottadb C extension.
# Used to exercise YdbConnection itself (not just YdbFake).
# ------------------------------------------------------------------


class FakeYdbModule:
    """Minimal fake for the yottadb Python extension.

    Stores globals as { (global_name, sub1, sub2, ...): value }.
    """

    class YDBNodeEnd(Exception):
        pass

    def __init__(self, data: dict[tuple, str]) -> None:
        self._data = data

    def get(self, global_name: str, subs: list[str]) -> str:
        key = (global_name, *subs)
        val = self._data.get(key)
        if val is None:
            raise self.YDBNodeEnd()
        return val

    def subscript_next(self, global_name: str, subs: list[str]) -> str:
        """Return the next subscript after subs[-1] at the given level."""
        prefix = (global_name, *subs[:-1])
        current = subs[-1]
        candidates = sorted(
            k[len(prefix)]
            for k in self._data
            if len(k) > len(prefix)
            and k[: len(prefix)] == prefix
            and isinstance(k[len(prefix)], str)
        )
        for cand in candidates:
            if cand > current:
                return cand
        raise self.YDBNodeEnd()

    def data(self, global_name: str, subs: list[str]) -> int:
        prefix = (global_name, *subs)
        for key in self._data:
            if key[: len(prefix)] == prefix:
                return 11 if len(key) == len(prefix) else 10
        return 0


# ------------------------------------------------------------------
# YdbFake (testing the fake itself)
# ------------------------------------------------------------------


def test_fake_get_existing_node(fake_dd_conn):
    val = fake_dd_conn.get("^DD", ["2", "0"])
    assert val == "FIELD^NL^3160101^4"


def test_fake_get_missing_node(fake_dd_conn):
    val = fake_dd_conn.get("^DD", ["999", "0"])
    assert val == ""


def test_fake_subscripts_top_level(fake_dd_conn):
    subs = list(fake_dd_conn.subscripts("^DD", [""]))
    assert "2" in subs
    assert "50" in subs


def test_fake_subscripts_field_level(fake_dd_conn):
    subs = list(fake_dd_conn.subscripts("^DD", ["2", ""]))
    assert ".01" in subs
    assert ".02" in subs
    assert ".03" in subs


def test_fake_subscripts_no_duplicates(fake_dd_conn):
    subs = list(fake_dd_conn.subscripts("^DD", [""]))
    assert len(subs) == len(set(subs))


def test_fake_node_exists_true(fake_dd_conn):
    assert fake_dd_conn.node_exists("^DD", ["2", "0"])


def test_fake_node_exists_partial(fake_dd_conn):
    """node_exists should return True for parent nodes even without a value."""
    assert fake_dd_conn.node_exists("^DD", ["2"])


def test_fake_node_exists_false(fake_dd_conn):
    assert not fake_dd_conn.node_exists("^DD", ["999"])


def test_fake_context_manager(fake_dd_conn):
    with fake_dd_conn as conn:
        val = conn.get("^DD", ["2", "0"])
    assert val == "FIELD^NL^3160101^4"


# ------------------------------------------------------------------
# YdbConnection.connect() — host guard
# ------------------------------------------------------------------


def test_connect_raises_outside_container():
    """connect() must raise ImportError on host where yottadb is not installed."""
    with pytest.raises(ImportError, match="VEHU Docker"):
        YdbConnection.connect()


# ------------------------------------------------------------------
# YdbConnection with FakeYdbModule — exercises the real connection class
# ------------------------------------------------------------------

_FAKE_DATA = {
    ("^DD", "2", "0"): "PATIENT^DPT(^",
    ("^DD", "2", ".01", "0"): "NAME^F^^",
    ("^DD", "50", "0"): "DRUG^PS(50,^",
}


def _make_conn() -> YdbConnection:
    return YdbConnection(FakeYdbModule(_FAKE_DATA))


def test_ydb_conn_get_existing():
    conn = _make_conn()
    assert conn.get("^DD", ["2", "0"]) == "PATIENT^DPT(^"


def test_ydb_conn_get_missing_returns_empty():
    conn = _make_conn()
    assert conn.get("^DD", ["999", "0"]) == ""


def test_ydb_conn_subscripts_yields_keys():
    conn = _make_conn()
    subs = list(conn.subscripts("^DD", [""]))
    assert "2" in subs
    assert "50" in subs


def test_ydb_conn_subscripts_empty_when_none():
    conn = _make_conn()
    assert list(conn.subscripts("^DD", ["999", ""])) == []


def test_ydb_conn_node_exists_true():
    conn = _make_conn()
    assert conn.node_exists("^DD", ["2", "0"])


def test_ydb_conn_node_exists_false():
    conn = _make_conn()
    assert not conn.node_exists("^DD", ["999"])


def test_ydb_conn_context_manager():
    conn = _make_conn()
    with conn as c:
        val = c.get("^DD", ["2", "0"])
    assert val == "PATIENT^DPT(^"
