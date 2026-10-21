import json
import os
import re
import time
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

from src.config import (
    CURATION_MAX_OUTPUT_TOKENS,
    CURATION_THINKING_BUDGET,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
)
from src.models import Event


class CuratedShow(BaseModel):
    time: str
    venue: str
    title: str
    url: str
    starred: bool
    details: str


class CuratedDay(BaseModel):
    date_iso: str
    label: str
    emoji: str
    shows: List[CuratedShow]


class CuratedNewsletter(BaseModel):
    days: List[CuratedDay]

load_dotenv()

# Option A: Gemini Developer API
# Expects GEMINI_API_KEY or GOOGLE_API_KEY in your environment.
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# If you later want Vertex AI instead, use:
# client = genai.Client(
#     vertexai=True,
#     project=os.getenv("GOOGLE_CLOUD_PROJECT"),
#     location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
# )

MODEL_NAME = GEMINI_MODEL

PROMPT_REGISTRY = {
    "default": "src/prompts/summarizer_prompt.txt",
    "humorous": "src/prompts/summarizer_humorous.txt",
    "editorial": "src/prompts/summarizer_editorial.txt",
    "newsletter": "src/prompts/newsletter_prompt.txt",
    "newsletter_json": "src/prompts/newsletter_json_prompt.txt",
}


def format_events_for_prompt(events: List[Event]) -> str:
    """Format events grouped by date, sorted chronologically within each day."""
    from collections import defaultdict
    from src.utils.formatting import normalize_title

    by_date = defaultdict(list)
    for e in events:
        if not e.start_time:
            continue
        date_key = e.start_time.strftime("%A, %B %d")
        by_date[date_key].append(e)

    # Sort dates chronologically
    sorted_dates = sorted(by_date.keys(), key=lambda d: by_date[d][0].start_time.date())

    sections = []
    for date_key in sorted_dates:
        day_events = sorted(by_date[date_key], key=lambda e: (not e.time_known, e.start_time))
        lines = [f"### {date_key}"]
        for e in day_events:
            title = normalize_title(e.title)
            venue_price = f'{e.venue} - {e.price}' if e.price else e.venue
            if e.time_known:
                line = f'- [{e.start_time.strftime("%I:%M %p")}] "{title}" ({venue_price})'
            else:
                line = f'- "{title}" ({venue_price}) — check venue for showtime'
            if e.description:
                line += f'\n  Description: {e.description.strip()}'
            if e.url:
                line += f'\n  Link: {e.url}'
            lines.append(line)
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def build_prompt(event_block: str, style: str = "default",
                 days: int = 7, date_range: str = "",
                 event_count: int = 0, venue_count: int = 0,
                 venue_list: str = "") -> str:
    prompt_path = PROMPT_REGISTRY.get(style, PROMPT_REGISTRY["default"])
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()
        result = template.replace("{event_block}", event_block)
        result = result.replace("{days}", str(days))
        result = result.replace("{date_range}", date_range)
        result = result.replace("{event_count}", str(event_count))
        result = result.replace("{venue_count}", str(venue_count))
        result = result.replace("{venue_list}", venue_list)
        return result
    except FileNotFoundError:
        print(f"❌ Prompt template not found: {prompt_path}. Using fallback prompt.")
        return f"Summarize the following events:\n{event_block}"


def summarize_events(events: List[Event], style: str = "default",
                     days: int = 7, date_range: str = "") -> str:
    if not events:
        return "No upcoming events to summarize."

    event_block = format_events_for_prompt(events)
    venues = set(e.venue for e in events)
    venue_list = ", ".join(sorted(venues))
    prompt = build_prompt(
        event_block, style=style, days=days, date_range=date_range,
        event_count=len(events), venue_count=len(venues),
        venue_list=venue_list,
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        return response.text.strip() if response.text else "[No summary returned]"
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "[Error generating summary]"


# Retry policy for transient Gemini errors (429 quota/rate limit, 5xx overload).
# Waits are per model and bounded so a quota outage costs at most ~45s per model
# before we move on to the fallback model and then the deterministic listing.
_RETRYABLE_CODES = {429, 500, 503, 504}
_RETRY_WAITS = (15, 30)  # seconds between the 3 attempts on one model
_sleep = time.sleep  # patched in tests


def _error_code(err: Exception) -> int | None:
    code = getattr(err, "code", None)
    return code if isinstance(code, int) else None


def _parse_curated(response) -> dict | None:
    """Return the curated dict, or None if the response is truncated/unparseable."""
    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        return parsed_obj.model_dump()

    raw = (getattr(response, "text", None) or "").strip()
    # Strip code fences if the model wraps the JSON
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⚠️  Could not parse curated JSON ({e}). Raw output:\n{raw[:500]}")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        print(f"⚠️  Curated JSON has no 'days' list. Raw output:\n{raw[:500]}")
        return None
    return data


def _show_count(curated: dict) -> int:
    return sum(len(d.get("shows") or []) for d in curated.get("days") or [])


def _call_model(model: str, prompt: str) -> dict | None:
    """Up to 3 attempts on one model with bounded backoff on retryable errors."""
    for attempt in range(len(_RETRY_WAITS) + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": CuratedNewsletter,
                    "max_output_tokens": CURATION_MAX_OUTPUT_TOKENS,
                    "thinking_config": {"thinking_budget": CURATION_THINKING_BUDGET},
                },
            )
        except Exception as e:
            code = _error_code(e)
            if code in _RETRYABLE_CODES and attempt < len(_RETRY_WAITS):
                wait = _RETRY_WAITS[attempt]
                print(f"⚠️  {model} failed (attempt {attempt + 1}, HTTP {code}): {e}. "
                      f"Retrying in {wait}s...")
                _sleep(wait)
                continue
            print(f"❌ {model} failed (attempt {attempt + 1}, HTTP {code}): {e}")
            return None
        # A truncated or malformed answer won't improve by asking the same
        # model again with the same prompt; let the caller try the next model.
        return _parse_curated(response)
    return None


