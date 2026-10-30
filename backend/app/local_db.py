"""SQLite-backed stand-in for supabase-py (offline development mode).

The API only uses a small slice of the PostgREST query builder (``table``,
``select``, ``insert``, ``update``, ``delete``, ``eq``/``is_``/``or_``,
``order``, ``limit`` and ``range``).  This module implements that slice on top
of a single SQLite file so the app is fully usable before a Supabase project
exists:

* rows are stored as JSON documents, filtered/sorted in Python (fine for demo
  data volumes),
* data survives restarts,
* the same validation errors (e.g. duplicate phone number -> ``23505``) are
  raised as :class:`postgrest.exceptions.APIError`, so the HTTP error handlers
  behave identically in both modes.

Switch to the real database by setting ``SUPABASE_URL`` and
``SUPABASE_SERVICE_KEY``; nothing else changes.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from postgrest.exceptions import APIError

TABLE_NAMES = ("users", "market_listings", "bids", "machinery_listings", "scans")
_UPDATED_AT_TABLES = {"users", "market_listings", "machinery_listings"}
_DEFAULTS: dict[str, dict[str, Any]] = {
    "users": {"role": "Farmer & Seller"},
    "market_listings": {"status": "active"},
    "machinery_listings": {"status": "active"},
    "scans": {"prevention": []},
}

SEED_MARKET = (
    {
        "name": "Organic Roma Tomatoes",
        "category": "Vegetables",
        "mode": "auction",
        "price": 28.00,
        "current_bid": 32.00,
        "quantity": "450 kg",
        "seller": "Ramesh Gowda",
        "phone": "+91 98450 11223",
        "location": "Mandya",
        "image": "https://images.unsplash.com/photo-1592924357228-91a4daadcfea"
        "?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Premium Sona Masoori Rice",
        "category": "Grains",
        "mode": "direct",
        "price": 54.00,
        "current_bid": None,
        "quantity": "1,200 kg",
        "seller": "Basavaraj Patil",
        "phone": "+91 97312 44556",
        "location": "Raichur",
        "image": "https://images.unsplash.com/photo-1586201375761-83865001e31c"
        "?auto=format&fit=crop&w=600&q=80",
    },
)

SEED_MACHINERY = (
    {
        "title": "Mahindra 575 DI Tractor + Rotavator",
        "type": "available",
        "category": "Heavy Machinery",
        "rate": "\u20b9850 / hour",
        "owner": "Suresh Tractor",
        "phone": "+91 98801 33445",
        "location": "Hubballi",
        "specs": "45 HP with experienced driver",
    },
    {
        "title": "5HP Solar Water Pump & Panel Kit",
        "type": "available",
        "category": "Smart Equipment",
        "rate": "\u20b9450 / day",
        "owner": "GreenSun",
        "phone": "+91 96112 55667",
        "location": "Belagavi",
        "specs": "Portable solar panels included",
    },
)


class LocalSupabase:
    """A tiny subset of ``supabase.Client`` backed by SQLite."""

    provider = "local-sqlite"

    def __init__(self, path: str | os.PathLike[str], seed: bool = True) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._last_timestamp = 0.0
        self._init_schema()
        if seed:
            self._seed()

    # -- storage ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists local_rows (
                    table_name text not null,
                    row_id     text not null,
                    doc        text not null,
                    primary key (table_name, row_id)
                )
                """
            )

    def _seed(self) -> None:
        if not self._load("market_listings"):
            for row in SEED_MARKET:
                self.insert_row("market_listings", row)
        if not self._load("machinery_listings"):
            for row in SEED_MACHINERY:
                self.insert_row("machinery_listings", row)

    def _load(self, table: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select doc from local_rows where table_name = ? order by rowid",
                (table,),
            ).fetchall()
        return [json.loads(row["doc"]) for row in rows]

    def _save(self, table: str, row: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert or replace into local_rows (table_name, row_id, doc) values (?, ?, ?)",
                (table, row["id"], json.dumps(row, ensure_ascii=False)),
            )

    def _remove(self, table: str, row_ids: list[str]) -> None:
        if not row_ids:
            return
        with self._connect() as connection:
            connection.executemany(
                "delete from local_rows where table_name = ? and row_id = ?",
                [(table, row_id) for row_id in row_ids],
            )

    # -- helpers ---------------------------------------------------------
    def next_timestamp(self) -> str:
        with self._lock:
            now = time.time()
            if now <= self._last_timestamp:
                now = self._last_timestamp + 0.000001
            self._last_timestamp = now
        return datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="microseconds")

    def insert_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table not in TABLE_NAMES:
            raise AssertionError(f"Unknown table {table!r}")

        stored = copy.deepcopy(dict(row))
        stored.setdefault("id", str(uuid.uuid4()))
        stored.setdefault("created_at", self.next_timestamp())
        if table in _UPDATED_AT_TABLES:
            stored.setdefault("updated_at", stored["created_at"])
        for column, value in _DEFAULTS.get(table, {}).items():
            stored.setdefault(column, copy.deepcopy(value))

        if table == "users" and any(
            existing.get("phone") == stored.get("phone") for existing in self._load(table)
        ):
            raise APIError(
                {
                    "message": 'duplicate key value violates unique constraint "users_phone_key"',
                    "code": "23505",
                    "details": None,
                    "hint": None,
                }
            )

        self._save(table, stored)
        return copy.deepcopy(stored)

    def delete_rows(self, table: str, row_ids: list[str]) -> None:
        self._remove(table, row_ids)
        if table == "market_listings":
            bid_ids = [
                bid["id"]
                for bid in self._load("bids")
                if bid.get("listing_id") in set(row_ids)
            ]
            self._remove("bids", bid_ids)

    def table(self, name: str) -> "LocalQuery":
        if name not in TABLE_NAMES:
            raise AssertionError(f"Unknown table {name!r}")
        return LocalQuery(self, name)


