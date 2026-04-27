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
import glob
import re
import html as html_lib
from datetime import date, datetime, timedelta

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
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'archive')


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
    """Render one day as stacked show cards (mobile-friendly, single-column)."""
    label = _esc(day.get("label", ""))
    emoji = _esc(day.get("emoji", ""))
    date_iso = day.get("date_iso", "")
    shows = day.get("shows", []) or []

    anchor = f' id="day-{_esc(date_iso)}"' if date_iso else ""
    header = (
        f'<tr><td{anchor} style="background-color: #8B0000; color: #FFD700; padding: 12px 14px; '
        'text-align: left; font-size: 16px; letter-spacing: 1px; '
        f'border-bottom: 3px solid #FFD700;">{label} &nbsp; {emoji}</td></tr>'
    )

    cards: list[str] = []
    for show in shows:
        time_s = _esc(show.get("time", ""))
        venue = show.get("venue", "")
        title = show.get("title", "")
        url = show.get("url", "")
        starred = bool(show.get("starred"))
        details = _esc(show.get("details", ""))

        neighborhood, maps_url = venue_lookup(venue)

        star = "&#9733; " if starred else ""
        venue_html = (
            f'<a href="{_esc(maps_url)}" '
            f'style="color: #FFD700; text-decoration: none;">{_esc(venue)}</a>'
        )
        title_html = (
            f'<a href="{_esc(url)}" '
            f'style="color: #FF6B6B; text-decoration: underline; font-weight: bold; '
            f'font-size: 16px;">{_esc(title)}</a>'
        )

        card = (
            '<tr><td style="padding: 14px 16px; border-bottom: 1px solid #2a2238;">'
            f'<p style="margin: 0 0 4px 0; font-size: 13px; color: #FFD700;">'
            f'{star}{time_s} &middot; {venue_html} ({_esc(neighborhood)})</p>'
            f'<p style="margin: 0 0 6px 0;">{title_html}</p>'
            f'<p style="margin: 0; font-size: 14px; line-height: 1.5; color: #d4ccd0;">'
            f'{details}</p>'
            '</td></tr>'
        )
        cards.append(card)

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color: #1e1e2a; border-radius: 8px; '
        'overflow: hidden; margin: 0 0 24px 0; border-collapse: collapse;">'
        + header
        + "".join(cards)
        + "</table>"
    )


def _build_jump_nav(days: list[dict]) -> str:
    """Render a visual table-of-contents showing which days are covered."""
    if not days:
        return ""
    items = []
    for d in days:
        label = d.get("label", "")
        short = label.split(",")[0].strip() if "," in label else label
        emoji = d.get("emoji", "")
        if short:
            items.append(
                f'<span style="white-space: nowrap;">{_esc(emoji)} {_esc(short)}</span>'
            )
    if not items:
        return ""
    return (
        '<p style="margin: 0 0 6px 0; font-size: 13px; letter-spacing: 1px; '
        'text-transform: uppercase; color: #ffecb3; text-align: center;">'
        f'This week, {len(days)} days of shows &darr;</p>'
        '<p style="margin: 0; font-size: 14px; line-height: 2.2; '
        'color: #FFD700; text-align: center;">'
        + ' &nbsp;&middot;&nbsp; '.join(items)
        + '</p>'
    )


