from __future__ import annotations

import random
import re
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
from src.models import Event
from src.store import db as store


class UcbScraper:
    """Scrape events from UCB Comedy (New York) via the WordPress/Tickera REST API.

    UCB runs on WordPress with the Tickera ticketing plugin, protected by
    Cloudflare.  We use ``cloudscraper`` to bypass the JS challenge and hit
    the ``/wp-json/wp/v2/tc_events`` endpoint for event listings.  Exact
    show times are extracted from individual event pages since the API only
    exposes the WordPress publish date, not the real event datetime.
    """

    API_URL = "https://ucbcomedy.com/wp-json/wp/v2/tc_events"
    BASE_URL = "https://ucbcomedy.com"
    NYC_CATEGORY_ID = 66  # "NYC" event category

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

    BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }

    @classmethod
    def _random_headers(cls) -> dict:
        return {**cls.BASE_HEADERS, "User-Agent": random.choice(cls.USER_AGENTS)}

    def __init__(self):
        store.init_db()
        self.scraper = cloudscraper.create_scraper()

    def _make_request(self, url: str, headers: dict = None, max_retries: int = 3, accept_json: bool = False):
        """Make a GET request with retry logic and exponential backoff."""
        if accept_json:
            request_headers = {"Accept": "application/json", "User-Agent": random.choice(self.USER_AGENTS)}
        else:
            request_headers = self._random_headers()
        if headers:
            request_headers.update(headers)

        print("making request for: " + str(url))

        for attempt in range(max_retries):
            try:
                response = self.scraper.get(url, timeout=60, headers=request_headers)
                response.raise_for_status()
                return response
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Request failed, retrying in {wait_time:.1f}s... ({e})")
                time.sleep(wait_time)

    def _parse_date_from_slug(self, slug: str) -> datetime | None:
        """Extract an event date from the slug (e.g. 'show-name-04-03-26').

        Returns a date or None if the slug doesn't end with MM-DD-YY.
        """
        match = re.search(r"(\d{2})-(\d{2})-(\d{2})$", slug)
        if match:
            month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            full_year = 2000 + year
            try:
                return datetime(full_year, month, day)
            except ValueError:
                pass
        return None

    def _fetch_event_time_and_venue(self, url: str) -> tuple[str, str]:
        """Fetch the individual event page to extract exact time and venue.

        Returns (time_str, venue_str) — e.g. ("10:30 pm", "NY - 14TH ST. Mainstage").
        """
        try:
            response = self._make_request(url)
            soup = BeautifulSoup(response.text, "html.parser")

            time_el = soup.select_one("span.tc_event_date_title_front")
            venue_el = soup.select_one("span.tc_event_location_title_front")

            time_str = ""
            if time_el:
                text = time_el.get_text(strip=True)
                # Format: "Friday, April 3, 2026 -- 10:30 pm"
                parts = text.split("--")
                if len(parts) >= 2:
                    time_str = parts[-1].strip()

            venue_str = venue_el.get_text(strip=True) if venue_el else ""
            return time_str, venue_str
        except Exception as e:
            print(f"  ⚠️ Error fetching event page {url}: {e}")
            return "", ""

    def _parse_description(self, html: str) -> str:
        """Extract plain-text description from the API's content.rendered HTML."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return UCB NYC events occurring within the next ``future_days`` days.

        Uses the WordPress REST API to list events, filters by slug date,
        then fetches individual pages for exact showtimes.
        """
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            # Fetch events from the API — grab a generous batch
            url = (
                f"{self.API_URL}"
                f"?event_category={self.NYC_CATEGORY_ID}"
                f"&per_page=100&order=desc"
            )
            print(f"🔗 Fetching: {url}")
            response = self._make_request(url, accept_json=True)
            items = response.json()

            for item in items:
                slug = item.get("slug", "")
                event_date = self._parse_date_from_slug(slug)

                if not event_date:
                    continue
                if event_date.date() < today or event_date.date() > end_date:
                    continue

                title = BeautifulSoup(
                    item.get("title", {}).get("rendered", "Untitled"), "html.parser"
                ).get_text(strip=True)
                event_url = item.get("link", "")
                description_html = item.get("content", {}).get("rendered", "")

                # Description is always available from the API response
                description = self._parse_description(description_html)

                # Try to get exact time and venue from the individual page
                cached = store.get_show(event_url)
                time_str = ""
                venue = "UCB NY"
                if cached and cached.get("venue") and cached["venue"] != "UCB NY":
                    venue = cached["venue"]
                    print(f"  ✓ Cached: {title}")
                else:
                    fetched_time, venue_raw = self._fetch_event_time_and_venue(event_url)
                    time_str = fetched_time
                    if venue_raw:
                        venue = f"UCB {venue_raw}"
                    time.sleep(random.uniform(1.5, 3.5))

                # Build full datetime with time if available
                full_dt = event_date
                if time_str:
                    try:
                        full_dt = datetime.strptime(
                            f"{event_date.strftime('%Y-%m-%d')} {time_str}",
                            "%Y-%m-%d %I:%M %p",
                        )
                    except ValueError:
                        # Try without space before am/pm
                        try:
                            full_dt = datetime.strptime(
                                f"{event_date.strftime('%Y-%m-%d')} {time_str}",
                                "%Y-%m-%d %I:%M%p",
                            )
                        except ValueError:
                            pass

                # Persist to knowledge store
                show_id = store.upsert_show(
                    url=event_url,
                    title=title,
                    venue=venue,
                    source="ucb",
                    description=description or None,
                )
                if full_dt:
                    store.upsert_occurrence(show_id, full_dt.isoformat())

                events.append(Event(
                    title=title,
                    venue=venue,
                    start_time=full_dt,
                    description=description,
                    url=event_url,
                    source="ucb",
                ))

        except Exception as e:
            print(f"Error fetching UCB events: {e}")

        return events