class LocalQuery:
    """Mirrors the PostgREST builder methods the API relies on."""

    def __init__(self, db: LocalSupabase, table: str) -> None:
        self.db = db
        self.table = table
        self._op = "select"
        self._payload: Any = None
        self._columns = "*"
        self._filters: list[tuple[str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._offset = 0
        self._limit: int | None = None

    # -- builders --------------------------------------------------------
    def select(self, *columns: str, **_kwargs: Any) -> "LocalQuery":
        self._op = "select"
        self._columns = ",".join(columns) if columns else "*"
        return self

    def insert(self, payload: dict | list[dict]) -> "LocalQuery":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict) -> "LocalQuery":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> "LocalQuery":
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("neq", column, value))
        return self

    def lt(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("lt", column, value))
        return self

    def gt(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("gt", column, value))
        return self

    def lte(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("lte", column, value))
        return self

    def gte(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("gte", column, value))
        return self

    def is_(self, column: str, value: Any) -> "LocalQuery":
        self._filters.append(("is", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "LocalQuery":
        self._filters.append(("in", column, list(values)))
        return self

    def ilike(self, column: str, pattern: str) -> "LocalQuery":
        self._filters.append(("ilike", column, pattern))
        return self

    def or_(self, expression: str) -> "LocalQuery":
        self._filters.append(("or", [part for part in expression.split(",") if part]))
        return self

    def order(self, column: str, desc: bool = False, **_kwargs: Any) -> "LocalQuery":
        self._orders.append((column, desc))
        return self

    def limit(self, size: int, offset: int = 0, **_kwargs: Any) -> "LocalQuery":
        self._limit = size
        self._offset = offset
        return self

    def range(self, start: int, end: int) -> "LocalQuery":
        self._offset = start
        self._limit = end - start + 1
        return self

    # -- execution -------------------------------------------------------
    def execute(self) -> SimpleNamespace:
        with self.db._lock:
            if self._op == "insert":
                payloads = self._payload if isinstance(self._payload, list) else [self._payload]
                return SimpleNamespace(
                    data=[self.db.insert_row(self.table, row) for row in payloads]
                )

            rows = self.db._load(self.table)
            matches = [row for row in rows if self._matches(row)]

            if self._op == "update":
                now = self.db.next_timestamp()
                updated: list[dict[str, Any]] = []
                for row in matches:
                    row.update(copy.deepcopy(self._payload))
                    if "updated_at" in row:
                        row["updated_at"] = now
                    self.db._save(self.table, row)
                    updated.append(copy.deepcopy(row))
                return SimpleNamespace(data=updated)

            if self._op == "delete":
                deleted = [copy.deepcopy(row) for row in matches]
                self.db.delete_rows(self.table, [row["id"] for row in deleted])
                return SimpleNamespace(data=deleted)

            for column, descending in reversed(self._orders):
                matches.sort(
                    key=lambda row, col=column: (
                        row.get(col) is None,
                        row.get(col) if row.get(col) is not None else "",
                    ),
                    reverse=descending,
                )

            end = self._offset + self._limit if self._limit is not None else None
            page = matches[self._offset : end]
            return SimpleNamespace(data=self._project(copy.deepcopy(page)))

    def _project(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        columns = [column.strip() for column in self._columns.split(",") if column.strip()]
        if not columns or "*" in columns:
            return rows
        return [{key: row.get(key) for key in columns if key in row} for row in rows]

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
