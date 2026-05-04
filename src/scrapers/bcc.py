"""Brooklyn Comedy Collective scraper.

Originally this scraper used Squarespace's ``?format=json`` endpoint, but
that returned ``startDate`` as an epoch-ms value that didn't round-trip
through ``datetime.fromtimestamp`` cleanly across timezones (the newsletter
ran in UTC on GitHub Actions and shifted every show by +4 hours).

We now scrape the index page for show URLs and parse the JSON-LD blob on
each per-show page. JSON-LD includes a tz-aware ISO timestamp like
``2026-04-07T19:00:00-0400`` which we can trust.
"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from src.models import Event
from src.store import db as store
from src.utils.formatting import detect_show_format


class BccScraper:
    BASE_URL = "https://www.brooklyncc.com"
    INDEX_URL = "https://www.brooklyncc.com/show-schedule"

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]

    BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self):
        store.init_db()
        self.session = requests.Session()
        self.session.headers.update(self._random_headers())

    @classmethod
    def _random_headers(cls) -> dict:
        return {**cls.BASE_HEADERS, "User-Agent": random.choice(cls.USER_AGENTS)}

    def _make_request(self, url: str, max_retries: int = 5):
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=60, headers=self._random_headers())
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"  Retry in {wait_time:.1f}s: {e}")
                time.sleep(wait_time)

    def _collect_show_urls(self) -> list[str]:
        """Pull all per-show URLs from the schedule index page."""
        print(f"🔗 Fetching BCC index: {self.INDEX_URL}")
        response = self._make_request(self.INDEX_URL)
        soup = BeautifulSoup(response.text, "html.parser")

        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Per-show pages: /show-schedule/<slug>  (not the index itself)
            if href.startswith("/show-schedule/") and href != "/show-schedule":
                full = self.BASE_URL + href.split("?")[0]
                if full not in seen:
                    seen.add(full)
                    urls.append(full)
        print(f"  Found {len(urls)} show URLs on index")
        return urls

    def _parse_show_page(self, url: str) -> dict | None:
        """Fetch one show page and extract data from its JSON-LD blob."""
        try:
            response = self._make_request(url)
        except Exception as e:
            print(f"  ⚠️  Failed to fetch {url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the JSON-LD Event blob
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "{}")
            except (json.JSONDecodeError, TypeError):
                continue

            # Sometimes JSON-LD is a list
            candidates = data if isinstance(data, list) else [data]
            for entry in candidates:
                if not isinstance(entry, dict):
                    continue
                if entry.get("@type") != "Event":
                    continue

                start_iso = entry.get("startDate")
                if not start_iso:
                    continue

                # Parse "2026-04-07T19:00:00-0400" — note the lack of colon in offset.
                start_dt = self._parse_iso(start_iso)
                if not start_dt:
                    continue

                title = (entry.get("name") or "").strip() or "Untitled"
                description = (entry.get("description") or "").strip()
                if not description:
                    # Fall back to a meta description on the page
                    meta = soup.find("meta", attrs={"name": "description"})
                    if meta and meta.get("content"):
                        description = meta["content"].strip()

                # Try to derive a stage / venue category from the page
                venue = self._extract_venue(soup, entry)

                return {
                    "title": title,
                    "start_dt": start_dt,
                    "description": description,
                    "venue": venue,
                }
        return None

    @staticmethod
    def _parse_iso(value: str) -> datetime | None:
        """Parse JSON-LD startDate. Handles ``-0400`` and ``-04:00`` offsets.

        Returns a naive datetime in the venue's local time (offset stripped),
        which matches how the rest of the pipeline treats datetimes.
        """
        s = value.strip()
        # Insert colon in offset if needed: -0400 -> -04:00
        m = re.match(r"^(.*[T ]\d{2}:\d{2}:\d{2})([+-])(\d{2})(\d{2})$", s)
        if m:
            s = f"{m.group(1)}{m.group(2)}{m.group(3)}:{m.group(4)}"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        # Strip tz to keep parity with the rest of the pipeline (naive local).
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt

    @staticmethod
    def _extract_venue(soup: BeautifulSoup, entry: dict) -> str:
        """Try to find which BCC stage hosts the show."""
        # JSON-LD location.name is often present
        loc = entry.get("location") or {}
        if isinstance(loc, dict):
            name = loc.get("name")
            if name:
                if name.upper().startswith("BCC"):
                    return name
                return f"BCC {name}"

        # Fall back to category tags rendered on the page
        tag = soup.find("a", class_=re.compile("eventlist-cat"))
        if tag:
            text = tag.get_text(strip=True)
            if text:
                return text if text.upper().startswith("BCC") else f"BCC {text}"

        return "Brooklyn Comedy Collective"

    def fetch(self, future_days: int = 7) -> list[Event]:
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            show_urls = self._collect_show_urls()
        except Exception as e:
            print(f"Error fetching BCC index: {e}")
            return events

        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 5
        for url in show_urls:
            # Reuse cached metadata if we already have a description, but we
            # always re-fetch the page so occurrence times stay accurate.
            data = self._parse_show_page(url)
            if not data:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(
                        f"  🛑 {MAX_CONSECUTIVE_FAILURES} consecutive BCC fetch failures "
                        "— likely network issue or rate limit. Skipping the rest of this run."
                    )
                    break
                continue
            consecutive_failures = 0

            start_dt = data["start_dt"]
            if start_dt.date() < today or start_dt.date() > end_date:
                continue

            title = data["title"]
            description = data["description"]
            venue = data["venue"]

            show_fmt = detect_show_format(title)
            class_show = show_fmt == "class_show"
            show_id = store.upsert_show(
                url=url,
                title=title,
                venue=venue,
                source="bcc",
                description=description or None,
                is_class_show=class_show,
                show_format=show_fmt,
            )
            store.upsert_occurrence(show_id, start_dt.isoformat())

            events.append(Event(
                title=title,
                venue=venue,
                start_time=start_dt,
                description=description,
                url=url,
                source="bcc",
                is_class_show=class_show,
                show_format=show_fmt,
            ))

            # Be polite to the host
            time.sleep(random.uniform(0.2, 0.5))

        return events
