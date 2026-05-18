"""CRUD operations for performers, show_performers, and performer_links."""

from __future__ import annotations

from datetime import datetime
from src.store.db import _conn, init_db


def upsert_performer(
    name: str,
    ig_handle: str | None = None,
    ig_confidence: str | None = None,
    twitter_handle: str | None = None,
    tiktok_handle: str | None = None,
    youtube_handle: str | None = None,
    imdb_url: str | None = None,
    website: str | None = None,
    bio: str | None = None,
    home_venue: str | None = None,
) -> int:
    """Insert or update a performer. Returns the performer's id.

    Existing fields are preserved when None is passed, so callers can
    update a single field without clobbering others.
    """
    init_db()
    now = datetime.utcnow().isoformat()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM performers WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE performers
                SET ig_handle      = COALESCE(?, ig_handle),
                    ig_confidence  = COALESCE(?, ig_confidence),
                    twitter_handle = COALESCE(?, twitter_handle),
                    tiktok_handle  = COALESCE(?, tiktok_handle),
                    youtube_handle = COALESCE(?, youtube_handle),
                    imdb_url       = COALESCE(?, imdb_url),
                    website        = COALESCE(?, website),
                    bio            = COALESCE(?, bio),
                    home_venue     = COALESCE(?, home_venue),
                    updated_at     = ?
                WHERE id = ?
                """,
                (ig_handle, ig_confidence, twitter_handle, tiktok_handle,
                 youtube_handle, imdb_url, website, bio, home_venue,
                 now, existing["id"]),
            )
            return existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO performers
                    (name, ig_handle, ig_confidence, twitter_handle, tiktok_handle,
                     youtube_handle, imdb_url, website, bio, home_venue,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, ig_handle, ig_confidence, twitter_handle, tiktok_handle,
                 youtube_handle, imdb_url, website, bio, home_venue, now, now),
            )
            return cur.lastrowid


def upsert_performer_link(
    performer_id: int,
    source_name: str,
    url: str,
    confidence: str = "auto",
):
    """Insert or update a profile link for a performer."""
    init_db()
    now = datetime.utcnow().isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO performer_links (performer_id, source_name, url, confidence, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(performer_id, source_name) DO UPDATE SET url = excluded.url,
                confidence = excluded.confidence
            """,
            (performer_id, source_name, url, confidence, now),
        )


def get_performer_links(performer_id: int) -> list[dict]:
    """Return all profile links for a performer."""
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM performer_links WHERE performer_id = ? ORDER BY source_name",
            (performer_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def link_performer_to_show(show_id: int, performer_id: int, role: str = "performer"):
    """Associate a performer with a show. Silently ignores duplicates."""
    init_db()
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO show_performers (show_id, performer_id, role) VALUES (?, ?, ?)",
            (show_id, performer_id, role),
        )


def get_performer(name: str) -> dict | None:
    """Look up a performer by name (case-insensitive)."""
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM performers WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return dict(row) if row else None


def get_performers_for_show_url(show_url: str) -> list[dict]:
    """Return all performers linked to a show identified by URL."""
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT p.*, sp.role
            FROM performers p
            JOIN show_performers sp ON sp.performer_id = p.id
            JOIN shows s ON s.id = sp.show_id
            WHERE s.url = ?
            ORDER BY p.name
            """,
            (show_url,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_performers(home_venue: str | None = None) -> list[dict]:
    """Return all performers, optionally filtered by home venue."""
    init_db()
    with _conn() as conn:
        if home_venue:
            rows = conn.execute(
                "SELECT * FROM performers WHERE home_venue = ? COLLATE NOCASE ORDER BY name",
                (home_venue,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM performers ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def search_performers(query: str) -> list[dict]:
    """Full-text search over name, ig_handle, and home_venue."""
    init_db()
    q = f"%{query}%"
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM performers
            WHERE name LIKE ? OR ig_handle LIKE ? OR home_venue LIKE ?
            ORDER BY name
            """,
            (q, q, q),
        ).fetchall()
        return [dict(r) for r in rows]