def build_newsletter_html(curated: dict, date_range: str) -> str:
    """Wrap the per-day tables in a full HTML email template."""
    days = curated.get("days", []) or []
    body_html = "".join(render_day_table(d) for d in days)
    jump_nav = _build_jump_nav(days)
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
      <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.6; color: #b8b0b4;">
        Forwarded this? <a href="https://james-wall.github.io/improv-nyc-aggregator" style="color: #FFD700;">Subscribe here</a> so you don't miss next week.
      </p>
    </td>
  </tr>

  <!-- Jump to -->
  <tr>
    <td style="padding: 0 32px 16px 32px;">
      {jump_nav}
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
      <p style="margin: 0 0 12px 0; font-size: 16px; line-height: 1.6; color: #FFD700;">
        &mdash; The NYC Improv &amp; Sketch Digest crew &#127908;
      </p>
      <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #b8b0b4;">
        Know someone who'd like this? Send them to <a href="https://james-wall.github.io/improv-nyc-aggregator" style="color: #FFD700;">ourscene</a>.
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
      <p style="margin: 8px 0 0 0; font-size: 11px; color: #ffcc80;">
        <a href="https://james-wall.github.io/improv-nyc-aggregator" style="color: #FFD700; text-decoration: none;">ourscene &middot; NYC</a>
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
    lines.append(
        "Forwarded this? Subscribe at https://james-wall.github.io/improv-nyc-aggregator"
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
    lines.append("Know someone who'd like this? Send them to https://james-wall.github.io/improv-nyc-aggregator")
    lines.append("")
    lines.append("---")
    lines.append("Venues we follow: The PIT · Magnet · BCC · UCB · Second City NY · Caveat · The Rat")
    lines.append("Got a tip or want to be featured? Reply to this email.")
    lines.append("ourscene · NYC — https://james-wall.github.io/improv-nyc-aggregator")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Archive (writes static issue pages and an index into docs/archive)
# ---------------------------------------------------------------------------

_ARCHIVE_NAV = (
    '<div style="background-color: #1a1117; padding: 14px 20px; '
    'text-align: center; border-bottom: 1px solid #2a2238;">'
    '<a href="../" style="color: #FFD700; text-decoration: none; '
    'font-family: \'Trebuchet MS\', sans-serif; font-size: 14px; '
    'letter-spacing: 0.04em;">&larr; Back to Our Scene</a>'
    '</div>'
)


def _wrap_for_archive(email_html: str) -> str:
    """Inject a navigation banner at the top of an archived issue page."""
    return re.sub(r"(<body[^>]*>)", r"\1" + _ARCHIVE_NAV, email_html, count=1)


def _format_archive_label(date_iso: str) -> str:
    """'2026-04-28' -> 'Week of April 28, 2026'."""
    dt = datetime.strptime(date_iso, "%Y-%m-%d").date()
    return f"Week of {dt.strftime('%B %-d, %Y')}"


def _list_archive_issues() -> list[tuple[str, str]]:
    """Return [(YYYY-MM-DD, filename)] for each archived issue, newest first."""
    pattern = os.path.join(ARCHIVE_DIR, "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].html")
    issues = []
    for path in glob.glob(pattern):
        fname = os.path.basename(path)
        date_iso = fname[:10]
        try:
            datetime.strptime(date_iso, "%Y-%m-%d")
        except ValueError:
            continue
        issues.append((date_iso, fname))
    issues.sort(reverse=True)
    return issues


def _build_archive_index(issues: list[tuple[str, str]]) -> str:
    """Render docs/archive/index.html listing every archived issue."""
    if issues:
        items = "\n".join(
            f'      <li><a href="{_esc(fname)}">{_esc(_format_archive_label(date_iso))}</a></li>'
            for date_iso, fname in issues
        )
        body = f"<ul class=\"issues\">\n{items}\n    </ul>"
    else:
        body = '<p class="empty">No issues archived yet — check back after Sunday.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Past issues — Our Scene</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background-color: #1a1117; color: #e8e0e4; min-height: 100vh;
      font-family: 'Trebuchet MS', 'Lucida Grande', Verdana, sans-serif;
    }}
    .hero {{
      background-color: #8B0000; border-bottom: 4px solid #FFD700;
      text-align: center; padding: 48px 24px;
    }}
    .hero h1 {{ color: #FFD700; font-size: 2.4rem; letter-spacing: 0.04em; }}
    .hero .tagline {{ color: #ffecb3; margin-top: 6px; font-size: 1rem; }}
    .hero a.back {{
      display: inline-block; margin-top: 16px; color: #FFD700;
      text-decoration: none; font-size: 0.9rem;
      border-bottom: 1px solid transparent;
    }}
    .hero a.back:hover {{ border-bottom-color: #FFD700; }}
    main {{ max-width: 620px; margin: 0 auto; padding: 48px 24px; }}
    .issues {{ list-style: none; }}
    .issues li {{
      background-color: #1e1e2a; border-radius: 8px; margin-bottom: 12px;
    }}
    .issues a {{
      display: block; padding: 18px 24px; color: #FFD700;
      text-decoration: none; font-size: 1.05rem;
      border: 1px solid transparent; border-radius: 8px; transition: border-color 0.2s;
    }}
    .issues a:hover {{ border-color: #FFD700; }}
    .empty {{ color: #b8b0b4; text-align: center; }}
  </style>
</head>
<body>
  <header class="hero">
    <h1>Past issues</h1>
    <p class="tagline">Every week we've covered, in one place.</p>
    <a class="back" href="../">&larr; Back to Our Scene</a>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""


def archive_issue(issue_date: date, html: str) -> None:
    """Save a dated copy of the issue and rebuild the archive index."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    date_iso = issue_date.strftime("%Y-%m-%d")
    issue_path = os.path.join(ARCHIVE_DIR, f"{date_iso}.html")
    with open(issue_path, "w", encoding="utf-8") as f:
        f.write(_wrap_for_archive(html))
    print(f"🗄  Archived issue to docs/archive/{date_iso}.html")

    index_path = os.path.join(ARCHIVE_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(_build_archive_index(_list_archive_issues()))
    print(f"🗄  Rebuilt archive index")


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
            from src.emailer.buttondown_sender import send_newsletter
            try:
                send_newsletter(subject=subject, body=plaintext, html=html)
            except Exception as e:
                print(f"❌ Buttondown send failed: {e}")
                sys.exit(1)
            archive_issue(start_date, html)
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
                sys.exit(1)


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
