"""Post a carousel (or single image) to Instagram.

Uses the **Instagram API with Instagram Login** (host ``graph.instagram.com``),
which works for a standalone Instagram *professional* account that has **no
linked Facebook Page** — exactly @ourscenenyc's situation. (The older Instagram
Graph API on ``graph.facebook.com`` requires the account to be connected to a
Facebook Page, which @ourscenenyc is not.)

Carousel flow — https://developers.facebook.com/docs/instagram-platform/content-publishing/ :
  1. create one child container per image  (POST /<IG_ID>/media, is_carousel_item=true)
  2. create the carousel container          (POST /<IG_ID>/media, media_type=CAROUSEL, children=...)
  3. wait until the container status_code is FINISHED
  4. publish                                 (POST /<IG_ID>/media_publish, creation_id=...)

Environment variables:
  INSTAGRAM_ACCESS_TOKEN  — long-lived (60-day) Instagram User access token
  INSTAGRAM_ACCOUNT_ID    — Instagram user id (GET /me?fields=user_id)
  INSTAGRAM_API_VERSION   — optional Graph API version (default "v25.0")

Note: Instagram's publishing API has no private/sandbox post. ``dry_run=True``
runs everything *except* the final publish — it still creates the container,
which exercises the access token, the ``instagram_business_content_publish``
permission and the server-side image fetch — so it validates the whole chain
without making a public post.
"""

from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_API_VERSION = "v25.0"


def _base_url() -> str:
    """graph.instagram.com base; version overridable via env (read at call time)."""
    version = os.getenv("INSTAGRAM_API_VERSION", _DEFAULT_API_VERSION)
    return f"https://graph.instagram.com/{version}"


def _credentials() -> tuple[str, str]:
    try:
        return (
            os.environ["INSTAGRAM_ACCESS_TOKEN"],
            os.environ["INSTAGRAM_ACCOUNT_ID"],
        )
    except KeyError as e:
        raise RuntimeError(f"Missing required Instagram env var: {e}") from e


def _create_container(base: str, account_id: str, token: str, **fields) -> str:
    """POST /<IG_ID>/media and return the new container id."""
    resp = requests.post(
        f"{base}/{account_id}/media",
        data={**fields, "access_token": token},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"media container error {resp.status_code}: {resp.text}")
    return resp.json()["id"]


def _wait_for_container(
    base: str, container_id: str, token: str,
    timeout: int = 60, interval: int = 3,
) -> None:
    """Poll a media container's status_code until FINISHED (raise on ERROR/timeout).

    Replaces a blind sleep: image containers are usually ready immediately, but
    this is robust if Instagram needs a moment to fetch/process the image.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = requests.get(
            f"{base}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        if resp.ok:
            last = resp.json().get("status_code")
            if last == "FINISHED":
                return
            if last == "ERROR":
                raise RuntimeError(
                    f"Container {container_id} failed processing (status ERROR)"
                )
        time.sleep(interval)
    raise RuntimeError(
        f"Container {container_id} not FINISHED within {timeout}s (last status: {last})"
    )


def post_carousel(image_urls: list[str], caption: str, dry_run: bool = False) -> str:
    """Upload multiple JPEG images and publish them as a single carousel post.

    ``image_urls`` must be publicly reachable https URLs to **JPEG** images
    (Instagram rejects PNG). Returns the published media id, or — when
    ``dry_run`` is set — the unpublished carousel container id.
    """
    token, account_id = _credentials()
    base = _base_url()

    if not 2 <= len(image_urls) <= 10:
        raise ValueError(f"A carousel needs 2-10 images; got {len(image_urls)}.")

    # 1 — one child container per image
    child_ids: list[str] = []
    for i, url in enumerate(image_urls):
        cid = _create_container(
            base, account_id, token, image_url=url, is_carousel_item="true"
        )
        child_ids.append(cid)
        print(f"  📷 Child container {i + 1}/{len(image_urls)}: {cid}")

    # 2 — the carousel parent container
    carousel_id = _create_container(
        base, account_id, token,
        media_type="CAROUSEL",
        children=",".join(child_ids),
        caption=caption,
    )
    print(f"  📦 Carousel container: {carousel_id}")

    # 3 — wait until Instagram has finished assembling the container
    _wait_for_container(base, carousel_id, token)

    if dry_run:
        print(f"  🧪 DRY RUN — container {carousel_id} ready; skipping publish.")
        return carousel_id

    # 4 — publish
    resp = requests.post(
        f"{base}/{account_id}/media_publish",
        data={"creation_id": carousel_id, "access_token": token},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Carousel publish error {resp.status_code}: {resp.text}")
    media_id = resp.json()["id"]
    print(f"  ✅ Posted carousel to Instagram: {media_id}")
    return media_id


def post_to_instagram(image_url: str, caption: str, dry_run: bool = False) -> str:
    """Publish a single JPEG image (not a carousel). Prefer ``post_carousel``."""
    token, account_id = _credentials()
    base = _base_url()

    container_id = _create_container(
        base, account_id, token, image_url=image_url, caption=caption
    )
    print(f"  📦 Media container: {container_id}")
    _wait_for_container(base, container_id, token)

    if dry_run:
        print(f"  🧪 DRY RUN — container {container_id} ready; skipping publish.")
        return container_id

    resp = requests.post(
        f"{base}/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Publish error {resp.status_code}: {resp.text}")
    media_id = resp.json()["id"]
    print(f"  ✅ Posted image to Instagram: {media_id}")
    return media_id
