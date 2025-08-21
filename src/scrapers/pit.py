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
        
        for month_param in self._get_month_params():
            url = self.BASE_URL + month_param
            try:
                response = requests.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')


                # Each show is in a <li class="event ..."> inside a <ul class="events">
                event_items = soup.select("ul.events > li.event")


                for item in event_items:
                    title_elem = item.select_one(".event__title")
                    link_elem = item.select_one("a")
                    time_elem = item.select_one(".action__time")
                    venue_elem = item.select_one(".venue__title")


                title = title_elem.get_text(strip=True) if title_elem else ""
                url = link_elem['href'] if link_elem and link_elem.has_attr('href') else ""
                time_text = time_elem.get_text(strip=True) if time_elem else ""
                venue = venue_elem.get_text(strip=True) if venue_elem else "The PIT"


                # Try to guess datetime from URL and time (URL usually has event slug but no date)
                # Note: For real scraping, you'd want to combine with the day block info
                try:
                # Placeholder: In reality we’d need to extract the date from the DOM hierarchy
                    event_time = datetime.strptime(time_text, "%I:%M%p")
                except Exception:
                    event_time = None


                event = Event(
                    title=title,
                    venue=venue,
                    start_time=event_time,
                    description="", # Can expand later if needed
                    url=url,
                    source="pit"
                )
                events.append(event)


            except Exception as e:
                print(f"Error fetching PIT events for {month_param or 'current month'}: {e}")


                return events