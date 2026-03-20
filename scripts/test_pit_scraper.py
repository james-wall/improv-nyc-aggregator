# scripts/test_pit_scraper.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scrapers.pit import PitScraper


def main(dev=False, future_days: int = 7):
    scraper = PitScraper()
    if dev and future_days == 7:
        future_days = 2
    events = scraper.fetch(future_days=future_days)

    print(f"\nDEBUG: Found {len(events)} events.\n")
    for i, e in enumerate(events, 1):
        print(f"Event {i}:")
        print(f"  Title: {e.title}")
        print(f"  Time: {e.start_time}")
        print(f"  Venue: {e.venue}")
        print(f"  URL: {e.url}")
        print(f"  Description: {e.description[:100]}...\n")


if __name__ == "__main__":
    dev_mode = "dev" in sys.argv
    future_days = 3
    for arg in sys.argv[1:]:
        if arg.isdigit():
            future_days = int(arg)
            break
    main(dev=dev_mode, future_days=future_days)
