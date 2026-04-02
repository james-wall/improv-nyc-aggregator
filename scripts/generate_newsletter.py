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

    # Filter out non-main-show formats (they're still in the DB for future use)
    EXCLUDED_FORMATS = {"class_show", "jam", "open_mic"}
    filtered = [e for e in all_events if e.show_format in EXCLUDED_FORMATS]
    newsletter_events = [e for e in all_events if e.show_format not in EXCLUDED_FORMATS]
    if filtered:
        from collections import Counter
        fmt_counts = Counter(e.show_format for e in filtered)
        parts = [f"{count} {fmt}" for fmt, count in sorted(fmt_counts.items())]
        print(f"  📚 Filtered out: {', '.join(parts)}")

    return newsletter_events


def markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML for newsletter body (bold, links, line breaks)."""
    html = md
    # Links: [text](url) -> <a href="url">text</a>
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color: #FF6B6B; text-decoration: underline;">\1</a>', html)
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
<body style="margin: 0; padding: 0; background-color: #1a1117; font-family: 'Trebuchet MS', 'Lucida Grande', Verdana, sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color: #1a1117; padding: 20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color: #1e1e2a; border-radius: 8px; overflow: hidden;">

  <!-- Header -->
  <tr>
    <td style="background-color: #8B0000; color: #FFD700; padding: 32px 40px; text-align: center; border-bottom: 4px solid #FFD700;">
      <p style="margin: 0 0 6px 0; font-size: 12px; letter-spacing: 4px; text-transform: uppercase; color: #ffecb3;">
        &#9733; NOW SHOWING &#9733;
      </p>
      <h1 style="margin: 0; font-size: 26px; font-weight: bold; letter-spacing: 3px; text-transform: uppercase;">
        This Week in NYC Improv
      </h1>
      <p style="margin: 10px 0 0 0; font-size: 14px; color: #ffecb3;">
        {date_range}
      </p>
    </td>
  </tr>

  <!-- Greeting -->
  <tr>
    <td style="padding: 32px 40px 0 40px;">
      <p style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
        Hey there,
      </p>
      <p style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
        Here's what caught our eye on NYC comedy stages this week. As always, we're not trying to list everything &mdash; just the stuff we'd actually tell a friend about.
      </p>
    </td>
  </tr>

  <!-- Body (generated) -->
  <tr>
    <td style="padding: 0 40px; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
      {body_html}
    </td>
  </tr>

  <!-- Signoff -->
  <tr>
    <td style="padding: 24px 40px 16px 40px; border-top: 1px dashed #333344;">
      <p style="margin: 0 0 8px 0; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
        That's the week. Go see something live &mdash; your couch will still be there when you get back.
      </p>
      <p style="margin: 0; font-size: 16px; line-height: 1.6; color: #FFD700;">
        &mdash; The Improv NYC Digest crew &#127908;
      </p>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background-color: #8B0000; padding: 20px 40px; text-align: center; font-size: 12px; color: #ffecb3; border-top: 3px solid #FFD700;">
      <p style="margin: 0; letter-spacing: 1px;">
        &#127902; THE PIT &middot; MAGNET &middot; BCC &middot; UCB &middot; SECOND CITY &middot; CAVEAT &middot; THE RAT &#127902;
      </p>
      <p style="margin: 10px 0 0 0; color: #ffcc80;">
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
        to = os.getenv("NEWSLETTER_RECIPIENT")
        if not to:
            print("⚠️  NEWSLETTER_RECIPIENT not set — skipping email send.")
            return
        try:
            from src.emailer.smtp_sender import send_email
            subject = f"This Week in NYC Improv 🎭 ({date_range})"
            send_email(to=to, subject=subject, body=plaintext, html=html)
        except Exception as e:
            print(f"❌ Email send failed: {e}")
            print("   Make sure GMAIL_ADDRESS and GMAIL_APP_PASSWORD are set.")


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
