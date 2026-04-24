# Our Scene — NYC

An agentic newsletter that curates the best live improv and sketch comedy in New York City each week.

**Live site:** https://james-wall.github.io/improv-nyc-aggregator
**Newsletter signup:** on the site, powered by Buttondown
**Instagram:** [@ourscenenyc](https://instagram.com/ourscenenyc)

## How it works

Every Sunday at 9 PM UTC, a GitHub Action runs this pipeline:

1. **Scrape** 7 NYC venues (The PIT, Magnet, UCB, Brooklyn Comedy Collective, Second City, Caveat, The Rat)
2. **Curate** the events via Gemini — picks ~5–8 shows per day, flags standouts, writes short details
3. **Render** an HTML + plaintext newsletter
4. **Send** to every confirmed Buttondown subscriber via the Buttondown API

The same pipeline can be triggered manually from the Actions tab.

## Repo layout

```
docs/                  GitHub Pages landing page (signup + archive)
src/
  scrapers/            One scraper per venue
  agents/summarizer.py Gemini curation (structured JSON output)
  emailer/             Buttondown + legacy SMTP senders
  store/db.py          SQLite description cache
  prompts/             LLM prompts
scripts/
  generate_newsletter.py   Main orchestrator
.github/workflows/weekly-newsletter.yml   Sunday cron
```

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in keys

# Generate the newsletter (saves last_newsletter.html / .txt, does not send)
python scripts/generate_newsletter.py

# Dev mode — shorter 3-day window for faster iteration
python scripts/generate_newsletter.py dev

# Send via Buttondown to your real subscriber list
python scripts/generate_newsletter.py --send
```

## Required secrets (GitHub Actions)

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | LLM curation |
| `BUTTONDOWN_API_KEY` | Newsletter send |

## Next steps

### Short term
- **Instagram auto-posting.** Generate a 1080×1080 image with top picks via Pillow, host it somewhere public, and post via the Instagram Graph API (needs a Business account + Meta App Review) or a wrapper like Buffer.
- **Custom domain.** Buy `ourscene.com`, point it at GitHub Pages, and set up SPF/DKIM in Buttondown for better deliverability and faster confirmation emails.
- **Verify The Rat timezone handling.** Second City had a UTC→local bug; The Rat may have the same issue — confirm what format its JSON-LD `startDate` uses.
- **Monitor PIT representation.** We nudged the curator to give every venue weekly coverage — watch the next few issues and tighten further if PIT keeps getting skipped.

### Medium term
- **Opt-in for class shows / jams / open mics.** Currently filtered out; some subscribers might want them. Offer as a preference.
- **Better image / descriptions.** Fetch flyers or pull more structured data so the newsletter has visuals beyond text tables.
- **Engagement analytics.** Track open/click rates from Buttondown to inform curation.

### Long term
- **Multi-city expansion.** Structure the site as `ourscene.com/nyc`, `/la`, etc., with a scraper set per city.
- **Reader submissions.** Let performers and promoters submit events directly — reduce reliance on scraping.
- **Community features.** Reviews, favorite teams, show-of-the-week voting.
