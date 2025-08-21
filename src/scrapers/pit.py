import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil.relativedelta import relativedelta
from src.models import Event

class PitScraper:
    BASE_URL = "https://thepit-nyc.com/calendar/"

    def _get_month_params(self) -> list[str]:
        months = []
        for i in range(3): # current + next 2 months
            month_date = datetime.now().month + relativedelta(months=i)
            if i == 0:
                months.append("")
            else:
                formatted = month_date.strftime("?month=%b-%Y") # e.g., "?month=Sep-2025"
                months.append(formatted)
        return months

    def fetch(self) -> list[Event]:
        events = []
        try:
            response = requests.get(self.SHOWS_PAGE)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            show_cards = soup.select(".fusion-portfolio-post")

            for card in show_cards:
                title_elem = card.select_one(".fusion-title a")
                datetime_elem = card.select_one(".fusion-post-meta")
                desc_elem = card.select_one(".fusion-post-content-container")

                if not title_elem or not datetime_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = title_elem.get("href")
                date_text = datetime_elem.get_text(strip=True)
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Attempt to parse date (e.g., "August 23 @ 9:30 pm")
                try:
                    event_time = datetime.strptime(date_text, "%B %d @ %I:%M %p")
                except ValueError:
                    event_time = None

                event = Event(
                    title=title,
                    venue="The PIT NYC",
                    start_time=event_time,
                    description=description,
                    url=url,
                    source="pit"
                )
                events.append(event)

        except Exception as e:
            print(f"Error fetching PIT events: {e}")

        return events
