"""End-to-end long-form video generator for the 55+ audience.

Pipeline:
  1. Generate 6-act script (longform_55plus)
  2. Generate TTS narration per act
  3. Fetch fresh Pexels footage using act keywords (denser than Shorts)
  4. Generate long-form subtitles (5-7 word chunks, longer display)
  5. Assemble with denser footage + BGM bed at -26 dB
  6. Build chapters-enabled description

Usage:
  python3 generate_longform.py "After 38 Years Of Marriage, She Discovered His Second Family"
  python3 generate_longform.py "..." --no-upload
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

sys.path.insert(0, ".")
from config import AUDIO_DIR, VIDEO_DIR, SUBTITLE_DIR, OUTPUT_DIR
from scripts.longform_55plus import (
    generate_longform_script,
    build_chapters_description,
)
from scripts.tts_engine import generate_audio, get_audio_duration
from scripts.subtitle_generator import estimate_timestamps, group_words_for_longform
from scripts.footage_sourcer import fetch_all_footage, reset_used_videos
from scripts.video_assembler import assemble_longform_video


def generate_longform_video(topic: str, context: str = "", upload: bool = False) -> dict:
    """Generate a complete long-form video from topic to rendered file."""
    slug = topic.lower().replace(" ", "_").replace(",", "")[:60]

    # ── 1. Script
    print(f"\n[1/6] Generating 6-act longform script for: {topic}")
    script = generate_longform_script(topic, context)
    total_words = sum(len(s["narration"].split()) for s in script.get("sections", []))
    print(f"  Title: {script.get('title')}")
    print(f"  Total words: {total_words} (~{total_words/150:.1f} min)")

    # Save script
    script_path = OUTPUT_DIR / f"{slug}_longform_script.json"
    script_path.write_text(json.dumps(script, indent=2))

    # ── 2. TTS per act + concatenation
    print(f"\n[2/6] Generating TTS for {len(script['sections'])} acts...")
    section_audio_paths = []
    section_durations = []
    for i, sec in enumerate(script["sections"], 1):
        act_audio = AUDIO_DIR / f"{slug}_act{i}.mp3"
        generate_audio(sec["narration"], act_audio)
        dur = get_audio_duration(act_audio)
        section_audio_paths.append(act_audio)
        section_durations.append(dur)
        print(f"  Act {i}: {dur:.1f}s")

    # Concatenate act audio into one narration file
    full_audio_path = AUDIO_DIR / f"{slug}_longform_full.mp3"
    _concat_mp3s(section_audio_paths, full_audio_path)
    total_duration = sum(section_durations)
    print(f"  Full narration: {total_duration:.1f}s ({total_duration/60:.1f} min)")

    # ── 3. Fetch footage (denser for longform — more unique clips)
    print(f"\n[3/6] Fetching footage (denser mode)...")
    reset_used_videos()
    footage_map = fetch_all_footage(script)
    all_footage = []
    for files in footage_map.values():
        all_footage.extend(files)
    print(f"  Total unique clips: {len(all_footage)}")

    if len(all_footage) < 20:
        print(f"  WARNING: only {len(all_footage)} clips — longform wants 60-80. "
              f"Video may feel repetitive.")

    # ── 4. Subtitles — longform chunking
    print(f"\n[4/6] Generating longform subtitles (5-7 word chunks)...")
    # Build subtitle timing from the full concatenated narration
    full_narration = " ".join(sec["narration"] for sec in script["sections"])
    words = estimate_timestamps(full_narration, total_duration)
    subs = group_words_for_longform(words, min_words=5, max_words=7, min_display_seconds=1.8)
    print(f"  Subtitle groups: {len(subs)}")

    # ── 5. Assemble
    print(f"\n[5/6] Assembling longform video...")
    output_path = VIDEO_DIR / f"{slug}_longform.mp4"
    assemble_longform_video(
        footage_files=[str(f) for f in all_footage],
        audio_path=full_audio_path,
        subtitles=subs,
        output_path=output_path,
    )

    # ── 6. Description with chapters
    print(f"\n[6/6] Building chapters description...")
    full_description = build_chapters_description(script, section_durations)
    desc_path = OUTPUT_DIR / f"{slug}_longform_description.txt"
    desc_path.write_text(full_description)
    print(f"  Description saved: {desc_path}")
    print(f"\n  CHAPTERS:")
    for line in full_description.split("CHAPTERS\n")[1].split("\n\n")[0].split("\n"):
        print(f"    {line}")

    result = {
        "slug": slug,
        "title": script.get("title"),
        "video_path": str(output_path),
        "description_path": str(desc_path),
        "duration_min": total_duration / 60,
        "word_count": total_words,
    }

    # Upload (optional)
    if upload:
        print(f"\n[UPLOAD] Pushing to YouTube...")
        from scripts.youtube_uploader import upload_video
        try:
            vid_id = upload_video(
                str(output_path),
                title=script.get("title", topic)[:100],
                description=full_description,
                tags=script.get("tags", [])[:15],
                privacy="public",
                is_short=False,  # LONG-FORM
            )
            result["youtube_url"] = f"https://youtube.com/watch?v={vid_id}"
            print(f"  LIVE: {result['youtube_url']}")
        except Exception as e:
            print(f"  Upload failed: {e}")
            result["upload_error"] = str(e)

    return result


def _concat_mp3s(paths: list, output: Path):
    """Concatenate MP3 files into one file using ffmpeg concat demuxer."""
    import subprocess
    list_file = output.parent / f"{output.stem}_list.txt"
    list_file.write_text("\n".join(f"file '{p.absolute()}'" for p in paths))

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    list_file.unlink()


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else \
        "After 38 Years Of Marriage, She Discovered His Second Family"
    upload = "--upload" in sys.argv

    context = """A woman in her early 60s, married for nearly four decades,
discovers after her husband's retirement that he has maintained a second
family in another city for over two decades. Three adult children on each
side. The discovery comes from a misdirected letter. Focus on the slow
realization, the 40-year relationship history, the confrontation, the
fallout with the grown children on both sides, and what remained.
Documentary tone. No sensationalism."""

    result = generate_longform_video(topic, context, upload=upload)

    print(f"\n{'='*60}")
    print(f"  LONGFORM COMPLETE")
    print(f"{'='*60}")
    print(f"  Title:    {result['title']}")
    print(f"  Duration: {result['duration_min']:.1f} min")
    print(f"  Words:    {result['word_count']}")
    print(f"  Video:    {result['video_path']}")
    print(f"  Desc:     {result['description_path']}")
    if "youtube_url" in result:
        print(f"  YouTube:  {result['youtube_url']}")
