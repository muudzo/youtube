"""Re-render existing videos with upgraded visual effects (Ken Burns, transitions, BGM fade)."""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)

sys.path.insert(0, ".")
from scripts.video_assembler import assemble_video
from config import VIDEO_DIR, AUDIO_DIR, SUBTITLE_DIR, STOCK_DIR
import re


def load_subtitles(srt_path):
    """Parse an SRT file into a list of subtitle dicts."""
    subs = []
    if not srt_path.exists():
        return subs
    content = srt_path.read_text()
    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_match = re.match(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})", lines[1])
        if not time_match:
            continue
        g = time_match.groups()
        start = int(g[0])*3600 + int(g[1])*60 + int(g[2]) + int(g[3])/1000
        end = int(g[4])*3600 + int(g[5])*60 + int(g[6]) + int(g[7])/1000
        text = " ".join(lines[2:])
        subs.append({"start": start, "end": end, "text": text})
    return subs

def rerender(slug):
    """Re-render a single video using cached assets."""
    script_file = Path(f"output/{slug}_script.json")
    audio_file = AUDIO_DIR / f"{slug}_full.mp3"
    srt_file = SUBTITLE_DIR / f"{slug}_subs.srt"
    output_file = VIDEO_DIR / f"{slug}.mp4"

    if not audio_file.exists():
        print(f"  SKIP {slug} — no audio file")
        return False

    # Load subtitles
    subtitles = load_subtitles(srt_file) if srt_file.exists() else []

    # Grab a random subset of 30 clips from cached footage (avoids scanning 1000+)
    import random
    all_footage = list(STOCK_DIR.glob(f"section_*.mp4"))
    if not all_footage:
        print(f"  SKIP {slug} — no cached footage")
        return False
    random.shuffle(all_footage)
    footage = all_footage[:30]  # 30 clips is plenty for an 8-10 min video

    print(f"\n  Re-rendering: {slug}")
    print(f"  Audio: {audio_file.name}")
    print(f"  Footage clips: {len(footage)} (from {len(all_footage)} available)")
    print(f"  Subtitles: {len(subtitles)} groups")

    assemble_video(
        footage_files=[str(f) for f in footage],
        audio_path=audio_file,
        subtitles=subtitles,
        output_path=output_file,
    )
    return True


if __name__ == "__main__":
    slugs = [
        "the_employee_who_destroyed_a_2_billion_dollar_comp",
        "scientists_found_something_under_antarctica_they_c",
        "zimbabwes_real_life_prison_break_the_story_of_chid",
        "she_found_her_husbands_secret_family_after_15_year",
        "she_waited_20_years_to_get_revenge_on_her_bully",
        "he_gave_his_best_friend_everything_then_his_friend",
        "the_town_that_went_insane_from_eating_bread",
    ]

    success = 0
    for i, slug in enumerate(slugs, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(slugs)}] {slug}")
        print(f"{'='*60}")
        try:
            if rerender(slug):
                success += 1
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\n{'='*60}")
    print(f"  DONE — {success}/{len(slugs)} videos re-rendered with new effects")
    print(f"{'='*60}")
