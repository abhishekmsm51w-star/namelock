"""The spelling book: names the shop has already confirmed.

Two interchangeable stores:

* SQLiteBook   - a file next to the app. The default. Nothing leaves the laptop.
* PostgresBook - any Postgres, including a Tiger Cloud service. Set DATABASE_URL.
                 Needs `pip install -r requirements-tiger.txt`.

Only confirmed spellings are stored. Customer messages are never written here.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Protocol

from .lock import key, norm


class Book(Protocol):
    def approve(self, name: str) -> None: ...
    def names(self) -> list[str]: ...


class SQLiteBook:
    def __init__(self, path: str = "namelock.db") -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "create table if not exists approved_names (key text primary key, name text not null)"
        )
        self._db.commit()

    def approve(self, name: str) -> None:
        name = norm(name).strip()
        if not name:
            return
        with self._lock:
            self._db.execute(
                "insert or replace into approved_names(key, name) values (?, ?)",
                (key(name), name),
            )
            self._db.commit()

    def names(self) -> list[str]:
        with self._lock:
            rows = self._db.execute("select name from approved_names order by name").fetchall()
        return [r[0] for r in rows]


class PostgresBook:
    def __init__(self, dsn: str) -> None:
        import psycopg  # imported lazily so the app runs without it

        self._psycopg = psycopg
        self._dsn = dsn
        with self._connect() as con:
            con.execute(
                "create table if not exists approved_names "
                "(key text primary key, name text not null)"
            )

    def _connect(self):
        return self._psycopg.connect(self._dsn, autocommit=True)

    def approve(self, name: str) -> None:
        name = norm(name).strip()
        if not name:
            return
        with self._connect() as con:
            con.execute(
                "insert into approved_names(key, name) values (%s, %s) "
                "on conflict (key) do update set name = excluded.name",
                (key(name), name),
            )

    def names(self) -> list[str]:
        with self._connect() as con:
            return [r[0] for r in con.execute("select name from approved_names order by name")]


def open_book(demo: bool = False) -> Book:
    """Demo mode keeps the book in memory so a public page never stores anything."""
    if demo:
        return SQLiteBook(":memory:")
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return PostgresBook(dsn)
    return SQLiteBook(os.environ.get("NAMELOCK_DB", "namelock.db"))
