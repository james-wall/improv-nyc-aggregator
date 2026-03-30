from __future__ import annotations

import random
import base64
import json
import requests
from datetime import datetime, timedelta
import time
from src.models import Event
from src.store import db as store
from src.utils.formatting import detect_show_format


class SecondCityScraper:
    """Scrape events from Second City New York via their GraphQL API.

    The Second City website is a headless WordPress (Faust.js / Next.js)
    frontend backed by a WPGraphQL endpoint at ``platform.secondcity.com``.
    Show data — including exact performance datetimes — is available through
    the ``patronticketData`` field, which contains base64-encoded JSON from
    their Salesforce ticketing backend.
    """

    GRAPHQL_URL = "https://platform.secondcity.com/graphql"
    BASE_URL = "https://www.secondcity.com"

    SHOWS_QUERY = """
    query NYShows($first: Int!, $offset: Int!) {
      shows(
        where: {
          location: ["new-york"]
          offsetPagination: {size: $first, offset: $offset}
        }
      ) {
        nodes {
          title
          slug
          uri
          dates { dates { dates } }
          showAttributes {
            showType
            description
            venue {
              ... on Venue {
                name
                slug
              }
            }
          }
          timeOfDay { timeOfDay }
          patronticketData { patronticketData }
        }
      }
    }
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

    BASE_HEADERS = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
    }

    @classmethod
    def _random_headers(cls) -> dict:
        return {**cls.BASE_HEADERS, "User-Agent": random.choice(cls.USER_AGENTS)}

    def __init__(self):
        store.init_db()
        self.session = requests.Session()
        self.session.headers.update(self._random_headers())

    def _make_request(self, url: str, json_body: dict = None, headers: dict = None, max_retries: int = 3):
        """Make a POST request with retry logic and exponential backoff."""
        request_headers = self._random_headers()
        if headers:
            request_headers.update(headers)

        print("making request for: " + str(url))

        for attempt in range(max_retries):
            try:
                response = self.session.post(url, json=json_body, timeout=60, headers=request_headers)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise e
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Request failed, retrying in {wait_time:.1f}s... ({e})")
                time.sleep(wait_time)

    def _parse_patronticket_instances(self, encoded: str) -> list[dict]:
        """Decode the base64-encoded patronticketData and extract performance instances."""
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            data = json.loads(decoded)
            return data.get("instances", [])
        except Exception:
            return []

    def _parse_dates_field(self, dates_data: dict | None) -> list[str]:
        """Extract YYYYMMDD date strings from the nested dates field."""
        if not dates_data:
            return []
        try:
            inner = dates_data.get("dates", {})
            return inner.get("dates", []) if inner else []
        except (AttributeError, TypeError):
            return []

    def _extract_venue(self, show_attrs: dict) -> str:
        """Extract venue name from showAttributes."""
        venues = show_attrs.get("venue", [])
        if venues and isinstance(venues, list):
            return venues[0].get("name", "Second City NY")
        elif venues and isinstance(venues, dict):
            return venues.get("name", "Second City NY")
        return "Second City NY"

    def _extract_description(self, show_attrs: dict) -> str:
        """Extract plain-text description from showAttributes HTML."""
        from bs4 import BeautifulSoup

        html = show_attrs.get("description", "")
        if html:
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(separator="\n", strip=True)
        return ""

    def fetch(self, future_days: int = 3) -> list[Event]:
        """Return Second City NY events occurring within the next ``future_days`` days.

        Uses the GraphQL API to fetch all NY shows, then filters by date.
        Exact performance times come from the patronticketData field.
        """
        events: list[Event] = []
        today = datetime.now().date()
        end_date = today + timedelta(days=future_days)

        try:
            print(f"🔗 Fetching Second City NY shows via GraphQL")
            response = self._make_request(
                self.GRAPHQL_URL,
                json_body={
                    "query": self.SHOWS_QUERY,
                    "variables": {"first": 100, "offset": 0},
                },
            )
            data = response.json()
            shows = data.get("data", {}).get("shows", {}).get("nodes", [])

            for show in shows:
                title = show.get("title", "Untitled")
                uri = show.get("uri", "")
                show_url = f"{self.BASE_URL}{uri}" if uri else ""
                show_attrs = show.get("showAttributes", {}) or {}
                venue = self._extract_venue(show_attrs)
                # Use API showType or fall back to title-based detection
                show_type = show_attrs.get("showType", "")
                show_fmt = detect_show_format(title)
                if show_type == "student":
                    show_fmt = "class_show"
                class_show = show_fmt == "class_show"

                # Try to get exact instances from patronticketData
                patron_data = show.get("patronticketData", {}) or {}
                encoded = patron_data.get("patronticketData", "")
                instances = self._parse_patronticket_instances(encoded) if encoded else []

                # Use cached description if available
                cached = store.get_show(show_url)
                if cached and cached["description"]:
                    description = cached["description"]
                    print(f"  ✓ Cached: {title}")
                else:
                    description = self._extract_description(show_attrs)

                if instances:
                    # Each instance is a specific performance with an exact datetime
                    for instance in instances:
                        formatted = instance.get("formattedDates", {})
                        iso_str = formatted.get("ISO8601", "")
                        if not iso_str:
                            continue
                        try:
                            start_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                            # Convert to naive local time (EST/EDT assumed)
                            start_dt = start_dt.replace(tzinfo=None)
                        except ValueError:
                            continue

                        if start_dt.date() < today or start_dt.date() > end_date:
                            continue

                        sold_out = instance.get("soldOut", False)
                        display_title = f"{title} (SOLD OUT)" if sold_out else title

                        show_id = store.upsert_show(
                            url=show_url,
                            title=title,
                            venue=venue,
                            source="secondcity",
                            description=description or None,
                            is_class_show=class_show,
                            show_format=show_fmt,
                        )
                        store.upsert_occurrence(show_id, start_dt.isoformat())

                        events.append(Event(
                            title=display_title,
                            venue=venue,
                            start_time=start_dt,
                            description=description,
                            url=show_url,
                            source="secondcity",
                            is_class_show=class_show,
                            show_format=show_fmt,
                        ))
                else:
                    # Fall back to the dates field (YYYYMMDD strings, no time)
                    date_strings = self._parse_dates_field(show.get("dates"))
                    for date_str in date_strings:
                        try:
                            event_date = datetime.strptime(date_str, "%Y%m%d")
                        except ValueError:
                            continue

                        if event_date.date() < today or event_date.date() > end_date:
                            continue

                        show_id = store.upsert_show(
                            url=show_url,
                            title=title,
                            venue=venue,
                            source="secondcity",
                            description=description or None,
                            is_class_show=class_show,
                            show_format=show_fmt,
                        )
                        store.upsert_occurrence(show_id, event_date.isoformat())

                        events.append(Event(
                            title=title,
                            venue=venue,
                            start_time=event_date,
                            description=description,
                            url=show_url,
                            source="secondcity",
                            is_class_show=class_show,
                            show_format=show_fmt,
                        ))

        except Exception as e:
            print(f"Error fetching Second City events: {e}")

        return events
