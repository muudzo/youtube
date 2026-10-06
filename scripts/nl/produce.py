"""
Dutch production pipeline: topic in, uploaded video out.

Mirrors the English pipeline.py, with three structural differences:

- Every stage reads from a VideoVariant, so voice, hook shape, structure,
  captions, cut rhythm and thumbnail treatment differ per video.
- Narration is Dutch; visual keywords stay English because Pexels is indexed
  in English.
- Upload declares synthetic media and tags the video as Dutch, so YouTube
  surfaces it to Dutch viewers rather than inferring from the channel.
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import (
    AUDIO_DIR,
    BASE_DIR,
    NL_TOKEN_FILE,
    KEEP_LOCAL_AFTER_UPLOAD,
    MUSIC_DIR,
    NL_DECLARE_SYNTHETIC_MEDIA,
    NL_LANGUAGE_CODE,
    OUTPUT_DIR,
    SUBTITLE_DIR,
    THUMBNAIL_DIR,
    VIDEO_DIR,
)
from scripts.cleanup import purge_artifacts
from scripts.footage_sourcer import fetch_all_footage
from scripts.nl import nl_tts, safety
from scripts.nl.script_generator import (
    full_narration_nl,
    generate_script_nl,
    save_script,
)
from scripts.nl.seo import optimize_script_seo_nl
from scripts.nl.shorts import extract_short_hook_nl, short_title_nl
from scripts.nl.variation import VideoVariant, build_variant
from scripts.subtitle_generator import (
    estimate_timestamps,
    generate_subtitles,
    group_words_into_subtitles,
    save_subtitles,
)
from scripts.thumbnail_generator import create_thumbnail
from scripts.video_assembler import assemble_video


# Mid-rolls unlock past 8 minutes, and they are the entire revenue case here --
# Shorts RPM is ~$0.02-0.12/1k, which rounds to nothing.
MIN_MIDROLL_SECONDS = 8 * 60


class UnsafeTopicError(ValueError):
    """Raised when a topic is blocked by the safety gate."""


class TooShortToMonetizeError(ValueError):
    """Raised when narration lands under the mid-roll threshold."""


def assert_monetizable(duration_seconds: float) -> None:
    """Raise unless the video is long enough to carry mid-rolls."""
    if duration_seconds < MIN_MIDROLL_SECONDS:
        raise TooShortToMonetizeError(
            f"{duration_seconds / 60:.1f} min ligt onder de midroll-grens van "
            f"{MIN_MIDROLL_SECONDS / 60:.0f} min. Uploaden kost een slot en een "
            f"onderwerp zonder dat de video kan verdienen."
        )


def slugify(text: str) -> str:
    """Filename-safe slug, ASCII-folded so Dutch diacritics don't break paths."""
    folded = (
        text.lower()
        .replace("ë", "e").replace("é", "e").replace("è", "e")
        .replace("ï", "i").replace("í", "i")
        .replace("ö", "o").replace("ó", "o")
        .replace("ü", "u").replace("ú", "u")
        .replace("à", "a").replace("á", "a")
    )
    safe = "".join(c if c.isalnum() else "_" for c in folded)
    return "_".join(filter(None, safe.split("_")))[:50]


