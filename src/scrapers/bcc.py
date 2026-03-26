import random
import requests
from datetime import datetime, timedelta
import time
from src.models import Event
from src.store import db as store


class BccScraper:
    """Scrape events from Brooklyn Comedy Collective via Squarespace JSON API.

    BCC runs on Squarespace, which exposes a ``?format=json`` endpoint
    returning structured event data.  No HTML parsing needed.
    """

    BASE_URL = "https://www.brooklyncc.com/show-schedule"

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
        self.session = requests.Session()
        self.session.headers.update(self._random_headers())

    def _make_request(self, url: str, headers: dict = None, max_retries: int = 3):
        """Make a GET request with retry logic and exponential backoff."""
        request_headers = self._random_headers()
        if headers:
            request_headers.update(headers)

        print("making request for: " + str(url))

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=60, headers=request_headers)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise e
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Request failed, retrying in {wait_time:.1f}s... ({e})")
                time.sleep(wait_time)

    def _extract_description(self, item: dict) -> str:
        """Extract a plain-text description from the Squarespace event item."""
        # 'excerpt' has an HTML snippet; 'body' has the full HTML content
        from bs4 import BeautifulSoup

        for field in ("excerpt", "body"):
            html = item.get(field, "")
            if html:
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                if text:
                    return text
        return ""

    def _venue_from_categories(self, item: dict) -> str:
        """Derive the specific venue/stage from the event's categories."""
        cats = item.get("categories", [])
        if cats:
            stage = cats[0]
            # Avoid "BCC BCC Pig Pen" duplication
            if stage.upper().startswith("BCC"):
                return stage
            return f"BCC {stage}"
        return "Brooklyn Comedy Collective"

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return events occurring within the next ``future_days`` days.

        Descriptions are cached in the local knowledge store.
        """
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            url = f"{self.BASE_URL}?format=json"
            print(f"🔗 Fetching: {url}")
            response = self._make_request(url)
            data = response.json()

            upcoming = data.get("upcoming", []) + data.get("past", [])

            for item in upcoming:
                # Parse start time from epoch milliseconds
                start_ms = item.get("startDate")
                if not start_ms:
                    continue
                start_dt = datetime.fromtimestamp(start_ms / 1000)

                # Filter to date range
                if start_dt.date() < today or start_dt.date() > end_date:
                    continue

                title = item.get("title", "Untitled")
                full_url = "https://www.brooklyncc.com" + item.get("fullUrl", "")
                venue = self._venue_from_categories(item)

                # Use cached description if available
                cached = store.get_show(full_url)
                if cached and cached["description"]:
                    description = cached["description"]
                    print(f"  ✓ Cached: {title}")
                else:
                    description = self._extract_description(item)

                # Persist to knowledge store
                show_id = store.upsert_show(
                    url=full_url,
                    title=title,
                    venue=venue,
                    source="bcc",
                    description=description or None,
                )
                store.upsert_occurrence(show_id, start_dt.isoformat())

                events.append(Event(
                    title=title,
                    venue=venue,
                    start_time=start_dt,
                    description=description,
                    url=full_url,
                    source="bcc",
                ))

        except Exception as e:
            print(f"Error fetching BCC events: {e}")

        return events
