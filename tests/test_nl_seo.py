"""Tests for Dutch SEO relevance filtering.

These pin a real bug: autocomplete answers whatever prefix it is handed, so
querying "hoe" for the topic "hoe werken de deltawerken" returned "hoe maak je
een squishy" — which then landed in the video's tags and description.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl.seo import (
    DISCLOSURE_NL,
    _content_words,
    _is_relevant,
    _merge_tags,
    build_description_nl,
)


def test_content_words_drop_dutch_function_words():
    assert _content_words("hoe werken de deltawerken") == {"deltawerken"}


def test_content_words_drop_generic_verbs():
    """'werken' is shared by unrelated topics and carries no topical signal."""
    assert "werken" not in _content_words("hoe werken de longen")


def test_unrelated_suggestion_is_rejected():
    topic = _content_words("hoe werken de deltawerken")

    assert not _is_relevant("hoe maak je een squishy", topic)


def test_suggestion_sharing_only_a_generic_verb_is_rejected():
    topic = _content_words("hoe werken de deltawerken")

    assert not _is_relevant("hoe werken de longen", topic)


def test_genuinely_related_suggestion_is_kept():
    topic = _content_words("hoe werken de deltawerken")

    assert _is_relevant("deltawerken documentaire", topic)


def test_rich_topics_require_two_overlapping_words():
    """One shared word is too weak when the topic has several."""
    topic = _content_words("waarom staan amsterdamse huizen scheef")

    assert not _is_relevant("waarom staan amsterdamse psv fan", topic)
    assert _is_relevant("amsterdamse huizen verzakken", topic)


def test_empty_topic_matches_nothing():
    assert not _is_relevant("wat dan ook", set())


def test_description_carries_the_synthetic_media_disclosure():
    """Disclosure is what keeps AI-narrated content monetizable."""
    description = build_description_nl(
        {"description": "Uitleg.", "tags": ["deltawerken"]}, {"related": []}
    )

    assert DISCLOSURE_NL in description


def test_description_states_the_videos_own_angle():
    description = build_description_nl(
        {"description": "Uitleg.",
         "eigen_invalshoek": "De Deltawerken zijn een rekening, geen overwinning.",
         "tags": []},
        {"related": []},
    )

    assert "De Deltawerken zijn een rekening" in description


def test_description_omits_the_angle_line_when_there_is_none():
    description = build_description_nl({"description": "Uitleg.", "tags": []},
                                       {"related": []})

    assert "De stelling van deze video" not in description


def test_merged_tags_respect_youtubes_500_character_budget():
    terms = {"related": [f"nederlandse waterbouw onderwerp {i}" for i in range(60)]}

    tags = _merge_tags(["deltawerken"], terms)

    assert sum(len(t) + 1 for t in tags) <= 500
    assert len(tags) <= 15


def test_merged_tags_deduplicate_case_insensitively():
    tags = _merge_tags(["Deltawerken", "deltawerken"], {"related": ["DELTAWERKEN"]})

    assert len(tags) == 1
