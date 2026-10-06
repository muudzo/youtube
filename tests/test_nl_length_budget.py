"""Deterministic length control for Dutch scripts.

Prompt-level word limits do not hold: asking for 149-193 words per section
returned 406. Runtime matters because under 8 minutes YouTube serves no
mid-rolls at all, and much over ~12 minutes retention collapses on a faceless
channel. So the budget is enforced after generation, not requested before it.
"""

from scripts.nl.script_generator import trim_sections_to_budget


def _words(text: str) -> int:
    return len(text.split())


def test_leaves_sections_already_within_budget_untouched() -> None:
    # Arrange
    sections = [{"narration": "Een zin. Nog een zin.", "visual_keywords": ["sea"]}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=50)

    # Assert
    assert trimmed == sections


def test_trims_overlong_section_to_word_ceiling() -> None:
    # Arrange
    sentence = "Woord " + " ".join(["woord"] * 18) + "."
    sections = [{"narration": " ".join([sentence] * 10)}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=60)

    # Assert
    assert _words(trimmed[0]["narration"]) <= 60


def test_cuts_only_at_sentence_boundaries() -> None:
    # Arrange
    sections = [{"narration": "Eerste zin hier. Tweede zin hier. Derde zin hier."}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=7)

    # Assert
    assert trimmed[0]["narration"] == "Eerste zin hier. Tweede zin hier."


def test_keeps_first_sentence_even_when_it_alone_exceeds_ceiling() -> None:
    # Arrange
    sections = [{"narration": " ".join(["woord"] * 40) + ". Tweede zin."}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=10)

    # Assert
    assert _words(trimmed[0]["narration"]) == 40


def test_preserves_non_narration_fields() -> None:
    # Arrange
    sections = [{
        "narration": "Eerste zin. " * 30,
        "visual_keywords": ["storm surge barrier"],
        "title": "De kering",
    }]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=10)

    # Assert
    assert trimmed[0]["visual_keywords"] == ["storm surge barrier"]
    assert trimmed[0]["title"] == "De kering"


def test_does_not_mutate_the_input() -> None:
    # Arrange
    original = "Eerste zin. Tweede zin. Derde zin."
    sections = [{"narration": original}]

    # Act
    trim_sections_to_budget(sections, ceiling=4)

    # Assert
    assert sections[0]["narration"] == original


def test_handles_abbreviations_without_splitting_mid_sentence() -> None:
    # Arrange
    sections = [{"narration": "De kering bij Rotterdam is ca. 22 meter hoog en zwaar. Klaar."}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=11)

    # Assert
    assert trimmed[0]["narration"] == "De kering bij Rotterdam is ca. 22 meter hoog en zwaar."


def test_handles_question_and_exclamation_boundaries() -> None:
    # Arrange
    sections = [{"narration": "Werkt het echt? Ja, meestal wel! Maar niet altijd."}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=6)

    # Assert
    assert trimmed[0]["narration"] == "Werkt het echt? Ja, meestal wel!"


def test_empty_narration_survives() -> None:
    # Arrange
    sections = [{"narration": ""}]

    # Act
    trimmed = trim_sections_to_budget(sections, ceiling=10)

    # Assert
    assert trimmed[0]["narration"] == ""
