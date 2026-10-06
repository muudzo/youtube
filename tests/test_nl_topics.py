"""Tests for Dutch topic discovery.

The prefix-echo filter is the reason discovery returns usable topics at all:
autocomplete answers a prefix even when the seed matches nothing, so
"wat gebeurde er met wim" came back for all fifteen seeds and outranked every
real topic on fake consensus.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl import topics as nl_topics
from scripts.nl.topics import Topic, _headline_seed, load_seed_topics


def _stub_suggest(mapping, default=()):
    """Build a youtube_suggest_nl replacement from an exact-query mapping."""
    return lambda query: list(mapping.get(query, default))


def test_evergreen_outranks_equally_popular_news():
    evergreen = Topic("hoe werkt een polder", 3, True, "autocomplete")
    news = Topic("hoe werkt een polder", 3, False, "nos")

    assert evergreen.score > news.score


def test_consensus_raises_the_score():
    low = Topic("hoe werken de deltawerken", 1, True, "autocomplete")
    high = Topic("hoe werken de deltawerken", 5, True, "autocomplete")

    assert high.score > low.score


def test_two_word_queries_are_penalised_as_too_broad():
    broad = Topic("de deltawerken", 2, True, "autocomplete")
    specific = Topic("hoe werken de deltawerken precies", 2, True, "autocomplete")

    assert specific.score > broad.score


def test_prefix_echoes_are_excluded_from_consensus(monkeypatch):
    """A completion the bare prefix already returns proves nothing about a seed."""
    echo = "waarom is dat zo"
    real = "waarom is nederland zo plat"
    monkeypatch.setattr(nl_topics, "QUESTION_PREFIXES", ("waarom",))
    monkeypatch.setattr(nl_topics, "EVERGREEN_SEEDS", ("nederland", "het water"))
    monkeypatch.setattr(nl_topics, "youtube_suggest_nl", _stub_suggest(
        {
            "waarom": [echo],
            "waarom nederland": [echo, real],
            "waarom het water": [echo],
        }
    ))

    found = nl_topics.discover_topics_nl(limit=10, include_news=False)

    assert [t.query for t in found] == [real]


def test_unsafe_topics_are_gated_before_ranking(monkeypatch):
    monkeypatch.setattr(nl_topics, "QUESTION_PREFIXES", ("wat",))
    monkeypatch.setattr(nl_topics, "EVERGREEN_SEEDS", ("nederland",))
    monkeypatch.setattr(nl_topics, "youtube_suggest_nl", _stub_suggest(
        {
            "wat": [],
            "wat nederland": ["wat zijn joden", "wat is een polder precies"],
        }
    ))

    found = nl_topics.discover_topics_nl(limit=10, include_news=False)

    assert [t.query for t in found] == ["wat is een polder precies"]


def test_very_short_suggestions_are_discarded(monkeypatch):
    monkeypatch.setattr(nl_topics, "QUESTION_PREFIXES", ("hoe",))
    monkeypatch.setattr(nl_topics, "EVERGREEN_SEEDS", ("nederland",))
    monkeypatch.setattr(nl_topics, "youtube_suggest_nl", _stub_suggest(
        {"hoe": [], "hoe nederland": ["hoe dan", "hoe werkt een sluis precies"]}
    ))

    found = nl_topics.discover_topics_nl(limit=10, include_news=False)

    assert [t.query for t in found] == ["hoe werkt een sluis precies"]


def test_discovery_survives_a_dead_autocomplete(monkeypatch):
    monkeypatch.setattr(nl_topics, "youtube_suggest_nl", lambda q: [])

    assert nl_topics.discover_topics_nl(limit=5, include_news=False) == []


def test_suggest_returns_empty_on_network_failure(monkeypatch):
    import requests

    def boom(*a, **kw):
        raise requests.RequestException("down")

    monkeypatch.setattr(nl_topics.requests, "get", boom)

    assert nl_topics.youtube_suggest_nl("hoe werkt een polder") == []


def test_headline_seed_strips_function_words():
    seed = _headline_seed("Zorgen bij de NAVO over verdere escalatie na droneaanval")

    assert "de" not in seed.split()
    assert len(seed.split()) <= 2


def test_headline_seed_handles_a_headline_of_only_stopwords():
    assert _headline_seed("de het een van") == ""


def test_seed_topics_skip_comments_and_blanks(tmp_path):
    path = tmp_path / "topics_nl.txt"
    path.write_text("# commentaar\n\nHoe werkt een polder\n\n# nog een\nWaarom dijken breken\n")

    assert load_seed_topics(path) == ["Hoe werkt een polder", "Waarom dijken breken"]


def test_seed_topics_missing_file_returns_empty(tmp_path):
    assert load_seed_topics(tmp_path / "nope.txt") == []


def test_shipped_seed_file_is_non_empty_and_entirely_safe():
    """The seed file is the floor when discovery fails; it must never ship an
    unsafe topic."""
    from scripts.nl import safety

    seeds = load_seed_topics()

    assert len(seeds) >= 10
    assert [s for s in seeds if not safety.is_safe(s)] == []
