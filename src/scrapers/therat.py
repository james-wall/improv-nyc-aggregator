from __future__ import annotations

import json
import random
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import xml.etree.ElementTree as ET
from src.models import Event
from src.store import db as store
from src.utils.formatting import detect_show_format


class TheRatScraper:
    """Scrape events from The Rat NYC via sitemap + JSON-LD structured data.

    The Rat runs on Wix and renders event listings client-side.  We use
    the sitemap to discover event URLs, filter for upcoming dates by slug,
    then fetch individual pages to extract JSON-LD (schema.org Event) data.
    Results are cached in the knowledge store to avoid redundant fetches.
    """

    SITEMAP_URL = "https://www.theratnyc.com/event-pages-sitemap.xml"
    BASE_URL = "https://www.theratnyc.com"
    VENUE_NAME = "The Rat"

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

    def _parse_slug_date(self, url: str) -> datetime | None:
        """Try to extract a date from the event URL slug.

        Supports formats like:
        - ...-2026-05-08-19-00  (YYYY-MM-DD-HH-MM)
        - ...-04-14-21-50       (MM-DD-HH-MM with context)
        - ...-02-11-2026        (MM-DD-YYYY)
        """
        # YYYY-MM-DD pattern (most reliable)
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', url)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        # MM-DD-YYYY pattern
        match = re.search(r'(\d{2})-(\d{2})-(\d{4})', url)
        if match:
            try:
                return datetime(int(match.group(3)), int(match.group(1)), int(match.group(2)))
            except ValueError:
                pass

        return None

    def _fetch_sitemap_urls(self) -> list[str]:
        """Fetch and parse the sitemap for event page URLs."""
        response = self._make_request(self.SITEMAP_URL)
        root = ET.fromstring(response.text)
        # Handle XML namespace
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = []
        for url_el in root.findall("sm:url/sm:loc", ns):
            if url_el.text:
                urls.append(url_el.text)
        return urls

    def _fetch_event_jsonld(self, url: str) -> dict | None:
        """Fetch an event page and extract the JSON-LD structured data."""
        try:
            response = self._make_request(url)
            soup = BeautifulSoup(response.text, "html.parser")
            script = soup.find("script", type="application/ld+json")
            if script and script.string:
                data = json.loads(script.string)
                if data.get("@type") == "Event":
                    return data
        except Exception as e:
            print(f"  ⚠️ Error fetching {url}: {e}")
        return None

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return The Rat events occurring within the next ``future_days`` days.

        Fetches the sitemap, filters for potentially upcoming URLs,
        then fetches individual pages for JSON-LD event data.
        """
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            print(f"🔗 Fetching sitemap: {self.SITEMAP_URL}")
            all_urls = self._fetch_sitemap_urls()
            print(f"  Found {len(all_urls)} total event URLs in sitemap")

            # Filter to URLs that might be upcoming based on slug dates
            candidate_urls = []
            for url in all_urls:
                slug_date = self._parse_slug_date(url)
                if slug_date and slug_date.date() >= today and slug_date.date() <= end_date:
                    candidate_urls.append(url)
                elif not slug_date:
                    # No date in slug — we can't tell, so skip
                    # (most undated slugs are old/recurring)
                    continue

            print(f"  {len(candidate_urls)} URLs match date range")

            consecutive_failures = 0
            MAX_CONSECUTIVE_FAILURES = 5
            aborted = False
            for url in candidate_urls:
                # Check cache first
                cached = store.get_show(url)
                if cached and cached.get("description"):
                    title = cached["title"]
                    description = cached["description"]
                    print(f"  ✓ Cached: {title}")

                    # Reconstruct start_time from the DB occurrence
                    show_id = cached["id"]
                    from src.store.db import _conn
                    with _conn() as conn:
                        occ = conn.execute(
                            "SELECT start_time FROM occurrences WHERE show_id = ? ORDER BY start_time LIMIT 1",
                            (show_id,),
                        ).fetchone()
                    if occ:
                        try:
                            start_dt = datetime.fromisoformat(occ["start_time"])
                        except ValueError:
                            continue
                    else:
                        continue

                    show_fmt = detect_show_format(title)
                    class_show = show_fmt == "class_show"
                    events.append(Event(
                        title=title,
                        venue=cached.get("venue", self.VENUE_NAME),
                        start_time=start_dt,
                        description=description,
                        url=url,
                        source="therat",
                        time_known=True,
                        is_class_show=class_show,
                    show_format=show_fmt,
                    ))
                    continue

                if aborted:
                    continue

                # Fetch the page for JSON-LD
                data = self._fetch_event_jsonld(url)
                if not data:
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(
                            f"  🛑 {MAX_CONSECUTIVE_FAILURES} consecutive Rat fetch failures "
                            "— likely network issue or rate limit. Skipping the rest of this run."
                        )
                        aborted = True
                    continue
                consecutive_failures = 0

                title = data.get("name", "Untitled")
                # Clean emoji from title for consistency
                description = data.get("description", "")

                # Parse start time from ISO 8601
                start_str = data.get("startDate", "")
                start_dt = None
                has_time = False
                if start_str:
                    try:
                        start_dt = datetime.fromisoformat(start_str)
                        start_dt = start_dt.astimezone(ZoneInfo("America/New_York"))
                        start_dt = start_dt.replace(tzinfo=None)
                        has_time = True
                    except ValueError:
                        pass

                if not start_dt:
                    continue
                if start_dt.date() < today or start_dt.date() > end_date:
                    continue

                # Persist to knowledge store
                show_fmt = detect_show_format(title)
                class_show = show_fmt == "class_show"
                show_id = store.upsert_show(
                    url=url,
                    title=title,
                    venue=self.VENUE_NAME,
                    source="therat",
                    description=description or None,
                    is_class_show=class_show,
                    show_format=show_fmt,
                )
                store.upsert_occurrence(show_id, start_dt.isoformat())

                events.append(Event(
                    title=title,
                    venue=self.VENUE_NAME,
                    start_time=start_dt,
                    description=description,
                    url=url,
                    source="therat",
                    time_known=has_time,
                    is_class_show=class_show,
                    show_format=show_fmt,
                ))

                time.sleep(random.uniform(1.0, 2.5))

        except Exception as e:
            print(f"Error fetching The Rat events: {e}")

        return events
