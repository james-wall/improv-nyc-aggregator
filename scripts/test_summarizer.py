import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scrapers.pit import PitScraper
from src.agents.summarizer import summarize_events

def main(dev=False):
    print("⏳ Scraping PIT events...")
    scraper = PitScraper()
    if dev:
        events = scraper.fetch(max_days=2)  # Only scrape first 2 days
    else:
        events = scraper.fetch()

    print(f"\n📅 Fetched {len(events)} events.")

    if not events:
        print("❌ No events found.")
        return

    print("\n🪄 Generating summary with Gemini...")
    summary = summarize_events(events)

    print("\n📬 Summary:")
    print("=" * 40)
    print(summary)
    print("=" * 40)

if __name__ == "__main__":
    dev_mode = "dev" in sys.argv
    main(dev=dev_mode)
