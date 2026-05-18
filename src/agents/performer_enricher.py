"""Discover Instagram handles for performers using Gemini + Google Search grounding.

Runs after performer extraction. For each performer without a verified handle,
searches the web for their Instagram and stores the result with a confidence level.

Confidence levels:
  'auto'     — found by search, not yet manually verified
  'verified' — manually confirmed correct (set via manage_performers.py)
  'unfound'  — search ran but found nothing useful (won't retry)

Only 'verified' handles are included in Instagram captions to avoid tagging
the wrong person.
"""

from __future__ import annotations

import json
import os
import re
import time

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-2.0-flash"   # grounding works best with Flash; 2.5-flash may vary

_SEARCH_PROMPT = """\
I need to find the Instagram account for a performer named {name} who does \
improv and/or sketch comedy in New York City.

Search for their Instagram handle. Return ONLY a JSON object in this exact format:
{{"ig_handle": "handle_without_the_at_sign_or_null", "confidence": "high|medium|low", "notes": "one sentence explanation"}}

- Use "high" confidence only if you find a clear, verified match (e.g. a link to \
their Instagram bio page, or their official website lists the handle).
- Use "medium" if the evidence is good but not 100% certain.
- Use "low" if it's a guess or the name is common and you're not sure it's the right person.
- Set ig_handle to null if you can't find anything credible.

Performer name: {name}
NYC comedy context: they perform at venues like UCB, Magnet Theater, The PIT, \
Brooklyn Comedy Collective, Second City, or similar.
"""


def enrich_performers(limit: int = 20) -> int:
    """Look up IG handles for performers that don't have one yet.

    Only processes performers with no ig_handle and no ig_confidence set
    (i.e. never been tried). Returns count of handles discovered.
    """
    from src.store import performers as perf_store
    from src.store.db import _conn, init_db

    init_db()
    _ensure_confidence_column()

    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name FROM performers
            WHERE (ig_handle IS NULL OR ig_handle = '')
              AND (ig_confidence IS NULL OR ig_confidence = '')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    if not rows:
        print("  No performers need handle enrichment.")
        return 0

    print(f"\n🔍 Searching for Instagram handles for {len(rows)} performer(s)...")
    found = 0

    for row in rows:
        name = row["name"]
        pid  = row["id"]
        result = _search_ig_handle(name)

        with _conn() as conn:
            if result["ig_handle"]:
                conn.execute(
                    "UPDATE performers SET ig_handle = ?, ig_confidence = ?, updated_at = datetime('now') WHERE id = ?",
                    (result["ig_handle"], "auto", pid),
                )
                print(f"  ✓ {name} → @{result['ig_handle']} ({result['confidence']}) — {result['notes']}")
                found += 1
            else:
                conn.execute(
                    "UPDATE performers SET ig_confidence = 'unfound', updated_at = datetime('now') WHERE id = ?",
                    (pid,),
                )
                print(f"  – {name} → not found ({result['notes']})")

        time.sleep(2)  # be gentle with the search API

    print(f"  ✓ {found} handle(s) discovered (confidence='auto' — verify before they appear in captions)")
    return found


def _search_ig_handle(name: str) -> dict:
    """Use Gemini with Google Search grounding to find a performer's IG handle."""
    prompt = _SEARCH_PROMPT.format(name=name)
    try:
        response = _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = (response.text or "").strip()

        # Extract JSON from the response (search-grounded responses include extra prose)
        json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return {
                "ig_handle": data.get("ig_handle") or None,
                "confidence": data.get("confidence", "low"),
                "notes": data.get("notes", ""),
            }
    except Exception as e:
        pass
    return {"ig_handle": None, "confidence": "low", "notes": "search failed"}


def _ensure_confidence_column():
    """Add ig_confidence column to performers if it doesn't exist yet."""
    from src.store.db import _conn
    with _conn() as conn:
        try:
            conn.execute("ALTER TABLE performers ADD COLUMN ig_confidence TEXT")
        except Exception:
            pass  # already exists
