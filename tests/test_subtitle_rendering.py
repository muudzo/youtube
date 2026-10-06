"""Regression tests for subtitle clip construction.

SUBTITLE_BG_COLOR was "rgba(0,0,0,0.6)". Pillow's rgba() specifier requires an
integer alpha (0-255), so it raised, create_subtitle_clips swallowed the
exception, and every boxed subtitle was dropped — long-form videos and Shorts
both rendered with no captions and no error. These tests fail loudly if the
colour literals stop being renderable.
"""

import sys
from pathlib import Path

import pytest
from PIL import ImageColor

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SUBTITLE_BG_COLOR
from scripts.nl.variation import CAPTION_STYLES
from scripts.video_assembler import create_subtitle_clips

SUBTITLES = [{"text": "de deltawerken zijn een rekening", "start": 0.0, "end": 4.0}]
SIZE = (1920, 1080)


def test_configured_subtitle_background_is_a_colour_pillow_accepts():
    assert ImageColor.getrgb(SUBTITLE_BG_COLOR)


def test_shorts_subtitle_background_is_a_colour_pillow_accepts():
    """The Shorts renderer carries its own literal; it broke the same way."""
    source = Path(__file__).parent.parent / "scripts" / "shorts_generator.py"
    literals = [
        line.split('"')[1]
        for line in source.read_text().splitlines()
        if "cap_bg =" in line and "rgba(" in line
    ]

    assert literals, "expected a cap_bg rgba literal in shorts_generator"
    for literal in literals:
        assert ImageColor.getrgb(literal)


def test_english_pipeline_default_still_produces_a_subtitle_clip():
    assert len(create_subtitle_clips(SUBTITLES, video_size=SIZE)) == 1


@pytest.mark.parametrize("style", CAPTION_STYLES, ids=lambda s: s.name)
def test_every_dutch_caption_style_produces_a_clip(style):
    assert len(create_subtitle_clips(SUBTITLES, video_size=SIZE, style=style)) == 1


def test_boxed_styles_are_actually_exercised():
    """Guards the test above from passing vacuously if box is never True."""
    assert any(s.box for s in CAPTION_STYLES)
    assert any(not s.box for s in CAPTION_STYLES)


def test_zero_length_subtitles_are_skipped():
    degenerate = [{"text": "x", "start": 2.0, "end": 2.0}]

    assert create_subtitle_clips(degenerate, video_size=SIZE) == []


# ── caption box sizing ─────────────────────────────────
# MoviePy's method="caption" with size=(W, None) returns a bitmap marginally
# SHORTER than the font size, so glyphs were cut off inside their own clip.

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def test_caption_box_is_taller_than_the_font_size():
    from scripts.video_assembler import caption_box_size

    _, height = caption_box_size("OP HET WATER", FONT, 85, 4, 1620)

    assert height > 85


def test_caption_box_grows_for_text_that_wraps():
    from scripts.video_assembler import caption_box_size

    _, short = caption_box_size("KORT", FONT, 85, 4, 1620)
    _, long = caption_box_size(
        "DE DELTAWERKEN ZIJN GEEN OVERWINNING OP HET WATER MAAR EEN REKENING",
        FONT, 85, 4, 1620,
    )

    assert long > short


def test_caption_box_keeps_the_requested_width():
    from scripts.video_assembler import caption_box_size

    width, _ = caption_box_size("OP HET WATER", FONT, 85, 4, 1620)

    assert width == 1620


def test_caption_box_scales_with_font_size():
    from scripts.video_assembler import caption_box_size

    _, small = caption_box_size("OP HET WATER", FONT, 78, 3, 1620)
    _, large = caption_box_size("OP HET WATER", FONT, 100, 6, 1620)

    assert large > small
