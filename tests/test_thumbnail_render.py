"""create_thumbnail must actually render, not just accept its arguments.

A previous change threaded font_path into the public signature but not into the
private overlay helper, so every call raised NameError at render time. The
wiring tests mock create_thumbnail wholesale and the font tests call _load_font
directly, so nothing exercised the real path. These do.
"""

from PIL import Image

from scripts.nl.variation import THUMBNAIL_TREATMENTS
from scripts.thumbnail_generator import create_thumbnail
from config import THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT


def _background(tmp_path):
    path = tmp_path / "bg.png"
    Image.new("RGB", (1280, 720), (40, 60, 90)).save(path)
    return path


def test_renders_a_thumbnail_at_the_configured_size(tmp_path):
    # Arrange
    out = tmp_path / "thumb.png"

    # Act
    result = create_thumbnail(
        text="Deltawerken",
        background_image_path=_background(tmp_path),
        output_path=out,
    )

    # Assert
    assert result.exists()
    assert Image.open(result).size == (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)


def test_renders_with_every_variant_typeface(tmp_path):
    # Arrange / Act / Assert — the NameError only fired on this path
    for treatment in THUMBNAIL_TREATMENTS:
        out = tmp_path / f"{treatment.name}.png"
        result = create_thumbnail(
            text="Waarom de kering faalt",
            background_image_path=_background(tmp_path),
            output_path=out,
            text_color=treatment.text_color,
            style=treatment.style,
            font_path=treatment.font,
        )
        assert result.exists(), f"{treatment.name} produced no file"


def test_different_typefaces_produce_different_pixels(tmp_path):
    # Arrange — if font_path were ignored, these would be byte-identical
    first, second = THUMBNAIL_TREATMENTS[0], THUMBNAIL_TREATMENTS[1]
    bg = _background(tmp_path)

    # Act
    a = create_thumbnail(text="Zelfde tekst", background_image_path=bg,
                         output_path=tmp_path / "a.png", font_path=first.font)
    b = create_thumbnail(text="Zelfde tekst", background_image_path=bg,
                         output_path=tmp_path / "b.png", font_path=second.font)

    # Assert
    assert a.read_bytes() != b.read_bytes()


def test_falls_back_cleanly_when_the_font_is_missing(tmp_path):
    # Arrange / Act
    result = create_thumbnail(
        text="Geen font",
        background_image_path=_background(tmp_path),
        output_path=tmp_path / "fallback.png",
        font_path="/nonexistent/Fake.ttf",
    )

    # Assert
    assert result.exists()


def test_hex_text_colours_are_honoured_not_silently_whitened(tmp_path):
    # Arrange — mint and red treatments both pass hex; a name-only lookup
    # collapsed them to white, killing half the colour rotation.
    bg = _background(tmp_path)

    # Act
    mint = create_thumbnail(text="Kering", background_image_path=bg,
                            output_path=tmp_path / "mint.png", text_color="#9FFFCB")
    white = create_thumbnail(text="Kering", background_image_path=bg,
                             output_path=tmp_path / "white.png", text_color="white")

    # Assert
    assert mint.read_bytes() != white.read_bytes()


def test_every_treatment_colour_renders_distinctly(tmp_path):
    # Arrange
    bg = _background(tmp_path)

    # Act — same typeface throughout, so only colour can differ
    renders = {
        t.name: create_thumbnail(
            text="Zelfde tekst", background_image_path=bg,
            output_path=tmp_path / f"c_{t.name}.png", text_color=t.text_color,
        ).read_bytes()
        for t in THUMBNAIL_TREATMENTS
    }

    # Assert
    assert len(set(renders.values())) == len(THUMBNAIL_TREATMENTS)


def test_unparseable_colour_falls_back_to_white(tmp_path):
    # Arrange / Act
    result = create_thumbnail(
        text="Onzin", background_image_path=_background(tmp_path),
        output_path=tmp_path / "bad.png", text_color="not-a-colour",
    )

    # Assert
    assert result.exists()
