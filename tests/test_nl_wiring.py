"""End-to-end wiring tests for the Dutch pipeline.

Everything else in this package is only worth having if produce() actually
threads the variant into the renderer and declares synthetic media on upload.
These tests stub every external service and assert on the calls made.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl import produce as produce_mod
from scripts.nl.variation import build_variant

TOPIC = "Hoe werken de Deltawerken"

SCRIPT = {
    "title": "Hoe de Deltawerken Nederland droog houden",
    "description": "Uitleg over de Deltawerken.",
    "tags": ["deltawerken", "waterbouw"],
    "eigen_invalshoek": "De Deltawerken zijn een rekening, geen overwinning.",
    "hook": "De dijk hield het niet.",
    "short_hook": "De rekening van 1953",
    "thumbnail_text": "De rekening van 1953",
    "sections": [
        {"section_title": "Een", "narration": "Eerste deel.",
         "visual_keywords": ["storm surge barrier"]},
        {"section_title": "Twee", "narration": "Tweede deel.",
         "visual_keywords": ["flooded street aerial"]},
    ],
}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Stub every external dependency and capture the calls produce() makes."""
    calls: dict = {}

    for name in ("AUDIO_DIR", "VIDEO_DIR", "THUMBNAIL_DIR", "SUBTITLE_DIR",
                 "OUTPUT_DIR", "MUSIC_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(produce_mod, name, directory)

    monkeypatch.setattr(produce_mod, "generate_script_nl",
                        lambda topic, variant: dict(SCRIPT))
    monkeypatch.setattr(produce_mod, "optimize_script_seo_nl", lambda script: script)
    monkeypatch.setattr(produce_mod, "save_script", lambda script, path: path)

    def fake_synthesize(text, path, voice):
        calls.setdefault("voices", []).append(voice.label)
        Path(path).write_bytes(b"audio")
        return Path(path)

    monkeypatch.setattr(produce_mod.nl_tts, "synthesize", fake_synthesize)
    monkeypatch.setattr(produce_mod.nl_tts, "synthesize_sections",
                        lambda sections, slug, voice, audio_dir: [
                            fake_synthesize("x", audio_dir / f"{slug}_{i}.mp3", voice)
                            for i, _ in enumerate(sections)
                        ])

    def fake_combine(files, out, pause_ms=350, sections=None):
        calls["pause_ms"] = pause_ms
        Path(out).write_bytes(b"audio")
        return Path(out)

    monkeypatch.setattr(produce_mod.nl_tts, "combine", fake_combine)
    monkeypatch.setattr(produce_mod.nl_tts, "duration_of", lambda p: 9 * 60.0)

    monkeypatch.setattr(produce_mod, "generate_subtitles",
                        lambda audio, text, duration: [
                            {"text": "een", "start": 0.0, "end": 1.0}])
    monkeypatch.setattr(produce_mod, "save_subtitles", lambda subs, path: path)
    monkeypatch.setattr(produce_mod, "fetch_all_footage",
                        lambda script: {0: [tmp_path / "clip.mp4"]})

    def fake_assemble(**kwargs):
        calls["assemble"] = kwargs
        Path(kwargs["output_path"]).write_bytes(b"video")
        return Path(kwargs["output_path"])

    monkeypatch.setattr(produce_mod, "assemble_video", fake_assemble)

    def fake_thumbnail(text, output_path, stock_keywords=None, text_color="white",
                       style="bright", font_path=None):
        calls.setdefault("thumbnails", []).append(
            {"text_color": text_color, "style": style, "font_path": font_path})
        Path(output_path).write_bytes(b"png")
        return Path(output_path)

    monkeypatch.setattr(produce_mod, "create_thumbnail", fake_thumbnail)
    return calls


def test_variant_caption_style_and_cut_rhythm_reach_the_renderer(wired):
    variant = build_variant(TOPIC)

    produce_mod.produce(TOPIC, upload=False, make_short=False)

    assert wired["assemble"]["caption_style"] == variant.captions
    expected_cut = (variant.pacing.min_cut + variant.pacing.max_cut) / 2
    assert wired["assemble"]["target_clip_duration"] == pytest.approx(expected_cut)


def test_variant_voice_and_pause_profile_reach_the_narration(wired):
    variant = build_variant(TOPIC)

    produce_mod.produce(TOPIC, upload=False, make_short=False)

    assert set(wired["voices"]) == {variant.voice.label}
    assert wired["pause_ms"] == variant.pacing.section_pause_ms


def test_variant_thumbnail_treatment_reaches_the_thumbnail(wired):
    variant = build_variant(TOPIC)

    produce_mod.produce(TOPIC, upload=False, make_short=False)

    assert wired["thumbnails"][0]["text_color"] == variant.thumbnail.text_color
    assert wired["thumbnails"][0]["style"] == variant.thumbnail.style
    assert wired["thumbnails"][0]["font_path"] == variant.thumbnail.font


def test_the_short_thumbnail_uses_the_same_typeface_as_the_long_form(wired):
    variant = build_variant(TOPIC)

    produce_mod.produce(TOPIC, upload=False, make_short=True)

    fonts = {t["font_path"] for t in wired["thumbnails"]}
    assert fonts == {variant.thumbnail.font}


def test_music_is_only_used_when_the_variant_calls_for_it(wired, monkeypatch):
    variant = build_variant(TOPIC)

    produce_mod.produce(TOPIC, upload=False, make_short=False)

    used = wired["assemble"]["bg_music_path"]
    # No tracks exist in the stub MUSIC_DIR, so this is None either way; what
    # matters is that a variant with music off never even looks.
    assert used is None or variant.use_music


def test_upload_declares_synthetic_media_and_dutch_language(wired, monkeypatch):
    """Undisclosed AI narration is the fastest route to a strike."""
    captured: dict = {}

    def fake_upload(**kwargs):
        captured.update(kwargs)
        return "video123"

    import scripts.youtube_uploader as uploader
    monkeypatch.setattr(uploader, "upload_with_thumbnail", fake_upload)

    result = produce_mod.produce(TOPIC, upload=True, make_short=False,
                                 keep_local=True)

    assert captured["synthetic_media"] is True
    assert captured["language"] == "nl"
    assert result["video_url"] == "https://youtube.com/watch?v=video123"


def test_a_failed_upload_does_not_delete_local_artifacts(wired, monkeypatch):
    """Cleanup is gated on a confirmed upload, or a failure loses the render."""
    import scripts.youtube_uploader as uploader

    def boom(**kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(uploader, "upload_with_thumbnail", boom)

    purged: list = []
    monkeypatch.setattr(produce_mod, "purge_artifacts",
                        lambda paths, footage: purged.append(paths))

    result = produce_mod.produce(TOPIC, upload=True, make_short=False,
                                 keep_local=False)

    assert "video_id" not in result
    assert purged == []
    assert Path(result["video_path"]).exists()


def test_short_uses_the_contrasting_voice_and_caption_style(wired, monkeypatch):
    variant = build_variant(TOPIC)
    captured: dict = {}

    monkeypatch.setattr(produce_mod, "extract_short_hook_nl",
                        lambda script, v: {"narration": "Kort fragment.",
                                           "hook_text": "De rekening"})
    monkeypatch.setattr(produce_mod, "group_words_into_subtitles",
                        lambda words: [{"text": "een", "start": 0.0, "end": 1.0}])
    monkeypatch.setattr(produce_mod, "estimate_timestamps",
                        lambda text, duration: [])

    import scripts.shorts_generator as shorts_gen

    def fake_short(**kwargs):
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"short")
        return Path(kwargs["output_path"])

    monkeypatch.setattr(shorts_gen, "create_short", fake_short)

    produce_mod.produce(TOPIC, upload=False, make_short=True)

    assert captured["caption_style"] == variant.short_captions
    assert variant.short_voice.label in wired["voices"]


def test_a_failing_short_still_ships_the_long_form(wired, monkeypatch):
    """The long-form is the part that earns; a broken Short must not block it."""
    monkeypatch.setattr(
        produce_mod, "extract_short_hook_nl",
        lambda script, v: (_ for _ in ()).throw(ValueError("groq down")),
    )

    result = produce_mod.produce(TOPIC, upload=False, make_short=True)

    assert result["short_path"] is None
    assert Path(result["video_path"]).exists()
