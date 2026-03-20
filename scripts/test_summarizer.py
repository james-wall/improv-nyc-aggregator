import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.scrapers.pit import PitScraper
from src.agents.summarizer import summarize_events

SUMMARY_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_summary.txt')

def main(dev=False, send=False):
    print("⏳ Scraping PIT events...")
    scraper = PitScraper()
    if dev:
        events = scraper.fetch(future_days=2)
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

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\n💾 Summary saved to last_summary.txt")

    if send:
        to = os.getenv("TEST_EMAIL")
        if not to:
            print("⚠️  TEST_EMAIL not set in .env — skipping email send.")
            return
        try:
            from src.emailer.gmail_sender import send_email
            send_email(to=to, subject="This Week in NYC Improv 🎭", body=summary)
        except Exception as e:
            print(f"❌ Email send failed: {e}")
            print("   Make sure credentials.json is present and Gmail OAuth is set up.")

if __name__ == "__main__":
    dev_mode = "dev" in sys.argv
    send_mode = "--send" in sys.argv
    main(dev=dev_mode, send=send_mode)
