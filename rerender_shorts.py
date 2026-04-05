"""Re-render all stockpiled multi-part Shorts with the new impact-frame
intro. Reuses cached audio; re-runs the story split to get fresh hook
text per part; picks fresh footage from STOCK_DIR."""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(override=True)

sys.path.insert(0, ".")
from config import AUDIO_DIR, VIDEO_DIR, STOCK_DIR
from scripts.shorts_generator import create_short
from scripts.subtitle_generator import estimate_timestamps, group_words_into_subtitles
from scripts.tts_engine import get_audio_duration
from scripts.multipart_shorts import split_story_into_parts


def find_script_file(prefix: str) -> Optional[Path]:
    """Find the cached script json by audio-prefix match."""
    for p in Path("output").glob("*_script.json"):
        name = p.stem.replace("_script", "")
        if name == prefix or prefix.startswith(name) or name.startswith(prefix):
            return p
    return None


def group_parts_by_story():
    """Group part mp4s under output/videos by their slug prefix."""
    groups = {}
    for vid in sorted(VIDEO_DIR.glob("*_part*.mp4")):
        m = re.match(r"(.+)_part(\d+)$", vid.stem)
        if not m:
            continue
        prefix, part_num = m.group(1), int(m.group(2))
        groups.setdefault(prefix, []).append(part_num)
    return groups


def rerender_story(prefix, part_nums):
    """Re-render all parts for one story. Returns count of successes."""
    print(f"\n{'='*60}\n  STORY: {prefix}\n{'='*60}")

    script_file = find_script_file(prefix)
    if not script_file:
        print(f"  SKIP — no cached script for {prefix}")
        return 0

    script = json.loads(script_file.read_text())
    num_parts = max(part_nums)

    # Re-run split to get fresh narration + hook_text per part
    print(f"  Splitting into {num_parts} parts for hook text...")
    try:
        parts = split_story_into_parts(script, num_parts=num_parts)
    except Exception as e:
        print(f"  SPLIT FAILED: {e}")
        return 0

    # Grab a fresh footage subset (reused across all parts, different slices)
    all_footage = sorted(STOCK_DIR.glob("section_*.mp4"))
    random.shuffle(all_footage)
    footage_pool = all_footage[:40]
    if not footage_pool:
        print(f"  SKIP — no cached footage")
        return 0

    success = 0
    for part in parts:
        part_num = part.get("part_number", parts.index(part) + 1)
        if part_num not in part_nums:
            continue

        narration = part.get("narration", "")
        hook_text = part.get("hook_text", f"Part {part_num}")

        if part_num < num_parts:
            narration += f"... Follow for Part {part_num + 1}."

        audio_path = AUDIO_DIR / f"{prefix}_part{part_num}.mp3"
        if not audio_path.exists():
            print(f"  Part {part_num}: SKIP — no audio at {audio_path.name}")
            continue

        try:
            duration = get_audio_duration(audio_path)
            subs = group_words_into_subtitles(estimate_timestamps(narration, duration))

            # Different footage slice per part (no overlap)
            slice_size = max(8, len(footage_pool) // num_parts)
            start_idx = ((part_num - 1) * slice_size) % len(footage_pool)
            part_footage = footage_pool[start_idx:start_idx + slice_size]
            if len(part_footage) < 5:
                part_footage = footage_pool[:slice_size]

            out_path = VIDEO_DIR / f"{prefix}_part{part_num}.mp4"
            print(f"\n  [Part {part_num}] Hook: {hook_text!r} — rendering...")
            create_short(
                audio_path=audio_path,
                subtitles=subs,
                footage_files=part_footage,
                output_path=out_path,
                hook_text=hook_text,
            )
            success += 1
        except Exception as e:
            print(f"  Part {part_num}: FAILED — {e}")

    return success


if __name__ == "__main__":
    groups = group_parts_by_story()
    print(f"Found {len(groups)} stories with {sum(len(v) for v in groups.values())} parts total.")

    total_success = 0
    for i, (prefix, part_nums) in enumerate(groups.items(), 1):
        print(f"\n[{i}/{len(groups)}]")
        total_success += rerender_story(prefix, sorted(part_nums))

    print(f"\n{'='*60}")
    print(f"  DONE — {total_success} parts re-rendered with impact frame")
    print(f"{'='*60}")
