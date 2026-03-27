from __future__ import annotations

import random
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
from src.models import Event
from src.store import db as store


class UcbScraper:
    """Scrape events from UCB Comedy (New York) via their shows listing page.

    The ``/shows/new-york/`` page is server-side rendered by WP Grid Builder
    and contains event cards with date, time, title, venue, URL, and excerpt
    — all in a single request.  We use ``cloudscraper`` to handle Cloudflare.
    """

    SHOWS_URL = "https://ucbcomedy.com/shows/new-york/"

    def __init__(self):
        store.init_db()
        self.scraper = cloudscraper.create_scraper()

    def _make_request(self, url: str, max_retries: int = 3):
        """Make a GET request with retry logic and exponential backoff.

        Lets cloudscraper manage its own headers — overriding them with
        custom Sec-Fetch-* headers triggers Cloudflare's bot detection.
        """
        print("making request for: " + str(url))

        for attempt in range(max_retries):
            try:
                response = self.scraper.get(url, timeout=60)
                response.raise_for_status()
                return response
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Request failed, retrying in {wait_time:.1f}s... ({e})")
                time.sleep(wait_time)

    def _parse_card_datetime(self, date_text: str) -> tuple[datetime | None, bool]:
        """Parse a date string like 'Friday, March 27, 2026 @ 7:00 PM'.

        Returns (datetime, time_known).  If the '@' time portion is missing,
        time_known will be False and the time will be midnight.
        """
        if not date_text:
            return None, False

        if "@" in date_text:
            try:
                dt = datetime.strptime(date_text.strip(), "%A, %B %d, %Y @ %I:%M %p")
                return dt, True
            except ValueError:
                pass

        # Try without time
        try:
            dt = datetime.strptime(date_text.strip().split("@")[0].strip(), "%A, %B %d, %Y")
            return dt, False
        except ValueError:
            return None, False

    def _extract_ny_venue(self, card) -> str:
        """Extract the NY venue name from location spans, skipping 'Livestream'."""
        loc_el = card.select_one(".ucb-event-post-location")
        if not loc_el:
            return "UCB NY"
        terms = [s.get_text(strip=True) for s in loc_el.select(".wpgb-block-term")]
        for term in terms:
            if "NY" in term:
                return f"UCB {term}"
        return "UCB NY"

    def _is_ny_show(self, card) -> bool:
        """Check if a card is for a New York show (not LA-only or Livestream-only)."""
        loc_el = card.select_one(".ucb-event-post-location")
        if not loc_el:
            return False
        terms = [s.get_text(strip=True) for s in loc_el.select(".wpgb-block-term")]
        return any("NY" in t for t in terms)

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return UCB NYC events occurring within the next ``future_days`` days.

        Fetches the /shows/new-york/ page which contains all upcoming events
        with dates, times, venues, and descriptions in a single request.
        """
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            print(f"🔗 Fetching: {self.SHOWS_URL}")
            response = self._make_request(self.SHOWS_URL)
            soup = BeautifulSoup(response.text, "html.parser")

            cards = soup.select("article.wpgb-card")
            print(f"  Found {len(cards)} event cards")

            for card in cards:
                # Skip non-NY shows
                if not self._is_ny_show(card):
                    continue

                # Parse date and time
                date_el = card.select_one(".event-post-date")
                date_text = date_el.get_text(strip=True) if date_el else ""
                start_dt, has_time = self._parse_card_datetime(date_text)

                if not start_dt:
                    continue
                if start_dt.date() < today or start_dt.date() > end_date:
                    continue

                # Title and URL
                title_el = card.select_one(".ucb-event-post-title a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                event_url = title_el.get("href", "")

                # Venue
                venue = self._extract_ny_venue(card)

                # Description
                cached = store.get_show(event_url)
                if cached and cached.get("description"):
                    description = cached["description"]
                    print(f"  ✓ Cached: {title}")
                else:
                    excerpt_el = card.select_one(".ucb-event-post-excerpt")
                    description = excerpt_el.get_text(strip=True) if excerpt_el else ""

                # Persist to knowledge store
                show_id = store.upsert_show(
                    url=event_url,
                    title=title,
                    venue=venue,
                    source="ucb",
                    description=description or None,
                )
                if start_dt:
                    store.upsert_occurrence(show_id, start_dt.isoformat())

                events.append(Event(
                    title=title,
                    venue=venue,
                    start_time=start_dt,
                    description=description,
                    url=event_url,
                    source="ucb",
                    time_known=has_time,
                ))

        except Exception as e:
            print(f"Error fetching UCB events: {e}")

        return events
