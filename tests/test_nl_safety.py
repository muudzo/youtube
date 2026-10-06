"""Tests for the topic safety gate.

These encode a real incident: a live run of scripts/nl/topics.py ranked
"wat zijn joden" purely on search volume, with nothing downstream to stop it
before upload.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl import safety


def test_blocks_the_identity_topic_that_discovery_actually_surfaced():
    assert safety.classify("wat zijn joden") == "identiteit"


def test_blocks_health_topics_named_by_the_policy():
    for topic in ("symptomen van een burn-out", "welk medicijn helpt tegen pijn"):
        assert safety.classify(topic) == "gezondheid"


def test_blocks_finance_topics_named_by_the_policy():
    for topic in ("hoe beginnen met beleggen", "is crypto nog de moeite waard"):
        assert safety.classify(topic) == "financieel"


def test_allows_ordinary_explainer_topics():
    for topic in (
        "hoe werken de deltawerken",
        "waarom staan amsterdamse huizen scheef",
        "hoe is de nederlandse taal ontstaan",
        "hoe werkt een polder",
    ):
        assert safety.classify(topic) is None, topic


def test_word_boundary_prevents_false_positives():
    """'ras' must not trip on 'terras'; 'wil' must not trip on 'Wilhelmina'."""
    assert safety.classify("het grootste terras van Nederland") is None
    assert safety.classify("koningin Wilhelmina in ballingschap") is None


def test_filter_topics_splits_allowed_from_rejected():
    topics = ["hoe werkt een polder", "wat zijn joden", "hoe werken windmolens"]

    allowed, rejected = safety.filter_topics(topics)

    assert allowed == ["hoe werkt een polder", "hoe werken windmolens"]
    assert rejected == ["wat zijn joden"]


def test_filter_topics_accepts_a_key_extractor():
    rows = [{"q": "hoe werkt een sluis"}, {"q": "beleggen voor beginners"}]

    allowed, rejected = safety.filter_topics(rows, key=lambda r: r["q"])

    assert len(allowed) == 1 and len(rejected) == 1
