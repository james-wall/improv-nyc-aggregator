#!/usr/bin/env python3
"""Generate the weekly NYC improv & sketch newsletter.

Usage:
    python scripts/generate_newsletter.py              # default 7 days
    python scripts/generate_newsletter.py 14           # next 14 days
    python scripts/generate_newsletter.py --send       # send via email
    python scripts/generate_newsletter.py dev          # shorter scrape window

The newsletter window starts *tomorrow* (so a Sunday-evening send leads
with Monday) and runs for ``future_days`` days from there.
"""

import sys
import os
import html as html_lib
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
from src.agents.summarizer import curate_events_json
from src.venues import lookup as venue_lookup

SUMMARY_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_newsletter.txt')
HTML_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_newsletter.html')


def scrape_all(future_days: int, start_date):
    """Run all scrapers and return events filtered to >= start_date."""
    scrapers = [
        ("PIT", PitScraper()),
        ("Magnet", MagnetScraper()),
        ("BCC", BccScraper()),
        ("UCB", UcbScraper()),
        ("Second City", SecondCityScraper()),
        ("Caveat", CaveatScraper()),
        ("The Rat", TheRatScraper()),
    ]

    # Scrapers count their window from "today", so to cover an N-day window
    # starting tomorrow we ask for N+1 days and drop today's events below.
    scrape_days = future_days + 1

    all_events = []
    for name, scraper in scrapers:
        print(f"\n⏳ Scraping {name}...")
        try:
            events = scraper.fetch(future_days=scrape_days)
            print(f"  ✅ {len(events)} events from {name}")
            all_events.extend(events)
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")

    # Drop events before start_date (i.e., today)
    all_events = [
        e for e in all_events
        if e.start_time and e.start_time.date() >= start_date
    ]

    all_events.sort(key=lambda e: e.start_time or datetime.max)

    EXCLUDED_FORMATS = {"class_show", "jam", "open_mic"}
    filtered = [e for e in all_events if e.show_format in EXCLUDED_FORMATS]
    newsletter_events = [e for e in all_events if e.show_format not in EXCLUDED_FORMATS]
    if filtered:
        from collections import Counter
        fmt_counts = Counter(e.show_format for e in filtered)
        parts = [f"{count} {fmt}" for fmt, count in sorted(fmt_counts.items())]
        print(f"  📚 Filtered out: {', '.join(parts)}")

    return newsletter_events


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _esc(s) -> str:
    return html_lib.escape(str(s) if s is not None else "")


def render_day_table(day: dict) -> str:
    """Render one day as an HTML table.

    Header row spans all columns: "Monday, April 7  🎭"
    Columns: Time (★) | Location (venue linked + neighborhood) | Title (linked) | Details
    """
    label = _esc(day.get("label", ""))
    emoji = _esc(day.get("emoji", ""))
    shows = day.get("shows", []) or []

    header_cell = (
        '<th colspan="4" '
        'style="background-color: #8B0000; color: #FFD700; padding: 12px 14px; '
        'text-align: left; font-size: 16px; letter-spacing: 1px; '
        'border-bottom: 3px solid #FFD700;">'
        f'{label} &nbsp; {emoji}'
        '</th>'
    )

    cell_base = (
        'padding: 10px 12px; border-bottom: 1px solid #2a2238; '
        'font-size: 14px; color: #e8e0d4; vertical-align: top;'
    )

    rows: list[str] = []
    for show in shows:
        time_s = _esc(show.get("time", ""))
        venue = show.get("venue", "")
        title = show.get("title", "")
        url = show.get("url", "")
        starred = bool(show.get("starred"))
        details = _esc(show.get("details", ""))

        neighborhood, maps_url = venue_lookup(venue)

        location_html = (
            f'<a href="{_esc(maps_url)}" '
            f'style="color: #FFD700; text-decoration: none;">{_esc(venue)}</a>'
            f' ({_esc(neighborhood)})'
        )
        star = "&#9733; " if starred else ""
        time_html = f'{star}{time_s}'
        title_html = (
            f'<a href="{_esc(url)}" '
            f'style="color: #FF6B6B; text-decoration: underline; font-weight: bold;">'
            f'{_esc(title)}</a>'
        )

        rows.append(
            "<tr>"
            f'<td width="10%" style="{cell_base} white-space: nowrap; color: #FFD700;">{time_html}</td>'
            f'<td width="20%" style="{cell_base}">{location_html}</td>'
            f'<td width="28%" style="{cell_base}">{title_html}</td>'
            f'<td width="42%" style="{cell_base} line-height: 1.5;">{details}</td>'
            "</tr>"
        )

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color: #1e1e2a; border-radius: 8px; '
        'overflow: hidden; margin: 0 0 24px 0; border-collapse: collapse;">'
        f"<tr>{header_cell}</tr>"
        + "".join(rows)
        + "</table>"
    )


