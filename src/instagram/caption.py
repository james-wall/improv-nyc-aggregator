"""Build the Instagram caption for the weekly carousel post.

Voice: warm, knowledgeable, like a friend who's obsessed with the NYC
improv/sketch scene and wants everyone to know about it. Not a listings
bot. Not snarky. Just genuinely enthusiastic and specific.

Structure:
  Line 1   — date range + emoji hook
  Line 2-3 — 1-2 sentences highlighting the week's standouts
  Line 4   — neighborhood roundup (📍)
  Line 5   — venue tags
  Line 6   — emoji key (only symbols used this week)
  Line 7   — hashtags

Emoji key (consistent, readers learn it over time):
  ⭐  top pick    🆓  free show
"""

from __future__ import annotations

from src.venues import ig_handle as venue_ig_handle

HASHTAGS = (
    "#NYCImprov #SketchComedy #NYCComedy #ImprovComedy #NYC #Comedy "
    "#NewYorkCity #Improv #LiveComedy #NYCTheater #ImproveYourFriday"
)

SIGNUP_CTA = "Free weekly newsletter → link in bio 🔗"


def build_caption(curated: dict, date_range: str) -> str:
    days  = curated.get("days") or []
    shows = [s for d in days for s in (d.get("shows") or [])]

    # ── Venue tags ─────────────────────────────────────────────────────────
    seen_venues: set[str] = set()
    venue_tags: list[str] = []
    for s in shows:
        v = s.get("venue", "")
        h = venue_ig_handle(v)
        if h and h not in seen_venues:
            seen_venues.add(h)
            venue_tags.append(f"@{h}")

    # ── Neighborhood list ──────────────────────────────────────────────────
    from src.venues import lookup as venue_lookup
    seen_hoods: set[str] = set()
    neighborhoods: list[str] = []
    for s in shows:
        nb, _ = venue_lookup(s.get("venue", ""))
        if nb and nb != "NYC" and nb not in seen_hoods:
            seen_hoods.add(nb)
            neighborhoods.append(nb)

    # ── Highlight sentence ─────────────────────────────────────────────────
    highlight = _build_highlight(days)

    # ── Emoji key — only show symbols actually used this week ──────────────
    has_starred = any(s.get("starred") for s in shows)
    has_free    = any("free" in (s.get("price") or s.get("title") or "").lower()
                      for s in shows)
    key_parts: list[str] = []
    if has_starred: key_parts.append("⭐ = top pick")
    if has_free:    key_parts.append("🆓 = free")
    emoji_key = "  ·  ".join(key_parts)

    # ── Performer tags ─────────────────────────────────────────────────────
    performer_tags = _performer_tags_for_curated(curated)

    # ── Assemble ───────────────────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"This week in NYC improv & sketch  ({date_range}) 🎭")
    lines.append("")

    if highlight:
        lines.append(highlight)
        lines.append("")

    lines.append(SIGNUP_CTA)
    lines.append("")

    if neighborhoods:
        lines.append("📍 " + "  ·  ".join(neighborhoods))

    if venue_tags:
        lines.append("  ".join(venue_tags))

    if performer_tags:
        lines.append("  ".join(f"@{h}" for h in performer_tags))

    lines.append("")

    if emoji_key:
        lines.append(emoji_key)
        lines.append("")

    lines.append(HASHTAGS)

    return "\n".join(lines)


def _build_highlight(days: list[dict]) -> str:
    """Build a 1-2 sentence highlight of the week's standout shows.

    Pulls the top 2-3 starred shows and assembles a readable sentence.
    No LLM call needed — deterministic from the curated data.
    """
    starred: list[dict] = []
    for day in days:
        short_day = (day.get("label") or "").split(",")[0]
        for show in (day.get("shows") or []):
            if show.get("starred"):
                starred.append({**show, "_day": short_day})

    if not starred:
        return ""

    # Take up to 3 highlights
    picks = starred[:3]

    parts: list[str] = []
    for p in picks:
        title  = p.get("title", "")
        venue  = p.get("venue", "")
        day    = p.get("_day", "")
        is_free = "free" in (p.get("price") or title or "").lower()
        free_note = " (free)" if is_free else ""
        parts.append(f"{title} at {venue} {day}{free_note}")

    if len(parts) == 1:
        return f"This week: {parts[0]}."
    elif len(parts) == 2:
        return f"Highlights: {parts[0]}, and {parts[1]}."
    else:
        return f"Highlights: {parts[0]}, {parts[1]}, and {parts[2]}."


def _performer_tags_for_curated(curated: dict) -> list[str]:
    """Return verified IG handles for performers in featured shows."""
    try:
        from src.store import performers as perf_store
        urls = [
            show.get("url", "")
            for day in (curated.get("days") or [])
            for show in (day.get("shows") or [])
            if show.get("url")
        ]
        handles: list[str] = []
        seen: set[str] = set()
        for url in urls:
            for p in perf_store.get_performers_for_show_url(url):
                if p.get("ig_confidence") != "verified":
                    continue
                h = p.get("ig_handle")
                if h and h not in seen:
                    seen.add(h)
                    handles.append(h)
        return handles
    except Exception:
        return []
