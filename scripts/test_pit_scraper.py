# scripts/test_pit_scraper.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scrapers.pit import PitScraper
from src.models import Event


def main():
    scraper = PitScraper()
    events = scraper.fetch()

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
    main()
