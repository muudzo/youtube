#!/usr/bin/env python3
"""
Faceless YouTube Video Pipeline — Dark History / Rabbit Holes

Usage:
    python pipeline.py "The Dyatlov Pass Incident"
    python pipeline.py "MK Ultra CIA Mind Control" --upload
    python pipeline.py "The Lost Colony of Roanoke" --upload --short
    python pipeline.py "Unit 731" --upload --privacy unlisted --schedule "2026-03-26T15:00:00Z"

One command: topic → video → uploaded to YouTube.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from config import VIDEO_DIR, AUDIO_DIR, SUBTITLE_DIR, THUMBNAIL_DIR, MUSIC_DIR
from scripts.script_generator import generate_script, save_script, get_full_narration
from scripts.tts_engine import generate_audio, generate_section_audio, combine_audio, get_audio_duration
from scripts.footage_sourcer import fetch_all_footage
from scripts.subtitle_generator import generate_subtitles, save_subtitles
from scripts.video_assembler import assemble_video
from scripts.thumbnail_generator import create_thumbnail


def slugify(text: str) -> str:
    """Convert topic to a safe filename slug."""
    return text.lower().replace(" ", "_").replace("'", "")[:50]


def run_pipeline(
    topic: str,
    tts_provider: str = None,
    thumbnail_style: str = "bright",
    skip_footage: bool = False,
    skip_video: bool = False,
    upload: bool = False,
    upload_short: bool = False,
    privacy: str = "public",
    schedule: str = None,
):
    """Run the full video pipeline from topic to finished video."""
    slug = slugify(topic)
    print("=" * 60)
    print(f"  FACELESS YOUTUBE PIPELINE")
    print(f"  Topic: {topic}")
    print("=" * 60)

    # ─── Step 1: Generate Script ────────────────────────────
    print("\n[1/8] Generating script...")
    script = generate_script(topic)
    narration = get_full_narration(script)
    word_count = len(narration.split())
    print(f"  Title: {script['title']}")
    print(f"  Words: {word_count} | Sections: {len(script['sections'])}")

    # ─── Step 1b: SEO Optimization ───────────────────────────
    print("\n[1b/8] SEO optimizing...")
    try:
        from scripts.seo_optimizer import optimize_script_seo
        script = optimize_script_seo(script)
    except Exception as e:
        print(f"  SEO optimization skipped: {e}")

    script_path = save_script(script, Path("output") / f"{slug}_script.json")

    # ─── Step 2: Generate Audio ─────────────────────────────
    print("\n[2/8] Generating narration audio...")
    audio_files = generate_section_audio(script["sections"], slug, tts_provider)

    if script.get("hook"):
        hook_audio = AUDIO_DIR / f"{slug}_hook.mp3"
        generate_audio(script["hook"], hook_audio, tts_provider)
        audio_files.insert(0, hook_audio)
        print(f"  Generated audio: {hook_audio.name}")

    combined_audio = AUDIO_DIR / f"{slug}_full.mp3"
    combine_audio(audio_files, combined_audio)
    total_duration = get_audio_duration(combined_audio)
    print(f"  Total narration: {total_duration:.1f}s ({total_duration / 60:.1f} min)")

    # ─── Step 3: Generate Subtitles ─────────────────────────
    print("\n[3/7] Generating subtitles...")
    subtitles = generate_subtitles(combined_audio, narration, total_duration)
    sub_path = SUBTITLE_DIR / f"{slug}_subs"
    save_subtitles(subtitles, sub_path)

    # ─── Step 4: Fetch Stock Footage ────────────────────────
    footage_files = []
    if not skip_footage:
        print("\n[4/7] Fetching stock footage...")
        footage_map = fetch_all_footage(script)
        for section_idx in sorted(footage_map.keys()):
            footage_files.extend(footage_map[section_idx])
        print(f"  Total clips: {len(footage_files)}")
    else:
        print("\n[4/7] Skipping footage (--no-footage)")

    # ─── Step 5: Assemble Video ─────────────────────────────
    if not skip_video:
        print("\n[5/7] Assembling video...")
        bg_music = None
        music_files = list(MUSIC_DIR.glob("*.mp3"))
        if music_files:
            bg_music = music_files[0]
            print(f"  Using background music: {bg_music.name}")

        output_video = VIDEO_DIR / f"{slug}.mp4"
        assemble_video(
            footage_files=footage_files,
            audio_path=combined_audio,
            subtitles=subtitles,
            output_path=output_video,
            bg_music_path=bg_music,
        )
    else:
        print("\n[5/7] Skipping video assembly (--no-video)")
        output_video = None

    # ─── Step 6: Generate Thumbnail ─────────────────────────
    print("\n[6/7] Generating thumbnail...")
    thumb_text = script.get("thumbnail_text", topic[:30])
    stock_kw = ["mountain", "landscape", "snowy", "hiking", "forest"]
    thumbnail = create_thumbnail(
        text=thumb_text,
        output_path=THUMBNAIL_DIR / f"{slug}_thumb.png",
        stock_keywords=stock_kw,
    )

    # ─── Step 6b: Generate Short ────────────────────────────
    short_path = None
    short_thumb = None
    if upload_short and not skip_video:
        print("\n[6b/7] Generating YouTube Short...")
        try:
            from scripts.shorts_generator import extract_hook_for_short, create_short
            from scripts.subtitle_generator import estimate_timestamps, group_words_into_subtitles

            hook_data = extract_hook_for_short(script)
            short_narration = hook_data.get("narration", "")

            short_audio = AUDIO_DIR / f"{slug}_short.mp3"
            generate_audio(short_narration, short_audio, tts_provider)
            short_duration = get_audio_duration(short_audio)

            short_subs = group_words_into_subtitles(
                estimate_timestamps(short_narration, short_duration)
            )

            # Use all footage — Shorts generator handles brightness filtering + dedup
            hook_text = hook_data.get("hook_text", "")

            short_path = VIDEO_DIR / f"{slug}_short.mp4"
            create_short(
                audio_path=short_audio,
                subtitles=short_subs,
                footage_files=footage_files[:15],  # give it more to choose from
                output_path=short_path,
                hook_text=hook_text,
            )

            short_thumb = THUMBNAIL_DIR / f"{slug}_short_thumb.png"
            create_thumbnail(
                text=thumb_text,
                output_path=short_thumb,
                stock_keywords=stock_kw,
                text_color="yellow",
            )
        except Exception as e:
            print(f"  Short generation failed: {e}")

    # ─── Step 7: Upload to YouTube ──────────────────────────
    uploaded = {}
    if upload and output_video:
        print("\n[7/7] Uploading to YouTube...")
        try:
            from scripts.youtube_uploader import upload_with_thumbnail

            # Upload long-form
            video_id = upload_with_thumbnail(
                video_path=str(output_video),
                thumbnail_path=str(thumbnail),
                title=script["title"],
                description=_build_description(script),
                tags=script.get("tags", []),
                privacy=privacy,
                publish_at=schedule,
            )
            uploaded["video_id"] = video_id
            uploaded["video_url"] = f"https://youtube.com/watch?v={video_id}"

            # Upload Short
            if short_path and short_path.exists():
                print("\n  Uploading Short...")
                short_title = script.get("thumbnail_text", topic[:30])
                short_id = upload_with_thumbnail(
                    video_path=str(short_path),
                    thumbnail_path=str(short_thumb) if short_thumb else "",
                    title=short_title,
                    description=_build_description(script, is_short=True),
                    tags=script.get("tags", []),
                    privacy=privacy,
                    is_short=True,
                )
                uploaded["short_id"] = short_id
                uploaded["short_url"] = f"https://youtube.com/shorts/{short_id}"

        except FileNotFoundError as e:
            print(f"\n  Upload skipped: {e}")
        except Exception as e:
            print(f"\n  Upload failed: {e}")
    else:
        print("\n[7/7] Skipping upload (use --upload to auto-upload)")

    # ─── Summary ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE!")
    print("=" * 60)
    print(f"  Title:     {script['title']}")
    print(f"  Script:    {script_path}")
    print(f"  Audio:     {combined_audio}")
    print(f"  Subtitles: {sub_path}.srt")
    if output_video:
        print(f"  Video:     {output_video}")
    if short_path:
        print(f"  Short:     {short_path}")
    print(f"  Thumbnail: {thumbnail}")
    print(f"  Duration:  {total_duration / 60:.1f} min")
    if uploaded.get("video_url"):
        print(f"  YouTube:   {uploaded['video_url']}")
    if uploaded.get("short_url"):
        print(f"  Short:     {uploaded['short_url']}")
    print(f"\n  Description:\n  {script.get('description', 'N/A')}")
    print(f"\n  Tags: {', '.join(script.get('tags', []))}")
    print("=" * 60)

    result = {
        "title": script["title"],
        "description": script.get("description", ""),
        "tags": script.get("tags", []),
        "script_path": str(script_path),
        "audio_path": str(combined_audio),
        "subtitle_path": f"{sub_path}.srt",
        "video_path": str(output_video) if output_video else None,
        "short_path": str(short_path) if short_path else None,
        "thumbnail_path": str(thumbnail),
        "duration_seconds": total_duration,
    }
    result.update(uploaded)
    return result


def _build_description(script: dict, is_short: bool = False) -> str:
    """Build a YouTube description with keywords and hashtags."""
    desc = script.get("description", "")
    tags = script.get("tags", [])
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])

    if is_short:
        return f"{desc}\n\n{hashtags} #Shorts"

    return (
        f"{desc}\n\n"
        f"{hashtags}\n\n"
        f"---\n"
        f"Subscribe for more dark history and unsolved mysteries."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Faceless YouTube Video Pipeline — Dark History / Rabbit Holes"
    )
    parser.add_argument("topic", help="Video topic (e.g., 'The Dyatlov Pass Incident')")
    parser.add_argument("--tts", choices=["edge", "google"], help="TTS provider")
    parser.add_argument("--style", default="bright", help="Thumbnail style")
    parser.add_argument("--no-footage", action="store_true", help="Skip stock footage download")
    parser.add_argument("--no-video", action="store_true", help="Skip video assembly")
    parser.add_argument("--upload", action="store_true", help="Auto-upload to YouTube")
    parser.add_argument("--short", action="store_true", help="Also generate + upload a Short")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    parser.add_argument("--schedule", help="Schedule publish (ISO 8601: 2026-03-25T15:00:00Z)")

    args = parser.parse_args()

    run_pipeline(
        topic=args.topic,
        tts_provider=args.tts,
        thumbnail_style=args.style,
        skip_footage=args.no_footage,
        skip_video=args.no_video,
        upload=args.upload,
        upload_short=args.short,
        privacy=args.privacy,
        schedule=args.schedule,
    )


if __name__ == "__main__":
    main()
