"""Thumbnail typeface rotates with the variant.

Colour and style already rotate per video, but every thumbnail rendered in the
same typeface, so the set still read as one template at a glance — which is
exactly the surface YouTube's inauthentic-content review looks at.
"""

from pathlib import Path

from scripts.nl.variation import THUMBNAIL_TREATMENTS, build_variant
from scripts.thumbnail_generator import _load_font


def test_every_treatment_declares_a_font() -> None:
    # Arrange / Act
    fonts = [t.font for t in THUMBNAIL_TREATMENTS]

    # Assert
    assert all(fonts), "a treatment with no font falls back to the shared default"


def test_treatments_do_not_share_a_typeface() -> None:
    # Arrange / Act
    fonts = [t.font for t in THUMBNAIL_TREATMENTS]

    # Assert
    assert len(set(fonts)) == len(fonts)


def test_declared_fonts_are_loadable_on_this_machine() -> None:
    # Arrange / Act
    loaded = [_load_font(80, t.font) for t in THUMBNAIL_TREATMENTS]

    # Assert — a silent fallback to the default would defeat the rotation
    for treatment, font in zip(THUMBNAIL_TREATMENTS, loaded):
        assert Path(treatment.font).name.split(".")[0] in font.path, (
            f"{treatment.name} fell back instead of loading {treatment.font}"
        )


def test_load_font_still_falls_back_when_path_is_missing() -> None:
    # Arrange / Act
    font = _load_font(80, "/nonexistent/Fake.ttf")

    # Assert
    assert font is not None


def test_different_topics_can_draw_different_typefaces() -> None:
    # Arrange
    topics = [f"onderwerp nummer {n}" for n in range(40)]

    # Act
    fonts = {build_variant(t).thumbnail.font for t in topics}

    # Assert
    assert len(fonts) > 1
