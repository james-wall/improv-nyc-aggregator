"""Discover social handles and web profiles for performers using Gemini + Google Search.

One comprehensive search call per performer returns everything at once:
Instagram, Twitter/X, TikTok, YouTube, personal website, IMDB, and venue
roster pages (UCB, Magnet, etc.).

Confidence levels:
  'auto'     — found by search grounding, not yet manually reviewed
  'verified' — manually confirmed (set via manage_performers.py verify)
  'unfound'  — search ran but found nothing useful (won't be retried)

Only ig_confidence='verified' handles appear in Instagram captions.
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
_MODEL = "gemini-2.0-flash"

_SEARCH_PROMPT = """\
Search the web for the online presence of this performer: {name}

They do improv and/or sketch comedy in New York City, performing at venues \
like UCB, Magnet Theater, The PIT, Brooklyn Comedy Collective, Second City, \
Caveat, or The Rat.

Find as much as you can about their online profiles. Return ONLY a JSON object \
with this exact structure (use null for any field you can't find with reasonable confidence):

{{
  "ig_handle":      "instagram_username_without_@_or_null",
  "twitter_handle": "twitter_x_username_without_@_or_null",
  "tiktok_handle":  "tiktok_username_without_@_or_null",
  "youtube_handle": "youtube_channel_handle_without_@_or_null",
  "website":        "https://their-personal-site.com_or_null",
  "imdb_url":       "https://www.imdb.com/name/nm..._or_null",
  "venue_profiles": [
    {{"source": "UCB", "url": "https://ucbtheatre.com/performer/..."}},
    {{"source": "Magnet", "url": "https://magnettheater.com/..."}},
    {{"source": "press_or_other_site_name", "url": "https://..."}}
  ],
  "confidence": "high|medium|low",
  "notes": "one sentence about what you found or why you're uncertain"
}}

Rules:
- Only return a handle/URL if you have good evidence it's the right person \
  (not just anyone with the same name).
- For IMDB, only include if they have film/TV credits (not just stage work).
- venue_profiles can include UCB roster, Magnet bios, press features, \
  personal linktrees, or any other reputable pages about them as a performer.
- Leave venue_profiles as [] if you find nothing.
- If this is a very common name and you can't distinguish the right person, \
  set confidence to "low" and explain in notes.
"""


def enrich_performers(limit: int = 20) -> int:
    """Look up profiles for performers that haven't been enriched yet.

    Processes performers with no ig_handle and no ig_confidence (never tried).
    Returns the count of performers where at least one profile was found.
    """
    from src.store import performers as perf_store
    from src.store.db import _conn, init_db

    init_db()
    _ensure_columns()

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
        return 0

    print(f"\n🔍 Enriching profiles for {len(rows)} performer(s)...")
    enriched = 0

    for row in rows:
        name, pid = row["name"], row["id"]
        data = _search_profiles(name)
        _apply_enrichment(pid, name, data, perf_store)
        if data.get("ig_handle") or data.get("website") or data.get("imdb_url"):
            enriched += 1
        time.sleep(2)

    print(f"  ✓ {enriched} performer(s) enriched (confidence='auto' — review with 'manage_performers.py pending')")
    return enriched


def _search_profiles(name: str) -> dict:
    """Single Gemini+Search call that returns a full profile dict."""
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
        # Search-grounded responses may include prose; extract the JSON block
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        print(f"    ⚠️  Search failed for {name}: {e}")
    return {"confidence": "low", "notes": "search failed", "venue_profiles": []}


def _apply_enrichment(pid: int, name: str, data: dict, perf_store):
    """Write search results to the DB."""
    from src.store.db import _conn

    ig = _clean_handle(data.get("ig_handle"))
    twitter = _clean_handle(data.get("twitter_handle"))
    tiktok = _clean_handle(data.get("tiktok_handle"))
    youtube = _clean_handle(data.get("youtube_handle"))
    website = _clean_url(data.get("website"))
    imdb = _clean_url(data.get("imdb_url"))
    notes = data.get("notes", "")
    confidence = data.get("confidence", "low")

    # Only store if we found anything meaningful
    found_something = any([ig, twitter, tiktok, youtube, website, imdb,
                           data.get("venue_profiles")])

    new_confidence = "auto" if found_something else "unfound"

    perf_store.upsert_performer(
        name=name,
        ig_handle=ig or None,
        ig_confidence=new_confidence,
        twitter_handle=twitter or None,
        tiktok_handle=tiktok or None,
        youtube_handle=youtube or None,
        imdb_url=imdb or None,
        website=website or None,
    )

    for vp in (data.get("venue_profiles") or []):
        src = (vp.get("source") or "").strip()
        url = _clean_url(vp.get("url"))
        if src and url:
            perf_store.upsert_performer_link(pid, src, url, confidence="auto")

    # Summary log line
    parts = []
    if ig:        parts.append(f"IG:@{ig}")
    if twitter:   parts.append(f"TW:@{twitter}")
    if tiktok:    parts.append(f"TT:@{tiktok}")
    if youtube:   parts.append(f"YT:@{youtube}")
    if website:   parts.append(f"web:{website[:40]}")
    if imdb:      parts.append("imdb:✓")
    vp_count = len([v for v in (data.get("venue_profiles") or []) if v.get("url")])
    if vp_count:  parts.append(f"{vp_count} venue profile(s)")

    if parts:
        print(f"  ✓ {name} [{confidence}] — {', '.join(parts)}")
        if notes:
            print(f"      {notes}")
    else:
        print(f"  – {name} — nothing found ({notes})")


def _clean_handle(val) -> str:
    """Strip @ and whitespace from a handle string."""
    if not val or not isinstance(val, str):
        return ""
    return val.strip().lstrip("@").strip()


def _clean_url(val) -> str:
    """Return a URL string or empty string."""
    if not val or not isinstance(val, str):
        return ""
    val = val.strip()
    return val if val.startswith("http") else ""


def _ensure_columns():
    """Add new columns to existing DBs that predate this schema version."""
    from src.store.db import _conn
    with _conn() as conn:
        for stmt in [
            "ALTER TABLE performers ADD COLUMN ig_confidence TEXT",
            "ALTER TABLE performers ADD COLUMN youtube_handle TEXT",
            "ALTER TABLE performers ADD COLUMN imdb_url TEXT",
        ]:
            try:
                conn.execute(stmt)
            except Exception:
                pass
