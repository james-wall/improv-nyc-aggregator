"""Extract individual performer names from show descriptions using Gemini.

Runs after scraping, before curation. For each show that hasn't been
processed yet, sends its description to a cheap LLM call and upserts
any discovered performers into the DB.
"""

from __future__ import annotations

import json
import os
import re
import time

from google import genai
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-2.5-flash"

_EXTRACTION_PROMPT = """\
Given the show title and description below, extract any clear individual human performer names.

Rules:
- Only include full names of individual people (e.g. "Mike Birbiglia", "Amy Poehler")
- Skip improv team names, sketch group names, show titles, and venue names
- Skip vague references like "special guests", "the cast", "our performers"
- If the description has no clearly named individuals, return an empty list
- Names like "ASSSSCAT with Amy Poehler" → extract "Amy Poehler"
- Names like "Team Harold" or "The Beatrice" → skip (these are group names)

Show title: {title}
Description: {description}

Return ONLY valid JSON: {{"names": ["Full Name", ...]}}
"""


def extract_performers_from_events(events: list, batch_size: int = 10) -> int:
    """Extract performer names from event descriptions and upsert into the DB.

    Skips events that have already been processed. Returns the count of new
    performers discovered across all events.
    """
    from src.store import db as store
    from src.store import performers as perf_store

    store.init_db()
    _ensure_extracted_column()

    # Only process events with a URL and description that haven't been processed
    to_process = [
        e for e in events
        if e.url and e.description and not _already_extracted(e.url)
    ]

    if not to_process:
        return 0

    print(f"\n🎭 Extracting performers from {len(to_process)} show descriptions...")
    new_performers = 0

    for i, event in enumerate(to_process):
        names = _extract_names(event.title or "", event.description or "")
        _mark_extracted(event.url)

        if names:
            print(f"  Found: {', '.join(names)} — {event.title[:50]}")
            show_record = store.get_show(event.url)
            for name in names:
                pid = perf_store.upsert_performer(name=name, home_venue=event.venue)
                if show_record:
                    perf_store.link_performer_to_show(show_record["id"], pid)
                new_performers += 1

        # Gentle rate limiting
        if (i + 1) % batch_size == 0:
            time.sleep(1)

    print(f"  ✓ {new_performers} performer record(s) created/updated")
    return new_performers


def _extract_names(title: str, description: str) -> list[str]:
    """Call Gemini to extract individual human names from a description."""
    prompt = _EXTRACTION_PROMPT.format(
        title=title[:200],
        description=description[:800],
    )
    try:
        response = _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        text = (response.text or "").strip()
        # Strip code fences if present
        fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        data = json.loads(text)
        names = data.get("names", [])
        return [n.strip() for n in names if isinstance(n, str) and len(n.strip()) > 3]
    except Exception as e:
        # Non-fatal — just skip this description
        return []


def _ensure_extracted_column():
    """Add performers_extracted column to shows if it doesn't exist yet."""
    from src.store.db import _conn
    with _conn() as conn:
        try:
            conn.execute(
                "ALTER TABLE shows ADD COLUMN performers_extracted INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # already exists


def _already_extracted(url: str) -> bool:
    from src.store.db import _conn
    with _conn() as conn:
        row = conn.execute(
            "SELECT performers_extracted FROM shows WHERE url = ?", (url,)
        ).fetchone()
        return bool(row and row["performers_extracted"])


def _mark_extracted(url: str):
    from src.store.db import _conn
    with _conn() as conn:
        conn.execute(
            "UPDATE shows SET performers_extracted = 1 WHERE url = ?", (url,)
        )
