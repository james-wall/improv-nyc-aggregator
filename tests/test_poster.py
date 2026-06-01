"""Tests for the Instagram carousel poster (src/instagram/poster.py).

The HTTP layer is mocked so we assert the exact request shapes the Instagram
content-publishing API expects (host, version, 3-step carousel flow) without
hitting the network.
"""

import json

import pytest

import src.instagram.poster as poster


class _Resp:
    def __init__(self, payload, ok=True, status_code=200):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def ig_env(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "TEST_TOKEN")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "999")
    monkeypatch.delenv("INSTAGRAM_API_VERSION", raising=False)


def _install_fakes(monkeypatch, post_calls, get_calls, status="FINISHED"):
    child_ids = iter([f"child{i}" for i in range(1, 50)])

    def fake_post(url, data=None, params=None, timeout=None):
        body = data or params or {}
        post_calls.append({"url": url, "data": body})
        if url.endswith("/media"):
            if body.get("media_type") == "CAROUSEL":
                return _Resp({"id": "CAROUSEL_ID"})
            return _Resp({"id": next(child_ids)})
        if url.endswith("/media_publish"):
            return _Resp({"id": "PUBLISHED_ID"})
        return _Resp({}, ok=False, status_code=400)

    def fake_get(url, params=None, timeout=None):
        get_calls.append({"url": url, "params": params})
        return _Resp({"status_code": status})

    monkeypatch.setattr(poster.requests, "post", fake_post)
    monkeypatch.setattr(poster.requests, "get", fake_get)


def test_post_carousel_uses_instagram_login_host_and_version(ig_env, monkeypatch):
    post_calls, get_calls = [], []
    _install_fakes(monkeypatch, post_calls, get_calls)

    media_id = poster.post_carousel(
        ["https://x/img1.jpg", "https://x/img2.jpg", "https://x/img3.jpg"],
        "hello world",
    )

    assert media_id == "PUBLISHED_ID"
    # Every call must hit graph.instagram.com at v25.0 — NOT graph.facebook.com.
    for c in post_calls:
        assert c["url"].startswith("https://graph.instagram.com/v25.0/999/")
        assert "graph.facebook.com" not in c["url"]
    # 3 children + 1 carousel container + 1 publish = 5 POSTs.
    assert len(post_calls) == 5

    children = [c for c in post_calls if c["url"].endswith("/media") and c["data"].get("is_carousel_item")]
    assert len(children) == 3

    carousel = [c for c in post_calls if c["data"].get("media_type") == "CAROUSEL"]
    assert len(carousel) == 1
    assert carousel[0]["data"]["children"] == "child1,child2,child3"
    assert carousel[0]["data"]["caption"] == "hello world"

    publish = [c for c in post_calls if c["url"].endswith("/media_publish")]
    assert publish[0]["data"]["creation_id"] == "CAROUSEL_ID"

    # Status is polled before publishing (not a blind sleep).
    assert get_calls and get_calls[0]["params"]["fields"] == "status_code"


def test_dry_run_skips_publish(ig_env, monkeypatch):
    post_calls, get_calls = [], []
    _install_fakes(monkeypatch, post_calls, get_calls)

    cid = poster.post_carousel(["https://x/a.jpg", "https://x/b.jpg"], "cap", dry_run=True)

    assert cid == "CAROUSEL_ID"
    assert not any(c["url"].endswith("/media_publish") for c in post_calls)


def test_api_version_is_env_configurable(ig_env, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_API_VERSION", "v26.0")
    post_calls, get_calls = [], []
    _install_fakes(monkeypatch, post_calls, get_calls)

    poster.post_carousel(["https://x/a.jpg", "https://x/b.jpg"], "cap", dry_run=True)

    assert post_calls and all("/v26.0/" in c["url"] for c in post_calls)


def test_carousel_rejects_too_few_or_too_many_images(ig_env):
    with pytest.raises(ValueError):
        poster.post_carousel(["https://x/a.jpg"], "cap")
    with pytest.raises(ValueError):
        poster.post_carousel([f"https://x/{i}.jpg" for i in range(11)], "cap")


def test_error_response_raises(ig_env, monkeypatch):
    def fake_post(url, data=None, params=None, timeout=None):
        return _Resp({"error": {"message": "bad image"}}, ok=False, status_code=400)

    monkeypatch.setattr(poster.requests, "post", fake_post)
    with pytest.raises(RuntimeError):
        poster.post_carousel(["https://x/a.jpg", "https://x/b.jpg"], "cap")
