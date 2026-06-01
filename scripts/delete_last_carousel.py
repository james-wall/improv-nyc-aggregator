#!/usr/bin/env python3
"""Delete the most recently published Instagram carousel post.

Reads INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID from environment.
Run via the 'cleanup' workflow mode or directly when those env vars are set.
"""

import os
import sys

import requests

TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
ACCOUNT_ID = os.environ["INSTAGRAM_ACCOUNT_ID"]
BASE = "https://graph.instagram.com/v25.0"


def main() -> None:
    resp = requests.get(
        f"{BASE}/{ACCOUNT_ID}/media",
        params={
            "fields": "id,media_type,timestamp,caption",
            "limit": 20,
            "access_token": TOKEN,
        },
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])

    if not data:
        print("No media found on the account.")
        return

    carousel = next((m for m in data if m.get("media_type") == "CAROUSEL_ALBUM"), None)
    if not carousel:
        print("No carousel posts found — nothing to delete.")
        return

    media_id = carousel["id"]
    ts = carousel.get("timestamp", "unknown")
    cap = (carousel.get("caption") or "")[:80]
    print(f"Found carousel: id={media_id}  posted={ts}")
    print(f"  Caption preview: {cap!r}")

    del_resp = requests.delete(
        f"{BASE}/{media_id}",
        params={"access_token": TOKEN},
    )
    del_resp.raise_for_status()
    result = del_resp.json()

    if result.get("success"):
        print(f"Deleted carousel {media_id}")
    else:
        print(f"Unexpected delete response: {result}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
