import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil.relativedelta import relativedelta
from src.models import Event

class PitScraper:
    BASE_URL = "https://thepit-nyc.com/calendar/"

    def _get_month_params(self) -> list[str]:
        months = []
        for i in range(3):  # current + next 2 months
            month_date = datetime.now() + relativedelta(months=i)
            if i == 0:
                months.append("")  # current month = default view
            else:
                formatted = month_date.strftime("?month=%b-%Y")  # e.g., ?month=Sep-2025
                months.append(formatted)
        return months
    
    def fetch_event_description(self, url: str) -> str:
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            desc_section = soup.select_one("div.event__description section.wysiwyg")
            if desc_section:
                return desc_section.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"  ⚠️ Error fetching description for {url}: {e}")
        return ""

    def fetch(self) -> list[Event]:
        events = []
        for month_param in self._get_month_params():
            url = self.BASE_URL + month_param
            try:
                response = requests.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                day_blocks = soup.select("div.date.day")
                for day in day_blocks:
                    # Get date info
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

                    # Get each event in the day block
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

            except Exception as e:
                print(f"Error fetching PIT events for {month_param or 'current month'}: {e}")
                continue

        return events
