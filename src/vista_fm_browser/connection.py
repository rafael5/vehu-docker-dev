"""
YottaDB connection management.

Wraps the yottadb Python connector with helpers for FileMan global access.
Provides both a direct connection class and a context manager.

Inside the VEHU container the yottadb C extension is available.
On the host (unit tests) the module imports fine — callers must pass a
YdbFake in tests instead of calling YdbConnection.connect().
"""

import logging
from collections.abc import Iterator
from typing import Any

log = logging.getLogger(__name__)


class YdbConnection:
    """Thin wrapper around the yottadb Python connector.

    Usage::

        with YdbConnection.connect() as conn:
            value = conn.get("^DD", [200, 0])
            for sub in conn.subscripts("^DD", [200, ""]):
                ...
    """

    def __init__(self, ydb_module: Any) -> None:
        self._ydb = ydb_module

    @classmethod
    def connect(cls) -> "YdbConnection":
        """Import yottadb and return a live connection.

        Raises ImportError if the yottadb C extension is not available
        (i.e. not running inside the VEHU container).
        """
        try:
            import yottadb  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "yottadb Python connector not found. "
                "Run this inside the VEHU Docker container."
            ) from exc
        log.debug("YottaDB connection established")
        return cls(yottadb)

    def __enter__(self) -> "YdbConnection":
        return self

    def __exit__(self, *_: Any) -> None:
        pass  # yottadb manages its own connection lifecycle

    # ------------------------------------------------------------------
    # Low-level global access
    # ------------------------------------------------------------------

    def get(self, global_name: str, subscripts: list[str | int]) -> str:
        """Return the string value at global_name(subscripts).

        Returns empty string if the node has no value (but may have children).
        Raises KeyError if the node does not exist at all.
        """
        subs = [str(s) for s in subscripts]
        try:
            return self._ydb.get(global_name, subs) or ""
        except self._ydb.YDBNodeEnd:
            return ""

    def subscripts(
        self, global_name: str, subscripts: list[str | int]
    ) -> Iterator[str]:
        """Yield all subscripts at the given level.

        Example — iterate all FileMan file numbers::

            for file_num in conn.subscripts("^DD", [""]):
                ...
        """
        subs = [str(s) for s in subscripts]
        try:
            sub = self._ydb.subscript_next(global_name, subs)
            while sub:
                yield sub
                subs[-1] = sub
                sub = self._ydb.subscript_next(global_name, subs)
        except self._ydb.YDBNodeEnd:
            return

    def node_exists(self, global_name: str, subscripts: list[str | int]) -> bool:
        """Return True if the node (or its children) exist."""
        subs = [str(s) for s in subscripts]
        return self._ydb.data(global_name, subs) > 0
