"""Post a carousel to Instagram via the Graph API.

Single image flow  → create container → publish
Carousel flow      → create one child container per image
                  → create carousel container (media_type=CAROUSEL)
                  → publish carousel

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


def post_carousel(image_urls: list[str], caption: str) -> str:
    """Upload multiple images and publish as a carousel post.

    image_urls must all be publicly accessible (https).
    Returns the published media ID.
    """
    token      = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]

    # Step 1 — create a child container for each image
    child_ids: list[str] = []
    for i, url in enumerate(image_urls):
        resp = requests.post(
            f"{_BASE}/{account_id}/media",
            params={
                "image_url":        url,
                "is_carousel_item": "true",
                "access_token":     token,
            },
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(
                f"Carousel child {i+1} error {resp.status_code}: {resp.text}"
            )
        child_ids.append(resp.json()["id"])
        print(f"  📷 Child container {i+1}/{len(image_urls)}: {resp.json()['id']}")

    # Step 2 — create the carousel container
    resp = requests.post(
        f"{_BASE}/{account_id}/media",
        params={
            "media_type":   "CAROUSEL",
            "children":     ",".join(child_ids),
            "caption":      caption,
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Carousel container error {resp.status_code}: {resp.text}"
        )
    carousel_id = resp.json()["id"]
    print(f"  📦 Carousel container: {carousel_id}")

    # Brief pause before publishing (Meta recommends this)
    time.sleep(5)

    # Step 3 — publish
    resp = requests.post(
        f"{_BASE}/{account_id}/media_publish",
        params={
            "creation_id":  carousel_id,
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Carousel publish error {resp.status_code}: {resp.text}"
        )
    media_id = resp.json()["id"]
    print(f"  ✅ Posted carousel to Instagram: {media_id}")
    return media_id


def post_to_instagram(image_url: str, caption: str) -> str:
    """Single-image post (kept for compatibility). Prefer post_carousel."""
    return post_carousel([image_url], caption)
