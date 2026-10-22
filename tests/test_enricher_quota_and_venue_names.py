"""Enricher stays off curation's Gemini quota; BCC venue names have no BOM.

Gemini is mocked and no pages are fetched; no network or API key needed.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from bs4 import BeautifulSoup

from src.agents import performer_enricher
from src.config import ENRICHER_MODEL, GEMINI_MODEL
from src.scrapers.bcc import BccScraper


class _RecordingModels:
    def __init__(self):
        self.models = []

    def generate_content(self, model, contents, config=None):
        self.models.append(model)
        return SimpleNamespace(text='{"ig_handle": "@x", "confidence": "high", "venue_profiles": []}')


def test_enricher_uses_its_own_model(monkeypatch):
    models = _RecordingModels()
    monkeypatch.setattr(performer_enricher, "_client", SimpleNamespace(models=models))

    data = performer_enricher._search_profiles("Jane Improviser")

    assert data["ig_handle"] == "@x"
    assert models.models == [ENRICHER_MODEL]
    # Free-tier quota is per model: the enricher must not share curation's primary model.
    assert ENRICHER_MODEL != GEMINI_MODEL


def test_bcc_venue_strips_bom_from_jsonld_location():
    soup = BeautifulSoup("<html></html>", "html.parser")
    entry = {"location": {"name": "T\ufeffhe BCC  Pig\u200b Pen \n"}}

    venue = BccScraper._extract_venue(soup, entry)

    assert venue == "BCC The BCC Pig Pen"
    assert "\ufeff" not in venue


def test_bcc_venue_strips_leading_bom_and_keeps_bcc_prefix():
    soup = BeautifulSoup("<html></html>", "html.parser")
    entry = {"location": {"name": "\ufeffBCC Main Stage"}}

    assert BccScraper._extract_venue(soup, entry) == "BCC Main Stage"


def test_bcc_venue_strips_bom_from_category_tag():
    soup = BeautifulSoup(
        '<a class="eventlist-cat" href="#">\ufeffPig\ufeff   Pen</a>', "html.parser"
    )

    venue = BccScraper._extract_venue(soup, {})

    assert venue == "BCC Pig Pen"
    assert "\ufeff" not in venue
