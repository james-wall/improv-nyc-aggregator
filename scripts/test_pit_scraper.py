# scripts/test_pit_scraper.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scrapers.pit import PitScraper
from src.models import Event


def main(dev=False, use_selenium=False, future_days: int = 7):
    scraper = PitScraper(use_selenium=use_selenium)
    if dev and future_days == 7:
        future_days = 2
    events = scraper.fetch(future_days=future_days)

    # if not events:
    #     print("No events found.")
    #     return

    print(f"\nDEBUG: Found {len(events)} events.\n")
    for i, e in enumerate(events, 1):
        print(f"Event {i}:")
        print(f"  Title: {e.title}")
        print(f"  Time: {e.start_time}")
        print(f"  Venue: {e.venue}")
        print(f"  URL: {e.url}")
        print(f"  Description: {e.description[:100]}...\n")


if __name__ == "__main__":
    import sys
    dev_mode = "dev" in sys.argv
    use_selenium = "selenium" in sys.argv
    # look for numeric arg to override days
    future_days = 3
    for arg in sys.argv[1:]:
        if arg.isdigit():
            future_days = int(arg)
            break
    main(dev=dev_mode, use_selenium=use_selenium, future_days=future_days)