def produce(
    topic: str,
    upload: bool = False,
    make_short: bool = True,
    privacy: str = "public",
    schedule: str = None,
    keep_local: bool = None,
    salt: str = "",
) -> dict:
    """Produce one Dutch video (and optionally its Short) from a topic."""
    blocked = safety.classify(topic)
    if blocked:
        raise UnsafeTopicError(
            f"Onderwerp geblokkeerd ({blocked}): {topic!r}. "
            "Zie scripts/nl/safety.py."
        )

    if keep_local is None:
        keep_local = KEEP_LOCAL_AFTER_UPLOAD

    variant = build_variant(topic, salt)
    slug = slugify(topic)

    print("=" * 64)
    print("  NEDERLANDSE PIPELINE")
    print(f"  Onderwerp: {topic}")
    print(f"  Variant:   {variant.summary()}")
    print("=" * 64)

    # ─── 1. Script ──────────────────────────────────────
    print("\n[1/7] Script schrijven...")
    script = generate_script_nl(topic, variant)
    narration = full_narration_nl(script)
    print(f"  Titel: {script['title']}")
    print(f"  Woorden: {len(narration.split())} | Secties: {len(script['sections'])}")
    print(f"  Invalshoek: {script.get('eigen_invalshoek', '(geen)')}")

    # ─── 2. SEO ─────────────────────────────────────────
    print("\n[2/7] Nederlandse SEO...")
    try:
        script = optimize_script_seo_nl(script)
        narration = full_narration_nl(script)
    except (requests.RequestException, ValueError) as e:
        print(f"  SEO overgeslagen: {e}")

    script_path = save_script(script, OUTPUT_DIR / f"{slug}_nl_script.json")

    # ─── 3. Narration ───────────────────────────────────
    print(f"\n[3/7] Narratie inspreken ({variant.voice.id})...")
    section_audio = nl_tts.synthesize_sections(
        script["sections"], slug, variant.voice, AUDIO_DIR
    )
    if script.get("hook"):
        hook_audio = AUDIO_DIR / f"{slug}_hook.mp3"
        nl_tts.synthesize(script["hook"], hook_audio, variant.voice)
        section_audio.insert(0, hook_audio)

    full_audio = AUDIO_DIR / f"{slug}_vol.mp3"
    nl_tts.combine(
        section_audio, full_audio,
        pause_ms=variant.pacing.section_pause_ms,
        sections=script["sections"],
    )
    duration = nl_tts.duration_of(full_audio)
    print(f"  Totale duur: {duration / 60:.1f} min")

    # Checked here rather than before upload so the failure is loud while the
    # render can still be salvaged, instead of after 20 minutes of encoding.
    too_short = None
    try:
        assert_monetizable(duration)
    except TooShortToMonetizeError as e:
        too_short = e
        print(f"  LET OP: {e}")
        if upload:
            print("  Upload wordt overgeslagen. Render gaat door.")

    # ─── 4. Subtitles ───────────────────────────────────
    print("\n[4/7] Ondertitels...")
    subtitles = generate_subtitles(full_audio, narration, duration)
    subtitle_path = SUBTITLE_DIR / f"{slug}_nl_subs"
    save_subtitles(subtitles, subtitle_path)

    # ─── 5. Footage ─────────────────────────────────────
    print("\n[5/7] Beeldmateriaal ophalen...")
    footage_map = fetch_all_footage(script)
    footage = [clip for idx in sorted(footage_map) for clip in footage_map[idx]]
    print(f"  {len(footage)} clips")

    # ─── 6. Render ──────────────────────────────────────
    print("\n[6/7] Video monteren...")
    music = None
    if variant.use_music:
        tracks = sorted(MUSIC_DIR.glob("*.mp3"))
        if tracks:
            # Pick by seed so the bed varies across uploads.
            music = tracks[int(variant.seed, 16) % len(tracks)]
            print(f"  Muziek: {music.name}")

    video_path = VIDEO_DIR / f"{slug}_nl.mp4"
    assemble_video(
        footage_files=footage,
        audio_path=full_audio,
        subtitles=subtitles,
        output_path=video_path,
        bg_music_path=music,
        caption_style=variant.captions,
        target_clip_duration=(variant.pacing.min_cut + variant.pacing.max_cut) / 2,
    )

    thumbnail = create_thumbnail(
        text=script.get("thumbnail_text", topic[:30]),
        output_path=THUMBNAIL_DIR / f"{slug}_nl_thumb.png",
        stock_keywords=_thumbnail_keywords(script),
        text_color=variant.thumbnail.text_color,
        style=variant.thumbnail.style,
        font_path=variant.thumbnail.font,
    )

    short_path, short_thumb, short_meta = (None, None, {})
    if make_short:
        short_path, short_thumb, short_meta = _build_short(
            script, variant, slug, footage
        )

    # ─── 7. Upload ──────────────────────────────────────
    uploaded = {}
    if upload and too_short:
        print(f"\n[7/7] Upload geweigerd: {too_short}")
    elif upload:
        print("\n[7/7] Uploaden naar YouTube...")
        uploaded = _upload(
            script, variant, video_path, thumbnail,
            short_path, short_thumb, short_meta, privacy, schedule,
        )
    else:
        print("\n[7/7] Upload overgeslagen (gebruik --upload)")

    _summary(script, variant, video_path, short_path, duration, uploaded)

    if not keep_local and uploaded.get("video_id"):
        _cleanup(slug, video_path, thumbnail, short_path, short_thumb,
                 footage, uploaded)

    result = {
        "topic": topic,
        "title": script["title"],
        "variant": variant.summary(),
        "script_path": str(script_path),
        "video_path": str(video_path),
        "short_path": str(short_path) if short_path else None,
        "duration_seconds": duration,
    }
    result.update(uploaded)
    return result


def _thumbnail_keywords(script: dict) -> list[str]:
    """Reuse the script's own English visual keywords for the thumbnail frame."""
    keywords: list[str] = []
    for section in script.get("sections", [])[:3]:
        keywords.extend(str(k) for k in section.get("visual_keywords", []))
    return keywords[:5] or ["netherlands landscape", "dutch canal"]


