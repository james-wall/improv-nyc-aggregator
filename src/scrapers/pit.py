import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import time
from src.models import Event
from src.store import db as store
from src.utils.formatting import is_class_show

class PitScraper:
    BASE_URL = "https://thepit-nyc.com/calendar/"

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
        """Make a GET request with retry logic and exponential backoff.
        Rotates User-Agent on each call to reduce fingerprinting."""
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

    def _get_month_params_for_range(self, future_days: int) -> list[str]:
        """Return a list of URL suffixes needed to cover today through
        today+future_days.  Includes the base URL for the current month and
        additional ?month=Mon-Y entries for subsequent months as necessary."""
        start = datetime.now().date()
        end = start + timedelta(days=future_days)
        params = []
        current = datetime(start.year, start.month, 1).date()
        while current <= end:
            if current.month == start.month and current.year == start.year:
                params.append("")
            else:
                params.append(f"?month={current.strftime('%b-%Y')}")
            current = (datetime(current.year, current.month, 15) + relativedelta(months=1)).date()
        return params

    def fetch_event_description(self, url: str) -> str:
        try:
            headers = {"Referer": self.BASE_URL}
            response = self._make_request(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            desc_section = soup.select_one("div.event__description section.wysiwyg")
            if desc_section:
                return desc_section.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"  ⚠️ Error fetching description for {url}: {e}")
        return ""

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return events occurring within the next `future_days` days (from now).

        Descriptions are cached in the local knowledge store — if a show has
        been seen before its description page is not re-fetched, which reduces
        the number of HTTP requests and lowers the risk of IP blocking.
        """
        events = []
        month_params = self._get_month_params_for_range(future_days)

        for month_param in month_params:
            url = self.BASE_URL + month_param
            try:
                print(f"🔗 Fetching: {url}")
                response = self._make_request(url)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Restrict to current week container if present
                week_section = soup.select_one("div.week--current")
                if week_section:
                    day_blocks = week_section.select("div.date.day")
                else:
                    day_blocks = soup.select("div.date.day")

                # Drop any day blocks marked as past
                day_blocks = [
                    day for day in day_blocks
                    if "past" not in " ".join(day.get("class", []))
                ]

                for day in day_blocks:
                    month_span = day.select_one(".day__month")
                    day_span = day.select_one(".day__number")
                    if not month_span or not day_span:
                        continue
                    try:
                        date_str = f"{month_span.get_text(strip=True)} {day_span.get_text(strip=True)} {datetime.now().year}"
                        event_date = datetime.strptime(date_str, "%b %d %Y")
                    except Exception:
                        event_date = None

                    for item in day.select("ul.events > li.event"):
                        title_elem = item.select_one(".event__title")
                        link_elem = item.select_one("a")
                        time_elem = item.select_one(".action__time")
                        venue_elem = item.select_one(".venue__title")

                        title = title_elem.get_text(strip=True) if title_elem else "Untitled"
                        event_url = link_elem['href'] if link_elem and link_elem.has_attr('href') else ""
                        time_text = time_elem.get_text(strip=True).replace("\n", "") if time_elem else ""
                        venue = venue_elem.get_text(strip=True) if venue_elem else "The PIT"
                        if venue.lower() == "the fishbowl":
                            venue = "The PIT Fishbowl"

                        try:
                            full_dt = datetime.strptime(f"{event_date.strftime('%Y-%m-%d')} {time_text}", "%Y-%m-%d %I:%M%p") if event_date and time_text else event_date
                        except Exception:
                            full_dt = event_date

                        # Use cached description if available; only hit the
                        # network when we haven't seen this show before.
                        cached = store.get_show(event_url)
                        if cached and cached["description"]:
                            description = cached["description"]
                            print(f"  ✓ Cached: {title}")
                        else:
                            description = self.fetch_event_description(event_url)
                            time.sleep(random.uniform(1.5, 3.5))

                        # Persist to knowledge store
                        class_show = is_class_show(title)
                        show_id = store.upsert_show(
                            url=event_url,
                            title=title,
                            venue=venue,
                            source="pit",
                            description=description or None,
                            is_class_show=class_show,
                        )
                        if full_dt:
                            store.upsert_occurrence(show_id, full_dt.isoformat())

                        events.append(Event(
                            title=title,
                            venue=venue,
                            start_time=full_dt,
                            description=description,
                            url=event_url,
                            source="pit",
                            is_class_show=class_show,
                        ))

            except Exception as e:
                print(f"Error fetching PIT events for {month_param or 'current month'}: {e}")
                continue

            if month_param:
                time.sleep(random.uniform(4, 8))

        return events
