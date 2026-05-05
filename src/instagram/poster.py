"""Post a pre-generated image to Instagram via the Graph API.

Environment variables required:
  INSTAGRAM_ACCESS_TOKEN  — long-lived page access token
  INSTAGRAM_ACCOUNT_ID    — numeric Instagram Business account ID
"""

from __future__ import annotations

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://graph.facebook.com/v22.0"


def post_to_instagram(image_url: str, caption: str) -> str:
    """Upload image_url and publish to the configured Instagram account.

    image_url must be publicly accessible (https).
    Returns the published media ID.
    """
    token      = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]

    # Step 1 — create a media container
    resp = requests.post(
        f"{_BASE}/{account_id}/media",
        params={
            "image_url":    image_url,
            "caption":      caption,
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Instagram media container error {resp.status_code}: {resp.text}")

    container_id = resp.json()["id"]
    print(f"  📦 Container created: {container_id}")

    # Brief pause — Meta recommends waiting before publishing
    time.sleep(5)

    # Step 2 — publish the container
    resp = requests.post(
        f"{_BASE}/{account_id}/media_publish",
        params={
            "creation_id":  container_id,
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Instagram publish error {resp.status_code}: {resp.text}")

    media_id = resp.json()["id"]
    print(f"  ✅ Posted to Instagram: {media_id}")
    return media_id
