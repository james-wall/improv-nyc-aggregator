from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'knowledge.db')


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS shows (
                id             INTEGER PRIMARY KEY,
                url            TEXT UNIQUE NOT NULL,
                title          TEXT,
                venue          TEXT,
                source         TEXT,
                category       TEXT,
                description    TEXT,
                is_class_show  INTEGER NOT NULL DEFAULT 0,
                show_format    TEXT,
                price          TEXT,
                run_start      TEXT,
                run_end        TEXT,
                first_seen     TEXT NOT NULL,
                last_seen      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS occurrences (
                id          INTEGER PRIMARY KEY,
                show_id     INTEGER NOT NULL REFERENCES shows(id),
                start_time  TEXT NOT NULL,
                UNIQUE(show_id, start_time)
            );
        """)
        # Migrations for existing DBs
        for stmt in [
            "ALTER TABLE shows ADD COLUMN is_class_show INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE shows ADD COLUMN show_format TEXT",
            "ALTER TABLE shows ADD COLUMN price TEXT",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


@contextmanager
def _conn():
    conn = sqlite3.connect(os.path.abspath(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_show(url: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM shows WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None


def upsert_show(
    url: str,
    title: str,
    venue: str,
    source: str,
    description: str = None,
    category: str = None,
    is_class_show: bool = False,
    show_format: str = None,
    price: str = None,
    run_start: str = None,
    run_end: str = None,
) -> int:
    """Insert or update a show. Returns the show's id.

    For description, category, and show_format, existing values are preserved
    if the new value is None — so callers can upsert partial data without
    clobbering previously fetched fields.
    """
    now = datetime.utcnow().isoformat()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id, first_seen FROM shows WHERE url = ?", (url,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE shows
                SET title          = ?,
                    venue          = ?,
                    source         = ?,
                    description    = COALESCE(?, description),
                    category       = COALESCE(?, category),
                    is_class_show  = ?,
                    show_format    = COALESCE(?, show_format),
                    price          = COALESCE(?, price),
                    run_start      = COALESCE(?, run_start),
                    run_end        = COALESCE(?, run_end),
                    last_seen      = ?
                WHERE url = ?
                """,
                (title, venue, source, description, category, int(is_class_show), show_format, price, run_start, run_end, now, url),
            )
            return existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO shows
                    (url, title, venue, source, description, category, is_class_show, show_format, price, run_start, run_end, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (url, title, venue, source, description, category, int(is_class_show), show_format, price, run_start, run_end, now, now),
            )
            return cur.lastrowid


def upsert_occurrence(show_id: int, start_time: str):
    """Record a specific date/time instance of a show. Silently no-ops on duplicates."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO occurrences (show_id, start_time) VALUES (?, ?)",
            (show_id, start_time),
        )


def get_upcoming_shows(days: int = 7) -> list[dict]:
    """Return shows with occurrences falling within the next `days` days."""
    now = datetime.utcnow()
    end = now + timedelta(days=days)
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*, o.start_time
            FROM occurrences o
            JOIN shows s ON s.id = o.show_id
            WHERE o.start_time >= ? AND o.start_time <= ?
            ORDER BY o.start_time
            """,
            (now.isoformat(), end.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]
