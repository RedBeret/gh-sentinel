"""
dedup.py — SQLite-backed event deduplication store.

Tracks which events have been seen and notified so that alerts
are only sent once per event. Stored at ~/.gh-sentinel/events.db.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .monitor import Event


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventStore:
    """Persistent SQLite store for deduplication."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".gh-sentinel" / "events.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id    TEXT    NOT NULL,
                event_type  TEXT    NOT NULL,
                repo        TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                state       TEXT    NOT NULL DEFAULT '',
                seen_at     TEXT    NOT NULL,
                notified    INTEGER NOT NULL DEFAULT 0,
                UNIQUE(event_type, repo, event_id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_notified ON events(notified);
            CREATE INDEX IF NOT EXISTS idx_events_repo ON events(repo);
        """)
        self._conn.commit()

    def is_new(self, event: Event) -> bool:
        """Return True if this event has not been seen before."""
        row = self._conn.execute(
            "SELECT id FROM events WHERE event_type=? AND repo=? AND event_id=?",
            (event.event_type, event.repo, event.event_id),
        ).fetchone()
        return row is None

    def filter_new(self, events: list[Event]) -> list[Event]:
        """Return only events that haven't been seen before."""
        return [e for e in events if self.is_new(e)]

    def mark_seen(self, events: list[Event], notified: bool = True) -> None:
        """Record events as seen (and optionally notified)."""
        now = _now_iso()
        notified_int = 1 if notified else 0
        with self._conn:
            for event in events:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO events
                        (event_id, event_type, repo, title, url, state, seen_at, notified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type,
                        event.repo,
                        event.title,
                        event.url,
                        event.state,
                        now,
                        notified_int,
                    ),
                )

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Return the most recent seen events."""
        rows = self._conn.execute(
            """
            SELECT event_type, repo, event_id, title, url, state, seen_at, notified
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        notified = self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE notified=1"
        ).fetchone()[0]
        by_type = self._conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type"
        ).fetchall()
        return {
            "total": total,
            "notified": notified,
            "by_type": {row["event_type"]: row["cnt"] for row in by_type},
        }

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