def build_newsletter_html(curated: dict, date_range: str) -> str:
    """Wrap the per-day tables in a full HTML email template."""
    days = curated.get("days", []) or []
    body_html = "".join(render_day_table(d) for d in days)
    if not body_html:
        body_html = (
            '<p style="color: #e8e0d4;">No standout shows surfaced this week. '
            "Check the venues directly.</p>"
        )

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>This Week in NYC Improv &amp; Sketch</title>
</head>
<body style="margin: 0; padding: 0; background-color: #1a1117; font-family: 'Trebuchet MS', 'Lucida Grande', Verdana, sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color: #1a1117; padding: 20px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="background-color: #1e1e2a; border-radius: 8px; overflow: hidden;">

  <!-- Header -->
  <tr>
    <td style="background-color: #8B0000; color: #FFD700; padding: 32px 40px; text-align: center; border-bottom: 4px solid #FFD700;">
      <p style="margin: 0 0 6px 0; font-size: 12px; letter-spacing: 4px; text-transform: uppercase; color: #ffecb3;">
        &#9733; NOW SHOWING &#9733;
      </p>
      <h1 style="margin: 0; font-size: 24px; font-weight: bold; letter-spacing: 2px; text-transform: uppercase;">
        This Week in NYC Improv &amp; Sketch
      </h1>
      <p style="margin: 10px 0 0 0; font-size: 14px; color: #ffecb3;">
        {_esc(date_range)}
      </p>
    </td>
  </tr>

  <!-- Greeting -->
  <tr>
    <td style="padding: 28px 32px 12px 32px;">
      <p style="margin: 0 0 12px 0; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
        Hey there,
      </p>
      <p style="margin: 0 0 20px 0; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
        Here's a curated digest of what caught our eye on NYC improv &amp; sketch stages this week. Just the stuff we'd actually tell a friend about.
      </p>
    </td>
  </tr>

  <!-- Body (per-day tables) -->
  <tr>
    <td style="padding: 0 32px;">
      {body_html}
    </td>
  </tr>

  <!-- Signoff -->
  <tr>
    <td style="padding: 16px 32px 16px 32px; border-top: 1px dashed #333344;">
      <p style="margin: 0 0 8px 0; font-size: 16px; line-height: 1.6; color: #e8e0d4;">
        That's the week. Go see something live &mdash; your couch will still be there when you get back.
      </p>
      <p style="margin: 0; font-size: 16px; line-height: 1.6; color: #FFD700;">
        &mdash; The NYC Improv &amp; Sketch Digest crew &#127908;
      </p>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background-color: #8B0000; padding: 20px 40px; text-align: center; font-size: 12px; color: #ffecb3; border-top: 3px solid #FFD700;">
      <p style="margin: 0; font-size: 11px; color: #ffcc80; margin-bottom: 6px;">Venues we follow</p>
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


def build_plaintext_newsletter(curated: dict, date_range: str) -> str:
    days = curated.get("days", []) or []
    lines: list[str] = []
    lines.append("THIS WEEK IN NYC IMPROV & SKETCH")
    lines.append(date_range)
    lines.append("=" * 40)
    lines.append("")
    lines.append("Hey there,")
    lines.append("")
    lines.append(
        "Here's a curated digest of what caught our eye on NYC improv & "
        "sketch stages this week. Just the stuff we'd actually tell a "
        "friend about."
    )
    lines.append("")

    for day in days:
        label = day.get("label", "")
        emoji = day.get("emoji", "")
        lines.append(f"{label}  {emoji}".rstrip())
        lines.append("-" * 40)
        for show in day.get("shows", []) or []:
            star = "* " if show.get("starred") else ""
            time_s = show.get("time", "")
            venue = show.get("venue", "")
            neighborhood, _ = venue_lookup(venue)
            title = show.get("title", "")
            url = show.get("url", "")
            details = show.get("details", "")
            lines.append(f"{star}{time_s} — {venue} ({neighborhood}) — {title}")
            if details:
                lines.append(f"    {details}")
            if url:
                lines.append(f"    {url}")
            lines.append("")
        lines.append("")

    lines.append(
        "That's the week. Go see something live — your couch will still "
        "be there when you get back."
    )
    lines.append("")
    lines.append("— The NYC Improv & Sketch Digest crew")
    lines.append("")
    lines.append("---")
    lines.append("Venues we follow: The PIT · Magnet · BCC · UCB · Second City NY · Caveat · The Rat")
    lines.append("Got a tip or want to be featured? Reply to this email.")
    return "\n".join(lines)


def main(future_days: int = 7, send: bool = False):
    today = datetime.now().date()
    start_date = today + timedelta(days=1)            # newsletter starts tomorrow
    end_date = start_date + timedelta(days=future_days - 1)
    date_range = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}"

    # 1. Scrape all venues, dropping anything before tomorrow
    events = scrape_all(future_days, start_date)
    print(f"\n📅 Total: {len(events)} events in window")

    if not events:
        print("❌ No events found across any venue.")
        return

    # 2. Curate via LLM into structured per-day JSON
    print("\n🪄 Curating newsletter with Gemini...")
    curated = curate_events_json(events, days=future_days, date_range=date_range)
    day_count = len(curated.get("days", []) or [])
    show_count = sum(len(d.get("shows", []) or []) for d in curated.get("days", []) or [])
    print(f"  📋 {day_count} days, {show_count} curated shows")

    # 3. Build full newsletter (plain text + HTML)
    plaintext = build_plaintext_newsletter(curated, date_range)
    html = build_newsletter_html(curated, date_range)

    # 4. Save to files
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(plaintext)
    print(f"\n💾 Plain text saved to last_newsletter.txt")

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"💾 HTML saved to last_newsletter.html")

    # 5. Optionally send
    if send:
        subject = f"This Week in NYC Improv & Sketch 🎭 ({date_range})"

        if os.getenv("BUTTONDOWN_API_KEY"):
            try:
                from src.emailer.buttondown_sender import send_newsletter
                send_newsletter(subject=subject, body=plaintext, html=html)
            except Exception as e:
                print(f"❌ Buttondown send failed: {e}")
        else:
            # Legacy SMTP fallback for local testing
            to = os.getenv("NEWSLETTER_RECIPIENT")
            if not to:
                print("⚠️  NEWSLETTER_RECIPIENT not set — skipping email send.")
                return
            try:
                from src.emailer.smtp_sender import send_email
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
