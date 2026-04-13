"""
TDD tests for connection.py.

Tests the YdbFake (from conftest) and the YdbConnection contract.
No real YottaDB connection is needed.
"""

import pytest

from vista_fm_browser.connection import YdbConnection


# ------------------------------------------------------------------
# YdbFake (testing the fake itself)
# ------------------------------------------------------------------


def test_fake_get_existing_node(fake_dd_conn):
    val = fake_dd_conn.get("^DD", ["2", "0"])
    assert val == "PATIENT^DPT(^3160101^"


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
    assert val == "PATIENT^DPT(^3160101^"


# ------------------------------------------------------------------
# YdbConnection.connect() — host guard
# ------------------------------------------------------------------


def test_connect_raises_outside_container():
    """connect() must raise ImportError on host where yottadb is not installed."""
    with pytest.raises(ImportError, match="VEHU Docker"):
        YdbConnection.connect()
