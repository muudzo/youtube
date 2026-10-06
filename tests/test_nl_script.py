"""Tests for Dutch script sanitization, prosody and slugs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl.nl_tts import add_dutch_prosody
from scripts.nl.produce import slugify
from scripts.nl.script_generator import (
    _clean_tags,
    _detect_dutch_keywords,
    full_narration_nl,
)


def test_dutch_visual_keywords_are_flagged():
    """Pexels is English-indexed; a Dutch keyword costs a section its footage."""
    sections = [
        {"visual_keywords": ["flooded street aerial", "de dijk bij nacht"]},
        {"visual_keywords": ["storm surge barrier"]},
    ]

    leaked = _detect_dutch_keywords(sections)

    assert leaked == ["de dijk bij nacht"]


def test_english_keywords_are_not_flagged():
    sections = [{"visual_keywords": ["dutch canal houses", "windmill at sunset"]}]

    assert _detect_dutch_keywords(sections) == []


def test_tags_drop_dutch_stopwords_and_deduplicate():
    tags = ["de", "Deltawerken", "deltawerken", "waterbouw", "het", "Nederland"]

    cleaned = _clean_tags(tags)

    assert cleaned == ["Deltawerken", "waterbouw", "Nederland"]


def test_tags_are_capped_at_fifteen():
    assert len(_clean_tags([f"onderwerp{i}" for i in range(40)])) == 15


def test_tags_preserve_dutch_diacritics():
    assert "café" in _clean_tags(["café", "terras"])


def test_full_narration_joins_hook_and_sections():
    script = {
        "hook": "De dijk hield het.",
        "sections": [{"narration": "Tot 1953."}, {"narration": "Toen niet."}],
    }

    assert full_narration_nl(script) == "De dijk hield het.\n\nTot 1953.\n\nToen niet."


def test_full_narration_skips_empty_sections():
    script = {"hook": "Kort.", "sections": [{"narration": ""}, {"narration": "Wel."}]}

    assert full_narration_nl(script) == "Kort.\n\nWel."


def test_prosody_pauses_before_dutch_pivot_words():
    """The English SSML pass keys on 'But'/'However' and does nothing here."""
    result = add_dutch_prosody("Het ging goed. Maar toen brak de dijk.")

    assert "<break" in result
    assert result.index("<break") < result.index("Maar")


def test_prosody_slows_dutch_absolutes():
    result = add_dutch_prosody("Niemand wist het.")

    assert '<prosody rate="slow">Niemand</prosody>' in result


def test_prosody_beats_before_a_year():
    assert "<break" in add_dutch_prosody("Het gebeurde in 1953 opnieuw.")


def test_prosody_leaves_plain_text_untouched():
    plain = "De sluis gaat open en dicht"

    assert add_dutch_prosody(plain) == plain


def test_slugify_folds_dutch_diacritics():
    assert slugify("Waarom België anders is") == "waarom_belgie_anders_is"


def test_slugify_collapses_punctuation_without_trailing_separators():
    slug = slugify("Hoe werken de Deltawerken?")

    assert slug == "hoe_werken_de_deltawerken"
    assert not slug.endswith("_")


def test_slugify_is_bounded():
    assert len(slugify("woord " * 60)) <= 50