def _build_short(script: dict, variant: VideoVariant, slug: str,
                 footage: list) -> tuple:
    """Render the Short. Failure here must not cost the long-form."""
    print("\n[6b/7] Short maken...")
    try:
        from scripts.shorts_generator import create_short

        hook = extract_short_hook_nl(script, variant)
        narration = hook.get("narration", "")
        if not narration.strip():
            print("  Geen bruikbaar fragment — Short overgeslagen.")
            return None, None, {}

        audio = AUDIO_DIR / f"{slug}_nl_short.mp3"
        nl_tts.synthesize(narration, audio, variant.short_voice)
        duration = nl_tts.duration_of(audio)

        subtitles = group_words_into_subtitles(
            estimate_timestamps(narration, duration)
        )

        path = VIDEO_DIR / f"{slug}_nl_short.mp4"
        create_short(
            audio_path=audio,
            subtitles=subtitles,
            footage_files=footage[:15],
            output_path=path,
            hook_text=hook.get("hook_text", ""),
            caption_style=variant.short_captions,
            # Shorts cut faster than the long-form regardless of profile.
            cut_range=(variant.pacing.min_cut, variant.pacing.max_cut),
        )

        thumb = THUMBNAIL_DIR / f"{slug}_nl_short_thumb.png"
        create_thumbnail(
            text=hook.get("hook_text", script.get("thumbnail_text", "")),
            output_path=thumb,
            stock_keywords=_thumbnail_keywords(script),
            text_color=variant.thumbnail.text_color,
            font_path=variant.thumbnail.font,
        )
        return path, thumb, hook
    except (requests.RequestException, ValueError, OSError) as e:
        print(f"  Short mislukt: {e}")
        return None, None, {}


def _upload(script: dict, variant: VideoVariant, video_path: Path,
            thumbnail: Path, short_path: Path, short_thumb: Path,
            short_meta: dict, privacy: str, schedule: str) -> dict:
    """Upload long-form then Short, disclosing synthetic media on both."""
    from scripts.nl.channel_guard import assert_distinct_channels
    from scripts.youtube_uploader import upload_with_thumbnail

    # Last point at which a mis-authorised token is still recoverable. Past
    # this line the video is on a channel, and taking it down does not undo
    # the notification its subscribers already got.
    identity = assert_distinct_channels(
        BASE_DIR / NL_TOKEN_FILE, BASE_DIR / "token.json"
    )
    if identity:
        print(f"  Kanaal: {identity['title']} ({identity['id']})")

    uploaded: dict = {}
    try:
        video_id = upload_with_thumbnail(
            video_path=str(video_path),
            thumbnail_path=str(thumbnail),
            title=script["title"],
            description=script.get("description", ""),
            tags=script.get("tags", []),
            privacy=privacy,
            publish_at=schedule,
            synthetic_media=NL_DECLARE_SYNTHETIC_MEDIA,
            language=NL_LANGUAGE_CODE,
        )
        uploaded["video_id"] = video_id
        uploaded["video_url"] = f"https://youtube.com/watch?v={video_id}"
    except FileNotFoundError as e:
        print(f"  Upload overgeslagen: {e}")
        return uploaded
    except Exception as e:
        print(f"  Upload mislukt: {e}")
        return uploaded

    if short_path and Path(short_path).exists():
        try:
            print("\n  Short uploaden...")
            short_id = upload_with_thumbnail(
                video_path=str(short_path),
                thumbnail_path=str(short_thumb) if short_thumb else "",
                title=short_title_nl(script),
                description=script.get("description", "")[:400],
                tags=script.get("tags", [])[:10],
                privacy=privacy,
                is_short=True,
                synthetic_media=NL_DECLARE_SYNTHETIC_MEDIA,
                language=NL_LANGUAGE_CODE,
            )
            uploaded["short_id"] = short_id
            uploaded["short_url"] = f"https://youtube.com/shorts/{short_id}"
        except Exception as e:
            print(f"  Short-upload mislukt: {e}")

    return uploaded


def _cleanup(slug: str, video_path: Path, thumbnail: Path, short_path: Path,
             short_thumb: Path, footage: list, uploaded: dict) -> None:
    """Purge heavy artifacts once the long-form is confirmed on YouTube.

    A Short that rendered but failed to upload keeps its mp4 and audio so it
    can be retried; everything else goes.
    """
    keep_short = short_path is not None and not uploaded.get("short_id")

    artifacts = [video_path, thumbnail]
    artifacts += list(SUBTITLE_DIR.glob(f"{slug}_nl_subs*"))
    for audio in AUDIO_DIR.glob(f"{slug}*.mp3"):
        if keep_short and audio.name == f"{slug}_nl_short.mp3":
            continue
        artifacts.append(audio)
    if not keep_short:
        artifacts += [short_path, short_thumb]

    print("\n[8/8] Lokale bestanden opruimen...")
    purge_artifacts([a for a in artifacts if a], footage)


def _summary(script: dict, variant: VideoVariant, video_path: Path,
             short_path: Path, duration: float, uploaded: dict) -> None:
    """Print the run summary, including the variant so a run is traceable."""
    print("\n" + "=" * 64)
    print("  KLAAR")
    print("=" * 64)
    print(f"  Titel:      {script['title']}")
    print(f"  Invalshoek: {script.get('eigen_invalshoek', '(geen)')}")
    print(f"  Duur:       {duration / 60:.1f} min")
    print(f"  Variant:    {variant.summary()}")
    print(f"  Video:      {video_path}")
    if short_path:
        print(f"  Short:      {short_path}")
    if uploaded.get("video_url"):
        print(f"  YouTube:    {uploaded['video_url']}")
    if uploaded.get("short_url"):
        print(f"  Short-URL:  {uploaded['short_url']}")
    print("=" * 64)
