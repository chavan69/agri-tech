"""In-memory Supabase/PostgREST stand-in used by the test suite.

Only the query features used by the API are implemented: select/insert/update/
delete, eq/neq/lt/gt/lte/gte/is_/ilike/in_/or_, order/limit/range.
"""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from postgrest.exceptions import APIError

TABLES = ("users", "market_listings", "bids", "machinery_listings", "scans")


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLES}
        self._clock = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def table(self, name: str) -> "FakeQuery":
        if name not in self.tables:
            raise AssertionError(f"Unknown table {name!r}")
        return FakeQuery(self, name)

    # -- helpers ---------------------------------------------------------
    def next_timestamp(self) -> str:
        self._clock += timedelta(seconds=1)
        return self._clock.isoformat()

    def insert_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        stored = copy.deepcopy(row)
        stored.setdefault("id", str(uuid.uuid4()))
        stored.setdefault("created_at", self.next_timestamp())
        if table in {"users", "market_listings", "machinery_listings"}:
            stored.setdefault("updated_at", stored["created_at"])
        if table in {"market_listings", "machinery_listings"}:
            stored.setdefault("status", "active")
        if table == "scans":
            stored.setdefault("prevention", [])
        if table == "users":
            stored.setdefault("role", "Farmer & Seller")
        if table == "users" and any(
            existing["phone"] == stored.get("phone") for existing in self.tables[table]
        ):
            raise APIError(
                {
                    "message": 'duplicate key value violates unique constraint "users_phone_key"',
                    "code": "23505",
                    "details": None,
                    "hint": None,
                }
            )
        self.tables[table].append(stored)
        return copy.deepcopy(stored)


class FakeQuery:
    def __init__(self, db: FakeSupabase, table: str) -> None:
        self.db = db
        self.table = table
        self._op = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._offset = 0
        self._limit: int | None = None

    # -- query builders --------------------------------------------------
    def select(self, *_columns: str, **_kwargs: Any) -> "FakeQuery":
        self._op = "select"
        return self

    def insert(self, payload: dict | list[dict]) -> "FakeQuery":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict) -> "FakeQuery":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("neq", column, value))
        return self

    def lt(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("lt", column, value))
        return self

    def gt(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("gt", column, value))
        return self

    def lte(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("lte", column, value))
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("gte", column, value))
        return self

    def is_(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("is", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self._filters.append(("in", column, values))
        return self

    def ilike(self, column: str, pattern: str) -> "FakeQuery":
        self._filters.append(("ilike", column, pattern))
        return self

    def or_(self, expression: str) -> "FakeQuery":
        parts = [part for part in expression.split(",") if part]
        self._filters.append(("or", parts))
        return self

    def order(self, column: str, desc: bool = False, **_kwargs: Any) -> "FakeQuery":
        self._orders.append((column, desc))
        return self

    def limit(self, size: int, **_kwargs: Any) -> "FakeQuery":
        self._limit = size
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self._offset = start
        self._limit = end - start + 1
        return self

    # -- execution -------------------------------------------------------
    def execute(self) -> SimpleNamespace:
        rows = self.db.tables[self.table]

        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            created = [self.db.insert_row(self.table, row) for row in payloads]
            return SimpleNamespace(data=created)

        matches = [row for row in rows if self._matches(row)]

        if self._op == "update":
            updated: list[dict[str, Any]] = []
            for row in matches:
                row.update(copy.deepcopy(self._payload))
                if "updated_at" in row:
                    row["updated_at"] = self.db.next_timestamp()
                updated.append(copy.deepcopy(row))
            return SimpleNamespace(data=updated)

        if self._op == "delete":
            deleted = [copy.deepcopy(row) for row in matches]
            for row in matches:
                rows.remove(row)
            return SimpleNamespace(data=deleted)

        for column, desc in reversed(self._orders):
            matches.sort(key=lambda row: (row.get(column) is None, row.get(column)), reverse=desc)

        end = self._offset + self._limit if self._limit is not None else None
        return SimpleNamespace(data=copy.deepcopy(matches[self._offset : end]))

    # -- filtering -------------------------------------------------------
    def _matches(self, row: dict[str, Any]) -> bool:
        for kind, *args in self._filters:
            if kind == "or":
                if not any(self._match_expression(row, expr) for expr in args[0]):
                    return False
                continue

            column, value = args
            actual = row.get(column)
            if kind == "eq" and actual != value:
                return False
            if kind == "neq" and actual == value:
                return False
            if kind == "lt" and not _compare(actual, value, lambda a, b: a < b):
                return False
            if kind == "gt" and not _compare(actual, value, lambda a, b: a > b):
                return False
            if kind == "lte" and not _compare(actual, value, lambda a, b: a <= b):
                return False
            if kind == "gte" and not _compare(actual, value, lambda a, b: a >= b):
                return False
            if kind == "is":
                if value in ("null", None) and actual is not None:
                    return False
                if value not in ("null", None) and actual != value:
                    return False
            if kind == "in" and actual not in value:
                return False
            if kind == "ilike" and not _ilike(actual, value):
                return False
        return True

    def _match_expression(self, row: dict[str, Any], expression: str) -> bool:
        column, operator, value = expression.split(".", 2)
        actual = row.get(column)
        if operator == "ilike":
            return _ilike(actual, value)
        if operator == "eq":
            return str(actual) == value
        raise AssertionError(f"Unsupported or_ operator {operator!r}")


def _compare(actual: Any, expected: Any, comparator) -> bool:
    if actual is None:
        return False
    try:
        return comparator(float(actual), float(expected))
    except (TypeError, ValueError):
        return comparator(actual, expected)


def _ilike(actual: Any, pattern: str) -> bool:
    if actual is None:
        return False
    regex = "".join(
        ".*" if char == "%" else "." if char == "_" else re.escape(char)
        for char in pattern
    )
    return re.fullmatch(regex, str(actual), flags=re.IGNORECASE) is not None
