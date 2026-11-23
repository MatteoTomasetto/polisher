"""Local SQLite log of every replacement, so an original is never lost."""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from . import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    app TEXT, mode TEXT, provider TEXT,
    original TEXT NOT NULL, result TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class Entry:
    id: int
    ts: float
    app: str
    mode: str
    provider: str
    original: str
    result: str


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.history_file()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def _conn(self):
        return closing(sqlite3.connect(self.path))

    def add(self, *, app: str, mode: str, provider: str, original: str, result: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO history (ts, app, mode, provider, original, result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), app, mode, provider, original, result),
            )
            conn.commit()

    def recent(self, limit: int = 20) -> list[Entry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, app, mode, provider, original, result "
                "FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Entry(*row) for row in rows]

    def get(self, entry_id: int) -> Entry | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, ts, app, mode, provider, original, result FROM history WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return Entry(*row) if row else None

    def clear(self) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM history")
            conn.commit()
