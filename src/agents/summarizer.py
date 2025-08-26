import os
from datetime import datetime
from typing import List
import google.generativeai as genai
from dotenv import load_dotenv
from src.models import Event

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-1.5-flash")


def format_events_for_prompt(events: List[Event]) -> str:
    lines = []
    for e in events:
        if not e.start_time:
            continue
        date_str = e.start_time.strftime("%b %d, %I:%M %p")
        line = f"- \"{e.title}\", {date_str}, {e.venue}"
        lines.append(line)
    return "\n".join(lines)


def build_prompt(event_block: str) -> str:
    return f"""
You are an NYC improv newsletter editor with a witty, upbeat tone.

Summarize the following upcoming events at The PIT. Your goal is to make them sound fun, interesting, and worth attending.
Use casual, energetic language. Mention any standout titles, interesting combinations, or unique venues or times.

Here are the events:
{event_block}

Write a short, friendly digest paragraph. Sign off with something like \"See you there!\"
"""


def summarize_events(events: List[Event]) -> str:
    if not events:
        return "No upcoming events to summarize."

    event_block = format_events_for_prompt(events)
    prompt = build_prompt(event_block)

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "[Error generating summary]"


# For quick testing
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
    print(summarize_events(dummy_events))
