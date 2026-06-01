"""Build the Instagram caption for the weekly carousel post.

Voice: warm, specific, like a friend obsessed with the NYC improv/sketch scene.
Inspired by weekly-listing accounts (e.g. @thirstygallerina): lead with a clean,
scannable list of TOP PICKS, not a paragraph or a wall of @-tags.

Structure:
  This week in NYC improv & sketch 🎭
  <date range>

  ⭐ OUR PICKS
  ✨ <title> @<venue> — <day>
  ...

  Free weekly newsletter → link in bio 🔗
  📍 <neighborhoods>

  <hashtags>

When include_tags is False (test posts), venues are named but NOT @-tagged, so we
don't notify the theaters before we're ready to.
"""

from __future__ import annotations

from src.venues import ig_handle as venue_ig_handle
from src.venues import lookup as venue_lookup

HASHTAGS = (
    "#NYCImprov #SketchComedy #NYCComedy #ImprovComedy #NYC #Comedy "
    "#NewYorkCity #Improv #LiveComedy #NYCTheater #ImproveYourFriday"
)

SIGNUP_CTA = "Free weekly newsletter → link in bio 🔗"
MAX_PICKS = 4


def build_caption(curated: dict, date_range: str, include_tags: bool = True) -> str:
    days = curated.get("days") or []

    picks = _select_picks(days)
    neighborhoods = _neighborhoods(days)

    lines: list[str] = []
    lines.append("This week in NYC improv & sketch 🎭")
    lines.append(date_range)
    lines.append("")

    if picks:
        lines.append("⭐ OUR PICKS")
        for p in picks:
            title = (p.get("title") or "").strip()
            venue = (p.get("venue") or "").strip()
            day = p.get("_day", "")
            # Venue: @-tag on real posts; plain name on test posts (don't ping theaters)
            venue_str = ""
            if venue:
                handle = venue_ig_handle(venue) if include_tags else None
                venue_str = f" @{handle}" if handle else f" · {venue}"
            day_str = f" — {day}" if day else ""
            lines.append(f"✨ {title}{venue_str}{day_str}")
        lines.append("")

    lines.append(SIGNUP_CTA)
    if neighborhoods:
        lines.append("📍 " + "  ·  ".join(neighborhoods))
    lines.append("")
    lines.append(HASHTAGS)

    return "\n".join(lines)


def _select_picks(days: list[dict]) -> list[dict]:
    """Top picks = starred shows; fall back to the first few shows of the week."""
    starred: list[dict] = []
    spillover: list[dict] = []
    for day in days:
        short_day = (day.get("label") or "").split(",")[0].strip()
        for show in (day.get("shows") or []):
            tagged = {**show, "_day": short_day}
            (starred if show.get("starred") else spillover).append(tagged)
    picks = starred[:MAX_PICKS]
    if not picks:
        picks = spillover[:3]
    return picks


def _neighborhoods(days: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for day in days:
        for show in (day.get("shows") or []):
            nb, _ = venue_lookup(show.get("venue", ""))
            if nb and nb != "NYC" and nb not in seen:
                seen.add(nb)
                out.append(nb)
    return out