def fallback_listing(events: List[Event]) -> dict:
    """Deterministic, uncurated listing of every dated event, by day then time/venue.

    Used when Gemini curation fails so the issue is never silently empty.
    """
    from collections import defaultdict
    from src.utils.formatting import normalize_title

    by_day = defaultdict(list)
    for e in events:
        if e.start_time:
            by_day[e.start_time.date()].append(e)

    days = []
    for day in sorted(by_day):
        shows = []
        for e in sorted(by_day[day], key=lambda e: (not e.time_known, e.start_time, e.venue, e.title)):
            shows.append({
                "time": e.start_time.strftime("%I:%M %p").lstrip("0") if e.time_known else "TBA",
                "venue": e.venue,
                "title": normalize_title(e.title),
                "url": e.url or "",
                "starred": False,
                "details": e.price or "",
            })
        days.append({
            "date_iso": day.isoformat(),
            "label": f"{day.strftime('%A, %B')} {day.day}",
            "emoji": "🎭",
            "shows": shows,
        })
    return {"days": days}


def curate_events_json(events: List[Event], days: int, date_range: str) -> dict:
    """Ask the LLM to curate events into a structured per-day JSON object.

    Returns a dict with key "days" — see newsletter_json_prompt.txt for schema.
    Tries GEMINI_MODEL then GEMINI_FALLBACK_MODEL (with backoff on 429/5xx).
    If both fail or return truncated/empty JSON, returns fallback_listing(events)
    with "fallback": True. Returns {"days": []} only when there is nothing to
    list, which generate_newsletter.py treats as fail-closed (no send/post).
    """
    if not events:
        return {"days": []}

    event_block = format_events_for_prompt(events)
    venues = sorted({e.venue for e in events})
    prompt = build_prompt(
        event_block, style="newsletter_json", days=days, date_range=date_range,
        event_count=len(events), venue_count=len(venues),
        venue_list=", ".join(venues),
    )

    for model in (GEMINI_MODEL, GEMINI_FALLBACK_MODEL):
        curated = _call_model(model, prompt)
        if curated is not None and _show_count(curated) > 0:
            if model != GEMINI_MODEL:
                print(f"ℹ️  Curated with fallback model {model}")
            return curated
        if curated is not None:
            print(f"⚠️  {model} returned 0 curated shows from {len(events)} events")

    listing = fallback_listing(events)
    if _show_count(listing) == 0:
        return {"days": []}
    print(f"⚠️  Gemini curation failed on all models; using deterministic fallback "
          f"listing of {_show_count(listing)} shows (uncurated).")
    listing["fallback"] = True
    return listing


if __name__ == "__main__":
    dummy_events = [
        Event(
            title="Awkward Family Dinner",
            venue="The PIT Loft",
            start_time=datetime(2025, 8, 29, 19, 0),
            description="A sketch comedy show about your worst Thanksgiving.",
            url="https://thepit-nyc.com/events/awkward-family-dinner/",
            source="pit"
        ),
        Event(
            title="Big Gay Jam",
            venue="The PIT Loft",
            start_time=datetime(2025, 8, 30, 21, 30),
            description="Open improv jam for LGBTQ+ performers and allies.",
            url="https://thepit-nyc.com/events/big-gay-jam/",
            source="pit"
        )
    ]

    print(summarize_events(dummy_events, style="default"))