import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from google import genai

from src.models import Event

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

MODEL_NAME = "gemini-2.5-flash"

PROMPT_REGISTRY = {
    "default": "src/prompts/summarizer_prompt.txt",
    "humorous": "src/prompts/summarizer_humorous.txt",
    "editorial": "src/prompts/summarizer_editorial.txt",
    "newsletter": "src/prompts/newsletter_prompt.txt",
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