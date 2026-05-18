"""Build the Instagram caption for a weekly newsletter post.

Strategy: tag every venue that appears in the curated picks so they see the
notification and can reshare to their Stories. Also tag any performers we have
IG handles for in the knowledge store.
"""

from __future__ import annotations

from src.venues import ig_handle as venue_ig_handle

HASHTAGS = (
    "#NYCImprov #SketchComedy #NYCComedy #ImprovComedy #NYC #Comedy "
    "#NewYorkCity #Improv #StandUp #LiveComedy #NYCTheater"
)


def build_caption(curated: dict, date_range: str) -> str:
    """Return the full Instagram caption string.

    Pulls venue tags from shows in the curated dict, and performer tags from
    the performer DB if any performers are linked to the featured shows.
    """
    # Collect venue handles from curated shows (deduplicated, preserving order)
    seen: set[str] = set()
    venue_tags: list[str] = []
    for day in (curated.get("days") or []):
        for show in (day.get("shows") or []):
            venue = show.get("venue", "")
            handle = venue_ig_handle(venue)
            if handle and handle not in seen:
                seen.add(handle)
                venue_tags.append(f"@{handle}")

    # Collect performer tags for featured shows
    performer_tags = _performer_tags_for_curated(curated)

    # Assemble caption
    total_shows = sum(
        len(day.get("shows") or []) for day in (curated.get("days") or [])
    )
    days_count = len(curated.get("days") or [])

    venue_line = "  ".join(venue_tags) if venue_tags else ""

    lines: list[str] = []
    lines.append(f"This week in NYC improv & sketch ({date_range}) 🎭")
    lines.append("")
    lines.append(
        f"{total_shows} picks across {days_count} nights. "
        "Full descriptions + every show in the newsletter — link in bio to subscribe."
    )

    if venue_line:
        lines.append("")
        lines.append(venue_line)

    if performer_tags:
        lines.append("  ".join(f"@{h}" for h in performer_tags))

    lines.append("")
    lines.append(HASHTAGS)

    return "\n".join(lines)


def _performer_tags_for_curated(curated: dict) -> list[str]:
    """Return IG handles for performers linked to featured shows, if any."""
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
                h = p.get("ig_handle")
                if h and h not in seen:
                    seen.add(h)
                    handles.append(h)
        return handles
    except Exception:
        return []
