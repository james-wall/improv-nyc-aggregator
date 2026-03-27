import random
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import time
from src.models import Event
from src.store import db as store
from src.utils.formatting import is_class_show


class MagnetScraper:
    """Scrape events from Magnet Theater's weekly calendar.

    Uses the week view (/calendar/week/) which renders a 7-day HTML table.
    Each <td> holds a day number and zero-or-more event blocks.  Show
    descriptions are fetched from individual show pages and cached in the
    knowledge store to avoid redundant requests.
    """

    BASE_URL = "https://magnettheater.com/calendar/week/"
    SHOW_BASE_URL = "https://magnettheater.com/show/"

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

    # ------------------------------------------------------------------
    # Week URL helpers
    # ------------------------------------------------------------------

    def _get_week_urls(self, future_days: int) -> list[str]:
        """Return week-view URLs needed to cover today through today+future_days.

        The Magnet week view accepts a ``?date=YYYY-MM-DD`` param.  Each page
        shows 7 days starting from that date's week.  We step forward in 7-day
        increments to cover the full range.
        """
        urls = [self.BASE_URL]  # current week (no param needed)
        if future_days > 7:
            start = datetime.now().date()
            current = start + timedelta(days=7)
            end = start + timedelta(days=future_days)
            while current <= end:
                urls.append(f"{self.BASE_URL}?date={current.isoformat()}")
                current += timedelta(days=7)
        return urls

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_month_year(self, soup: BeautifulSoup) -> tuple[int, int]:
        """Extract (month, year) from the calendar header, e.g. 'Mar 2026'."""
        month_el = soup.select_one("strong.month")
        if month_el:
            text = month_el.get_text(strip=True)
            try:
                dt = datetime.strptime(text, "%b %Y")
                return dt.month, dt.year
            except ValueError:
                pass
        # Fallback to current month
        now = datetime.now()
        return now.month, now.year

    def _resolve_day_dates(
        self, day_numbers: list[int], header_month: int, header_year: int
    ) -> list[datetime]:
        """Turn a list of day-of-month numbers into actual dates.

        The week view may span a month boundary.  When a day number is
        *smaller* than the first day in the list, it belongs to the next month.
        """
        dates = []
        month, year = header_month, header_year
        prev_day = 0
        for day_num in day_numbers:
            if day_num < prev_day:
                # Rolled into the next month
                if month == 12:
                    month, year = 1, year + 1
                else:
                    month += 1
            try:
                dates.append(datetime(year, month, day_num))
            except ValueError:
                dates.append(None)
            prev_day = day_num
        return dates

    def _parse_time_price(self, abr_text: str) -> tuple[str, str]:
        """Parse an <abr> string like '7:00pm - $8' into (time_str, price_str)."""
        parts = abr_text.split("-", 1)
        time_str = parts[0].strip() if parts else ""
        price_str = parts[1].strip() if len(parts) > 1 else ""
        return time_str, price_str

    # ------------------------------------------------------------------
    # Show detail page
    # ------------------------------------------------------------------

    def fetch_event_description(self, url: str) -> str:
        """Fetch the full description from an individual show page."""
        try:
            headers = {"Referer": self.BASE_URL}
            response = self._make_request(url, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")

            # Primary: schema.org description
            desc_el = soup.select_one('p[itemprop="description"]')
            if desc_el:
                return desc_el.get_text(separator="\n", strip=True)

            # Fallback: .show-info section
            info = soup.select_one("div.show-info")
            if info:
                return info.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"  ⚠️ Error fetching description for {url}: {e}")
        return ""

    # ------------------------------------------------------------------
    # Day-view enrichment (featured ensembles for today's shows)
    # ------------------------------------------------------------------

    def _fetch_today_ensembles(self) -> dict[str, str]:
        """Fetch the day view to grab featured ensemble names for today's shows.

        Returns a dict mapping show URL -> ensemble text (e.g. 'Neptune & Macbeth').
        """
        ensembles: dict[str, str] = {}
        try:
            url = "https://magnettheater.com/calendar/"
            response = self._make_request(url)
            soup = BeautifulSoup(response.text, "html.parser")
            for post in soup.select("[class*=sched]"):
                desc_div = post.select_one(".show-desc")
                if not desc_div:
                    continue
                link = desc_div.select_one(".show-title a")
                feat = desc_div.select_one(".show-feat")
                if link and feat:
                    ensembles[link["href"]] = feat.get_text(strip=True)
        except Exception as e:
            print(f"  ⚠️ Could not fetch day view for ensembles: {e}")
        return ensembles

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return events occurring within the next ``future_days`` days.

        Descriptions are cached in the local knowledge store -- if a show has
        been seen before its description page is not re-fetched.
        """
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)
        week_urls = self._get_week_urls(future_days)

        # Grab ensemble info from the richer day-view for today's shows
        today_ensembles = self._fetch_today_ensembles()

        for week_url in week_urls:
            try:
                print(f"🔗 Fetching: {week_url}")
                response = self._make_request(week_url)
                soup = BeautifulSoup(response.text, "html.parser")

                header_month, header_year = self._parse_month_year(soup)

                # Each <td> in the calendar table represents one day.
                # The first child <strong class="date"> holds the day number.
                cells = soup.select("td")
                day_numbers = []
                day_cells = []
                for cell in cells:
                    date_el = cell.select_one("strong.date")
                    if date_el:
                        try:
                            day_numbers.append(int(date_el.get_text(strip=True)))
                            day_cells.append(cell)
                        except ValueError:
                            continue

                day_dates = self._resolve_day_dates(
                    day_numbers, header_month, header_year
                )

                for cell, event_date in zip(day_cells, day_dates):
                    if event_date is None:
                        continue
                    if event_date.date() < today or event_date.date() > end_date:
                        continue

                    for event_div in cell.select("div.an-event"):
                        # Time and price from <abr class="time dtstart">
                        abr = event_div.select_one("abr.time")
                        time_str, price_str = "", ""
                        if abr:
                            time_str, price_str = self._parse_time_price(
                                abr.get_text(strip=True)
                            )

                        # Title and URL
                        title_el = event_div.select_one("p.summary strong")
                        link_el = event_div.select_one("a[href]")
                        title = title_el.get_text(strip=True) if title_el else "Untitled"
                        event_url = link_el["href"] if link_el else ""

                        # Skip placeholder / "No Shows" entries
                        if not event_url or event_url.rstrip("/").endswith("/show"):
                            continue

                        # Build full datetime
                        full_dt = event_date
                        if time_str:
                            try:
                                full_dt = datetime.strptime(
                                    f"{event_date.strftime('%Y-%m-%d')} {time_str}",
                                    "%Y-%m-%d %I:%M%p",
                                )
                            except ValueError:
                                pass

                        # Append ensemble info to title when available
                        ensemble_text = today_ensembles.get(event_url, "")
                        display_title = (
                            f"{title} ({ensemble_text})" if ensemble_text else title
                        )

                        # Use cached description if available
                        cached = store.get_show(event_url)
                        if cached and cached["description"]:
                            description = cached["description"]
                            print(f"  ✓ Cached: {display_title}")
                        else:
                            description = self.fetch_event_description(event_url)
                            time.sleep(random.uniform(1.5, 3.5))

                        # Persist to knowledge store
                        class_show = is_class_show(title)
                        show_id = store.upsert_show(
                            url=event_url,
                            title=title,
                            venue="Magnet Theater",
                            source="magnet",
                            description=description or None,
                            is_class_show=class_show,
                        )
                        if full_dt:
                            store.upsert_occurrence(show_id, full_dt.isoformat())

                        events.append(
                            Event(
                                title=display_title,
                                venue="Magnet Theater",
                                start_time=full_dt,
                                description=description,
                                url=event_url,
                                source="magnet",
                                is_class_show=class_show,
                            )
                        )

            except Exception as e:
                print(f"Error fetching Magnet events for {week_url}: {e}")
                continue

            if week_url != week_urls[0]:
                time.sleep(random.uniform(4, 8))

        return events
