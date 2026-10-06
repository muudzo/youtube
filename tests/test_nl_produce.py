"""Tests for the Dutch pipeline's guards and helpers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl.produce import UnsafeTopicError, _thumbnail_keywords, produce
from scripts.nl.script_generator import _validate_nl
from scripts.nl.shorts import short_title_nl
from scripts.nl.variation import build_variant


def test_unsafe_topic_is_rejected_before_any_api_call():
    """The gate must fire before Groq, Pexels or the uploader are touched."""
    with pytest.raises(UnsafeTopicError) as excinfo:
        produce("hoe begin ik met beleggen", upload=False)

    assert "financieel" in str(excinfo.value)


def test_thumbnail_keywords_come_from_the_scripts_english_keywords():
    script = {"sections": [
        {"visual_keywords": ["storm surge barrier", "flooded street"]},
        {"visual_keywords": ["dutch canal houses"]},
    ]}

    assert _thumbnail_keywords(script)[:3] == [
        "storm surge barrier", "flooded street", "dutch canal houses",
    ]


def test_thumbnail_keywords_fall_back_when_the_script_has_none():
    assert _thumbnail_keywords({"sections": []}) == [
        "netherlands landscape", "dutch canal",
    ]


def test_short_title_differs_from_the_long_form_title():
    """Two uploads sharing a title waste a search listing and read as duplicates."""
    script = {"title": "Hoe de Deltawerken Nederland droog houden",
              "thumbnail_text": "De rekening van 1953"}

    assert short_title_nl(script) != script["title"]


def test_short_title_falls_back_to_the_title_when_thumbnail_text_is_thin():
    script = {"title": "Hoe een polder werkt", "thumbnail_text": "Pol"}

    assert short_title_nl(script) == "Hoe een polder werkt"


def test_short_title_respects_youtubes_length_cap():
    script = {"title": "x" * 200, "thumbnail_text": "y" * 200}

    assert len(short_title_nl(script)) <= 90


def test_validation_returns_a_new_dict_and_leaves_the_original_alone():
    original = {"tags": ["de", "Deltawerken"], "description": "12:30 - intro",
                "sections": [], "hook": ""}
    snapshot = dict(original)

    cleaned = _validate_nl(original, build_variant("iets"))

    assert original == snapshot
    assert cleaned is not original


def test_validation_strips_hallucinated_timestamps_from_the_description():
    cleaned = _validate_nl(
        {"description": "10:45 - De doorbraak", "tags": [], "sections": [], "hook": ""},
        build_variant("iets"),
    )

    assert cleaned["description"] == "De doorbraak"


def test_validation_warns_about_a_missing_angle(capsys):
    _validate_nl({"tags": [], "sections": [], "hook": "", "description": ""},
                 build_variant("iets"))

    assert "geen eigen invalshoek" in capsys.readouterr().out


def test_validation_warns_when_visual_keywords_are_dutch(capsys):
    _validate_nl(
        {"tags": [], "hook": "", "description": "",
         "sections": [{"narration": "x", "visual_keywords": ["de dijk"]}]},
        build_variant("iets"),
    )

    assert "Nederlandse visual_keywords" in capsys.readouterr().out
