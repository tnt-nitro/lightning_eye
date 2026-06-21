"""SQLite database layer for Lightning Eye."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, Iterable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    distance_km REAL,
                    energy INTEGER,
                    relevant INTEGER NOT NULL DEFAULT 0,
                    block_id INTEGER,
                    temp_c REAL,
                    humidity_pct REAL
                );

                CREATE TABLE IF NOT EXISTS blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    relevant_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS boot_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    reason TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
                CREATE INDEX IF NOT EXISTS idx_events_relevant ON events(relevant);
                CREATE INDEX IF NOT EXISTS idx_events_block ON events(block_id);
                """
            )

    def log_boot(self, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO boot_log (ts, reason) VALUES (?, ?)",
                (utc_now_iso(), reason),
            )

    def create_block(self) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO blocks (started_at, relevant_count) VALUES (?, 0)",
                (utc_now_iso(),),
            )
            return int(cur.lastrowid)

    def close_block(self, block_id: int, relevant_count: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE blocks SET ended_at = ?, relevant_count = ? WHERE id = ?",
                (utc_now_iso(), relevant_count, block_id),
            )

    def get_open_block(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM blocks WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return row

    def get_block(self, block_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()

    def insert_event(
        self,
        event_type: str,
        distance_km: float | None,
        energy: int | None,
        relevant: bool,
        block_id: int | None,
        temp_c: float | None = None,
        humidity_pct: float | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events
                (ts, event_type, distance_km, energy, relevant, block_id, temp_c, humidity_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now_iso(),
                    event_type,
                    distance_km,
                    energy,
                    1 if relevant else 0,
                    block_id,
                    temp_c,
                    humidity_pct,
                ),
            )
            return int(cur.lastrowid)

    def count_events_since(self, since_iso: str, relevant_only: bool | None = None) -> int:
        query = "SELECT COUNT(*) FROM events WHERE ts >= ?"
        params: list[Any] = [since_iso]
        if relevant_only is True:
            query += " AND relevant = 1"
        elif relevant_only is False:
            query += " AND relevant = 0"
        with self.connect() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def count_events_today(self, relevant_only: bool | None = None) -> int:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.count_events_since(today.isoformat(), relevant_only)

    def has_relevant_since(self, minutes: int) -> bool:
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return self.count_events_since(since.isoformat(), relevant_only=True) > 0

    def last_relevant_event(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM events WHERE relevant = 1 ORDER BY ts DESC LIMIT 1"
            ).fetchone()

    def last_event(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM events ORDER BY ts DESC LIMIT 1").fetchone()

    def events_in_block(self, block_id: int, relevant_only: bool = False) -> list[sqlite3.Row]:
        query = "SELECT * FROM events WHERE block_id = ?"
        params: list[Any] = [block_id]
        if relevant_only:
            query += " AND relevant = 1"
        query += " ORDER BY ts ASC"
        with self.connect() as conn:
            return list(conn.execute(query, params).fetchall())

    def recent_relevant_distances(self, limit: int = 20) -> list[float]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT distance_km FROM events
                WHERE relevant = 1 AND distance_km IS NOT NULL
                ORDER BY ts DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        values = [float(r["distance_km"]) for r in rows]
        values.reverse()
        return values

    def events_since(self, since_iso: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM events WHERE ts >= ? ORDER BY ts ASC",
                    (since_iso,),
                ).fetchall()
            )

    def all_events(self) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            for row in conn.execute("SELECT * FROM events ORDER BY ts ASC"):
                yield row

    def block_stats(self, block_id: int) -> dict[str, Any]:
        events = self.events_in_block(block_id, relevant_only=True)
        block = self.get_block(block_id)
        if not block:
            return {}
        distances = [float(e["distance_km"])
                     for e in events if e["distance_km"] is not None]
        energies = [int(e["energy"])
                    for e in events if e["energy"] is not None]
        started = block["started_at"]
        ended = block["ended_at"] or utc_now_iso()
        return {
            "block_id": block_id,
            "started_at": started,
            "ended_at": block["ended_at"],
            "span_seconds": _iso_diff_seconds(started, ended),
            "relevant_count": len(events),
            "distance_min": min(distances) if distances else None,
            "distance_max": max(distances) if distances else None,
            "distance_avg": sum(distances) / len(distances) if distances else None,
            "energy_min": min(energies) if energies else None,
            "energy_max": max(energies) if energies else None,
            "energy_avg": sum(energies) / len(energies) if energies else None,
        }


def _iso_diff_seconds(start_iso: str, end_iso: str) -> float:
    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    return (end - start).total_seconds()
