"""Tests for Dutch fact research.

Research is best-effort by design: a Wikipedia outage must degrade script
quality, never kill a production run.
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl import research


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _wiki_stub(title="Watersnood van 1953", extract="Feiten over de ramp."):
    """Two-call stub: search, then extract."""
    calls = {"n": 0}

    def get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if params.get("list") == "search":
            return _Response({"query": {"search": [{"title": title}]}})
        return _Response({"query": {"pages": {"1": {"extract": extract}}}})

    return get


def test_returns_the_dutch_article_with_a_source_label(monkeypatch):
    monkeypatch.setattr(research.requests, "get", _wiki_stub())

    brief = research._wiki_search("Watersnoodramp", "nl")

    assert "BRON: Wikipedia NL — Watersnood van 1953" in brief
    assert "Feiten over de ramp." in brief


def test_english_article_is_labelled_separately(monkeypatch):
    monkeypatch.setattr(research.requests, "get", _wiki_stub())

    assert "BRON: Wikipedia EN" in research._wiki_search("North Sea flood", "en")


def test_extract_is_truncated_to_fit_the_model_context(monkeypatch):
    monkeypatch.setattr(research.requests, "get", _wiki_stub(extract="x" * 99_999))

    brief = research._wiki_search("iets", "nl")

    assert len(brief) < 4_000


def test_no_search_results_yields_empty(monkeypatch):
    monkeypatch.setattr(
        research.requests, "get",
        lambda *a, **kw: _Response({"query": {"search": []}}),
    )

    assert research._wiki_search("onvindbaar", "nl") == ""


def test_network_failure_degrades_instead_of_raising(monkeypatch):
    def boom(*a, **kw):
        raise requests.RequestException("wikipedia down")

    monkeypatch.setattr(research.requests, "get", boom)

    assert research._wiki_search("iets", "nl") == ""


def test_research_combines_both_languages(monkeypatch):
    monkeypatch.setattr(research, "_wiki_search",
                        lambda topic, lang: f"BRON {lang.upper()}")

    brief = research.research_topic_nl("Watersnoodramp")

    assert "BRON NL" in brief and "BRON EN" in brief


def test_research_returns_empty_when_every_source_fails(monkeypatch):
    monkeypatch.setattr(research, "_wiki_search", lambda topic, lang: "")

    assert research.research_topic_nl("onvindbaar") == ""
