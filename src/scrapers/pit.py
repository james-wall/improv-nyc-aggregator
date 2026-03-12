import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from src.models import Event

class PitScraper:
    BASE_URL = "https://thepit-nyc.com/calendar/"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
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
    
    def __init__(self, use_selenium: bool = False):
        """If use_selenium is True, spin up a headless Chrome driver. Otherwise
        fall back to a requests.Session with sensible headers. The VPN should
        normally be sufficient to avoid IP blocks, so selenium is optional."""
        self.use_selenium = use_selenium
        if use_selenium:
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in headless mode
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            try:
                self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            except Exception as e:
                # if Chrome binary isn't available, fallback to requests
                print(f"⚠️ Selenium init failed, falling back to requests: {e}")
                self.use_selenium = False
        if not use_selenium:
            # session headers for non-selenium requests
            self.session = requests.Session()
            self.session.headers.update(self.HEADERS)

    def _make_request(self, url: str, headers: dict = None, max_retries: int = 3):
        """Make a GET request with retry logic and exponential backoff."""
        request_headers = self.session.headers.copy()
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
                wait_time = 2 ** attempt  # exponential backoff
                print(f"Request failed, retrying in {wait_time} seconds... ({e})")
                time.sleep(wait_time)

    def _get_month_params(self) -> list[str]:
        # legacy helper; still returns current + two following months
        months = []
        for i in range(3):  # current + next 2 months
            month_date = datetime.now() + relativedelta(months=i)
            if i == 0:
                months.append("")  # current month = default view
            else:
                formatted = month_date.strftime("?month=%b-%Y")  # e.g., ?month=Sep-2025
                months.append(formatted)
        return months

    def _get_month_params_for_range(self, future_days: int) -> list[str]:
        """Return a list of URL suffixes needed to cover today through
        today+future_days.  Includes the base URL for the current month and
        additional ?month=Mon-Y entries for subsequent months as necessary."""
        start = datetime.now().date()
        end = start + timedelta(days=future_days)
        params = []
        # iterate month-by-month from start to end
        current = datetime(start.year, start.month, 1).date()
        while current <= end:
            if current.month == start.month and current.year == start.year:
                params.append("")
            else:
                params.append(f"?month={current.strftime('%b-%Y')}")
            # advance one month
            current = (datetime(current.year, current.month, 15) + relativedelta(months=1)).date()
        return params
    
    def fetch_event_description(self, url: str) -> str:
        try:
            if self.use_selenium and hasattr(self, 'driver'):
                self.driver.get(url)
                time.sleep(5)  # Wait for page to load
                html = self.driver.page_source
            else:
                headers = {"Referer": self.BASE_URL}
                response = self._make_request(url, headers=headers)
                html = response.text

            soup = BeautifulSoup(html, 'html.parser')
            desc_section = soup.select_one("div.event__description section.wysiwyg")
            if desc_section:
                return desc_section.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"  ⚠️ Error fetching description for {url}: {e}")
        return ""

    # TODO rework logic so we don't hit rate limits, currently works hackily with a hardcoded 1 day limit
    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return events occurring within the next `future_days` days (from
        now).  A small default keeps the scraper focused; caller can override
        (e.g. dev mode passes 2)."""
        # under the new requirements we ignore `future_days` entirely;
        # instead we only scrape the week container marked as current and drop
        # any individual day that has a past marker
        events = []
        # we still use month parameters so that if the current week spills into
        # the next month the appropriate URL will be fetched
        month_params = self._get_month_params_for_range(future_days)

        for month_param in month_params:
            url = self.BASE_URL + month_param
            try:
                print(f"🔗 Fetching: {url}")
                if self.use_selenium and hasattr(self, 'driver'):
                    self.driver.get(url)
                    time.sleep(3)  # Wait for page to load
                    soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                else:
                    response = self._make_request(url)
                    soup = BeautifulSoup(response.text, 'html.parser')

                # restrict to current week container if present
                week_section = soup.select_one("div.week--current")
                if week_section:
                    day_blocks = week_section.select("div.date.day")
                else:
                    day_blocks = soup.select("div.date.day")

                # drop any day blocks marked as past (class contains 'past')
                filtered = []
                for day in day_blocks:
                    cls = " ".join(day.get("class", []))
                    if "past" in cls:
                        continue
                    filtered.append(day)
                day_blocks = filtered

                for day in day_blocks:
                    # at this point we're only looking at candidate days;
                    # parse the date for logging or potential future filtering
                    month_span = day.select_one(".day__month")
                    day_span = day.select_one(".day__number")
                    if not month_span or not day_span:
                        continue
                    try:
                        month = month_span.get_text(strip=True)
                        day_num = day_span.get_text(strip=True)
                        date_str = f"{month} {day_num} {datetime.now().year}"
                        event_date = datetime.strptime(date_str, "%b %d %Y")
                    except Exception:
                        event_date = None

                    event_items = day.select("ul.events > li.event")
                    for item in event_items:
                        title_elem = item.select_one(".event__title")
                        link_elem = item.select_one("a")
                        time_elem = item.select_one(".action__time")
                        venue_elem = item.select_one(".venue__title")

                        title = title_elem.get_text(strip=True) if title_elem else "Untitled"
                        url = link_elem['href'] if link_elem and link_elem.has_attr('href') else ""
                        time_text = time_elem.get_text(strip=True).replace("\n", "") if time_elem else ""
                        venue = venue_elem.get_text(strip=True) if venue_elem else "The PIT"

                        try:
                            if event_date and time_text:
                                full_dt = datetime.strptime(f"{event_date.strftime('%Y-%m-%d')} {time_text}", "%Y-%m-%d %I:%M%p")
                            else:
                                full_dt = event_date
                        except Exception:
                            full_dt = event_date

                        description = self.fetch_event_description(url)

                        event = Event(
                            title=title,
                            venue=venue,
                            start_time=full_dt,
                            description=description,
                            url=url,
                            source="pit"
                        )

                        events.append(event)
                        
                        # Small delay to avoid rate limiting
                        time.sleep(2)

            except Exception as e:
                print(f"Error fetching PIT events for {month_param or 'current month'}: {e}")
                continue
            
            # Delay between month fetches to avoid rate limiting
            if month_param:
                time.sleep(5)

        return events
