from __future__ import annotations

import json
import random
import re
import requests
from datetime import datetime, timedelta
import time
from src.models import Event
from src.store import db as store
from src.utils.formatting import detect_show_format


class CaveatScraper:
    """Scrape events from Caveat NYC via Eventbrite's organizer page.

    Caveat uses Eventbrite for ticketing.  The organizer page embeds a
    ``window.__SERVER_DATA__`` JSON blob containing all upcoming events
    with dates, times, prices, and basic metadata.
    """

    ORGANIZER_URL = "https://www.eventbrite.com/o/caveat-13580085802"
    VENUE_NAME = "Caveat"

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]

    def __init__(self):
        store.init_db()
        self.session = requests.Session()

    def _make_request(self, url: str, max_retries: int = 5):
        """Make a GET request with retry logic and exponential backoff."""
        headers = {"User-Agent": random.choice(self.USER_AGENTS)}
        print("making request for: " + str(url))

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=60, headers=headers)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise e
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Request failed, retrying in {wait_time:.1f}s... ({e})")
                time.sleep(wait_time)

    def _parse_event_data(self, html: str) -> list[dict]:
        """Extract event list from the __NEXT_DATA__ blob in the page.

        Eventbrite migrated to Next.js — data moved from __SERVER_DATA__
        to the standard <script id="__NEXT_DATA__"> tag.
        """
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if not match:
            print("  ⚠️ Could not find __NEXT_DATA__ in page")
            return []

        try:
            data = json.loads(match.group(1))
            events = data.get("props", {}).get("pageProps", {}).get("upcomingEvents", [])
            return events
        except (json.JSONDecodeError, AttributeError, KeyError) as e:
            print(f"  ⚠️ Error parsing __NEXT_DATA__: {e}")
            return []

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return Caveat events occurring within the next ``future_days`` days."""
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            print(f"🔗 Fetching: {self.ORGANIZER_URL}")
            response = self._make_request(self.ORGANIZER_URL)
            items = self._parse_event_data(response.text)
            print(f"  Found {len(items)} upcoming Eventbrite events")

            for item in items:
                # Parse start time from split date/time fields
                date_str = item.get("start_date", "")
                time_str = item.get("start_time", "")
                if not date_str:
                    continue

                try:
                    iso_str = f"{date_str}T{time_str}" if time_str else date_str
                    start_dt = datetime.fromisoformat(iso_str)
                except ValueError:
                    continue

                if start_dt.date() < today or start_dt.date() > end_date:
                    continue

                # Extract fields
                title = item.get("name", "")
                if not title:
                    continue

                event_url = item.get("url", "")
                ticket_info = item.get("ticket_availability", {})
                is_free = ticket_info.get("is_free", False)
                min_price = ticket_info.get("minimum_ticket_price", {})
                price = f"${min_price.get('major_value', '')}" if min_price.get("major_value") else ""
                price_note = "Free" if is_free else price

                # Use cached description if available
                cached = store.get_show(event_url)
                if cached and cached.get("description"):
                    description = cached["description"]
                    print(f"  ✓ Cached: {title}")
                else:
                    description = item.get("summary", "")

                # Persist to knowledge store
                show_fmt = detect_show_format(title)
                class_show = show_fmt == "class_show"
                show_id = store.upsert_show(
                    url=event_url,
                    title=title,
                    venue=self.VENUE_NAME,
                    source="caveat",
                    description=description or None,
                    is_class_show=class_show,
                    show_format=show_fmt,
                    price=price_note or None,
                )
                store.upsert_occurrence(show_id, start_dt.isoformat())

                events.append(Event(
                    title=title,
                    venue=self.VENUE_NAME,
                    start_time=start_dt,
                    description=description,
                    url=event_url,
                    source="caveat",
                    is_class_show=class_show,
                    show_format=show_fmt,
                    price=price_note or None,
                ))

        except Exception as e:
            print(f"Error fetching Caveat events: {e}")

        return events
