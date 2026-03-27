#!/usr/bin/env python3
"""Generate the weekly NYC improv newsletter.

Usage:
    python scripts/generate_newsletter.py              # default 7 days
    python scripts/generate_newsletter.py 14           # next 14 days
    python scripts/generate_newsletter.py --send       # send via email
    python scripts/generate_newsletter.py dev          # shorter scrape window
"""

import sys
import os
import re
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.scrapers.pit import PitScraper
from src.scrapers.magnet import MagnetScraper
from src.scrapers.bcc import BccScraper
from src.scrapers.ucb import UcbScraper
from src.scrapers.secondcity import SecondCityScraper
from src.scrapers.caveat import CaveatScraper
from src.scrapers.therat import TheRatScraper
from src.agents.summarizer import summarize_events

SUMMARY_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_newsletter.txt')
HTML_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_newsletter.html')


def scrape_all(future_days: int):
    """Run all scrapers and return a combined, sorted event list."""
    scrapers = [
        ("PIT", PitScraper()),
        ("Magnet", MagnetScraper()),
        ("BCC", BccScraper()),
        ("UCB", UcbScraper()),
        ("Second City", SecondCityScraper()),
        ("Caveat", CaveatScraper()),
        ("The Rat", TheRatScraper()),
    ]

    all_events = []
    for name, scraper in scrapers:
        print(f"\n⏳ Scraping {name}...")
        try:
            events = scraper.fetch(future_days=future_days)
            print(f"  ✅ {len(events)} events from {name}")
            all_events.extend(events)
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")

    # Sort by start time (None-times go last)
    all_events.sort(key=lambda e: e.start_time or datetime.max)

    # Filter out class shows for the newsletter (they're still in the DB)
    class_count = sum(1 for e in all_events if e.is_class_show)
    newsletter_events = [e for e in all_events if not e.is_class_show]
    if class_count:
        print(f"  📚 Filtered out {class_count} class/student shows")

    return newsletter_events


def markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML for newsletter body (bold, line breaks)."""
    html = md
    # Bold: **text** -> <strong>text</strong>
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    # Convert double newlines to paragraph breaks
    paragraphs = re.split(r'\n{2,}', html.strip())
    html = ''.join(f'<p style="margin: 0 0 16px 0;">{p.strip()}</p>' for p in paragraphs if p.strip())
    # Single newlines within paragraphs -> <br>
    html = html.replace('\n', '<br>\n')
    return html


def build_newsletter_html(body_md: str, date_range: str) -> str:
    """Wrap the generated body in a full HTML email template."""
    body_html = markdown_to_html(body_md)

    today_str = datetime.now().strftime("%B %d, %Y")

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>This Week in NYC Improv</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: Georgia, 'Times New Roman', serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden;">

  <!-- Header -->
  <tr>
    <td style="background-color: #1a1a2e; color: #ffffff; padding: 32px 40px; text-align: center;">
      <h1 style="margin: 0; font-size: 28px; font-weight: normal; letter-spacing: 1px;">
        This Week in NYC Improv
      </h1>
      <p style="margin: 8px 0 0 0; font-size: 14px; color: #b0b0cc;">
        {date_range}
      </p>
    </td>
  </tr>

  <!-- Greeting -->
  <tr>
    <td style="padding: 32px 40px 0 40px;">
      <p style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #333333;">
        Hey there,
      </p>
      <p style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #333333;">
        Here's what caught our eye on NYC comedy stages this week. As always, we're not trying to list everything &mdash; just the stuff we'd actually tell a friend about.
      </p>
    </td>
  </tr>

  <!-- Body (generated) -->
  <tr>
    <td style="padding: 0 40px; font-size: 16px; line-height: 1.6; color: #333333;">
      {body_html}
    </td>
  </tr>

  <!-- Signoff -->
  <tr>
    <td style="padding: 24px 40px 16px 40px;">
      <p style="margin: 0 0 8px 0; font-size: 16px; line-height: 1.6; color: #333333;">
        That's the week. Go see something live &mdash; your couch will still be there when you get back.
      </p>
      <p style="margin: 0; font-size: 16px; line-height: 1.6; color: #333333;">
        &mdash; The Improv NYC Digest team
      </p>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background-color: #f0f0f5; padding: 20px 40px; text-align: center; font-size: 12px; color: #888888;">
      <p style="margin: 0;">
        Covering The PIT &middot; Magnet Theater &middot; Brooklyn Comedy Collective &middot; UCB &middot; Second City NY &middot; Caveat &middot; The Rat
      </p>
      <p style="margin: 8px 0 0 0;">
        Got a tip or want to be featured? Reply to this email.
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def build_plaintext_newsletter(body: str, date_range: str) -> str:
    """Wrap the generated body in a plain-text email."""
    return f"""\
THIS WEEK IN NYC IMPROV
{date_range}
{'=' * 40}

Hey there,

Here's what caught our eye on NYC comedy stages this week. As always, we're \
not trying to list everything — just the stuff we'd actually tell a friend about.

{body}

That's the week. Go see something live — your couch will still be there when you get back.

— The Improv NYC Digest team

---
Covering The PIT · Magnet Theater · Brooklyn Comedy Collective · UCB · Second City NY · Caveat · The Rat
Got a tip or want to be featured? Reply to this email.
"""


def main(future_days: int = 7, send: bool = False):
    today = datetime.now()
    end = today + timedelta(days=future_days)
    date_range = f"{today.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"

    # 1. Scrape all venues
    events = scrape_all(future_days)
    print(f"\n📅 Total: {len(events)} events across all venues")

    if not events:
        print("❌ No events found across any venue.")
        return

    # 2. Generate curated summary
    print("\n🪄 Generating newsletter with Gemini...")
    body = summarize_events(
        events, style="newsletter",
        days=future_days, date_range=date_range,
    )
    print("\n📝 Generated body:")
    print("=" * 40)
    print(body)
    print("=" * 40)

    # 3. Build full newsletter (plain text + HTML)
    plaintext = build_plaintext_newsletter(body, date_range)
    html = build_newsletter_html(body, date_range)

    # 4. Save to files
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(plaintext)
    print(f"\n💾 Plain text saved to last_newsletter.txt")

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"💾 HTML saved to last_newsletter.html")

    # 5. Optionally send
    if send:
        to = os.getenv("TEST_EMAIL")
        if not to:
            print("⚠️  TEST_EMAIL not set in .env — skipping email send.")
            return
        try:
            from src.emailer.gmail_sender import send_email
            subject = f"This Week in NYC Improv 🎭 ({date_range})"
            send_email(to=to, subject=subject, body=plaintext, html=html)
        except Exception as e:
            print(f"❌ Email send failed: {e}")
            print("   Make sure credentials.json is present and Gmail OAuth is set up.")


if __name__ == "__main__":
    future_days = 7
    send_mode = "--send" in sys.argv
    dev_mode = "dev" in sys.argv

    for arg in sys.argv[1:]:
        if arg.isdigit():
            future_days = int(arg)
            break

    if dev_mode and future_days == 7:
        future_days = 3

    main(future_days=future_days, send=send_mode)
