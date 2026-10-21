"""Curation hardening: retries, model fallback, deterministic listing, fail closed.

Gemini is mocked; no network or API key needed.
"""
import os
from datetime import datetime
from types import SimpleNamespace

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import pytest
from google.genai import errors

from src.agents import summarizer
from src.config import GEMINI_FALLBACK_MODEL, GEMINI_MODEL
from src.models import Event

GOOD_JSON = (
    '{"days": [{"date_iso": "2026-10-22", "label": "Thursday, October 22", "emoji": "🎭",'
    ' "shows": [{"time": "7:00 PM", "venue": "UCB", "title": "ASSSSCAT", "url": "https://x",'
    ' "starred": true, "details": "Classic."}]}]}'
)
TRUNCATED_JSON = '{"days": [{"date_iso": "2026-10-22", "label": "Thursday, Oct'


def _events():
    return [
        Event(title="Late Show", venue="The PIT", start_time=datetime(2026, 10, 23, 21, 30),
              description="", url="https://pit/late", source="pit"),
        Event(title="ASSSSCAT", venue="UCB", start_time=datetime(2026, 10, 22, 19, 0),
              description="", url="https://ucb/asssscat", source="ucb"),
        Event(title="Armando", venue="Magnet", start_time=datetime(2026, 10, 22, 19, 0),
              description="", url="https://magnet/armando", source="magnet"),
    ]


def _resp(text):
    return SimpleNamespace(text=text, parsed=None)


def _api_error(code, status):
    return errors.APIError(code, {"error": {"code": code, "message": status, "status": status}})


class FakeModels:
    """Returns/raises the scripted outcomes in order, recording the model per call."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models = []
        self.configs = []

    def generate_content(self, model, contents, config):
        self.models.append(model)
        self.configs.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _resp(outcome)


@pytest.fixture
def fake(monkeypatch):
    sleeps = []
    monkeypatch.setattr(summarizer, "_sleep", sleeps.append)

    def install(outcomes):
        models = FakeModels(outcomes)
        monkeypatch.setattr(summarizer, "client", SimpleNamespace(models=models))
        models.sleeps = sleeps
        return models

    return install


def _curate(events=None):
    return summarizer.curate_events_json(_events() if events is None else events,
                                         days=7, date_range="Oct 22 – Oct 28, 2026")


def test_429_then_success(fake):
    models = fake([_api_error(429, "RESOURCE_EXHAUSTED"), GOOD_JSON])
    out = _curate()
    assert out["days"][0]["shows"][0]["title"] == "ASSSSCAT"
    assert "fallback" not in out
    assert models.models == [GEMINI_MODEL, GEMINI_MODEL]
    assert models.sleeps == [summarizer._RETRY_WAITS[0]]


def test_thinking_budget_and_max_output_are_bounded(fake):
    models = fake([GOOD_JSON])
    _curate()
    cfg = models.configs[0]
    assert cfg["thinking_config"]["thinking_budget"] < cfg["max_output_tokens"]


def test_quota_exhausted_on_primary_uses_fallback_model(fake):
    models = fake([_api_error(429, "RESOURCE_EXHAUSTED")] * 3 + [GOOD_JSON])
    out = _curate()
    assert _show_count(out) == 1 and "fallback" not in out
    assert models.models == [GEMINI_MODEL] * 3 + [GEMINI_FALLBACK_MODEL]
    # Total wait is bounded: two backoffs on the primary only.
    assert sum(models.sleeps) == sum(summarizer._RETRY_WAITS)


def test_non_retryable_error_skips_straight_to_next_model(fake):
    models = fake([_api_error(404, "NOT_FOUND"), GOOD_JSON])
    _curate()
    assert models.models == [GEMINI_MODEL, GEMINI_FALLBACK_MODEL]
    assert models.sleeps == []


def test_truncated_json_falls_back_to_deterministic_listing(fake):
    fake([TRUNCATED_JSON, TRUNCATED_JSON])
    out = _curate()
    assert out["fallback"] is True
    assert [d["date_iso"] for d in out["days"]] == ["2026-10-22", "2026-10-23"]
    # Within a day: by time, then venue.
    assert [s["venue"] for s in out["days"][0]["shows"]] == ["Magnet", "UCB"]
    assert out["days"][0]["shows"][0]["time"] == "7:00 PM"
    assert out["days"][0]["label"] == "Thursday, October 22"
    assert _show_count(out) == 3


def test_empty_curation_from_both_models_uses_listing(fake):
    fake(['{"days": []}', '{"days": []}'])
    out = _curate()
    assert out["fallback"] is True and _show_count(out) == 3


def test_all_retries_exhausted_uses_listing(fake):
    models = fake([_api_error(503, "UNAVAILABLE")] * 6)
    out = _curate()
    assert out["fallback"] is True and _show_count(out) == 3
    assert len(models.models) == 6
    assert sum(models.sleeps) == 2 * sum(summarizer._RETRY_WAITS)


def test_empty_fails_closed_when_nothing_to_list(fake):
    # No events -> no Gemini call and an empty result.
    models = fake([])
    assert _curate(events=[]) == {"days": []}
    assert models.models == []
    # Events with no dates can't be listed: curation empty + nothing to fall back to.
    undated = [Event(title="TBD", venue="UCB", start_time=None, description="",
                     url="", source="ucb")]
    fake(['{"days": []}', '{"days": []}'])
    out = _curate(events=undated)
    assert out == {"days": []}  # show_count 0 -> generate_newsletter exits 1 (PR #20)


def _show_count(curated):
    return sum(len(d["shows"]) for d in curated["days"])
