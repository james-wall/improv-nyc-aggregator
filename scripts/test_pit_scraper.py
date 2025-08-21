# scripts/test_pit_scraper.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scrapers.pit import PitScraper
from src.models import Event


def main():
    scraper = PitScraper()
    events = scraper.fetch()

    if not events:
        print("No events found.")
        return

    print(f"✅ Found {len(events)} events from The PIT:\n")
    for e in events:
        print(f"🎭 {e.title}")
        print(f"   📍 Venue: {e.venue}")
        print(f"   🕒 Time: {e.start_time}")
        print(f"   🔗 URL: {e.url}")
        print(f"   📝 Description: {e.description[:120]}...\n")

if __name__ == "__main__":
    main()
