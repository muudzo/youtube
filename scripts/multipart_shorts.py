"""
Multi-Part Shorts Generator — splits one story into 3-5 cliffhanger Shorts.

Each part ends on a hook: "Follow for Part 2"
This creates binge loops and 3-5x more impressions from one story.
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    GROQ_API_KEY,
    SCRIPT_MODEL,
    AUDIO_DIR,
    VIDEO_DIR,
    THUMBNAIL_DIR,
)


def split_story_into_parts(script: dict, num_parts: int = 3) -> list:
    """Use Groq to split a full script into cliffhanger Shorts parts."""
    full_narration = script.get("hook", "") + "\n"
    for section in script.get("sections", []):
        full_narration += section.get("narration", "") + "\n"

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": f"""You split stories into exactly {num_parts} YouTube Shorts parts.
Each part MUST:
- Be 40-55 seconds when read aloud (~100-130 words)
- End on a CLIFFHANGER that makes viewers desperate for the next part
- Part 1 opens with the strongest hook — stop the scroll
- Each part tells a complete mini-arc but leaves the biggest question unanswered
- Last part delivers the payoff/twist

Return ONLY valid JSON.""",
            },
            {
                "role": "user",
                "content": f"""Split this story into {num_parts} YouTube Shorts parts.

Story:
{full_narration}

Return JSON:
{{
  "parts": [
    {{
      "part_number": 1,
      "narration": "Part 1 narration text...",
      "hook_text": "2-5 word hook overlay for Part 1",
      "cliffhanger": "The line that makes them need Part 2",
      "visual_keywords": ["keyword1", "keyword2", "keyword3"]
    }}
  ]
}}""",
            },
        ],
        "temperature": 0.6,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(3):
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        response.raise_for_status()
        break

    data = response.json()
    text = data["choices"][0]["message"]["content"]
    result = json.loads(text)
    return result.get("parts", [])


def generate_multipart_shorts(
    topic: str,
    num_parts: int = 3,
    upload: bool = True,
) -> list:
    """Full pipeline: topic → script → split into parts → render → upload."""
    from scripts.script_generator import generate_script
    from scripts.tts_engine import generate_audio, get_audio_duration
    from scripts.subtitle_generator import estimate_timestamps, group_words_into_subtitles
    from scripts.shorts_generator import create_short
    from scripts.footage_sourcer import fetch_all_footage
    from scripts.youtube_uploader import upload_video

    slug = topic.lower().replace(" ", "_")[:50]

    # Step 1: Generate full script
    print(f"\n[1] Generating full script for: {topic}")
    script = generate_script(topic)
    title_base = script.get("title", topic)
    print(f"  Title: {title_base}")

    # Step 2: Fetch footage (once, shared across all parts)
    print(f"\n[2] Fetching footage...")
    footage_map = fetch_all_footage(script)
    all_footage = []
    for files in footage_map.values():
        all_footage.extend(files)
    print(f"  Total clips: {len(all_footage)}")

    # Step 3: Split into parts
    print(f"\n[3] Splitting into {num_parts} cliffhanger parts...")
    parts = split_story_into_parts(script, num_parts)
    print(f"  Got {len(parts)} parts")

    # Step 4: Generate each part
    results = []
    footage_per_part = max(5, len(all_footage) // len(parts))

    for i, part in enumerate(parts):
        part_num = part.get("part_number", i + 1)
        narration = part.get("narration", "")
        hook_text = part.get("hook_text", f"Part {part_num}")
        cliffhanger = part.get("cliffhanger", "")

        # Add "Follow for Part X" to narration (except last part)
        if part_num < len(parts):
            narration += f"... Follow for Part {part_num + 1}."

        print(f"\n[4.{part_num}] Rendering Part {part_num}/{len(parts)}...")
        print(f"  Hook: {hook_text}")
        print(f"  Cliffhanger: {cliffhanger[:60]}...")
        print(f"  Words: {len(narration.split())}")

        # Generate audio
        audio_path = AUDIO_DIR / f"{slug}_part{part_num}.mp3"
        generate_audio(narration, audio_path)
        duration = get_audio_duration(audio_path)
        print(f"  Duration: {duration:.1f}s")

        # Generate subtitles
        subs = group_words_into_subtitles(estimate_timestamps(narration, duration))

        # Use different footage slice for each part (no repeats)
        start_idx = (i * footage_per_part) % len(all_footage)
        part_footage = all_footage[start_idx:start_idx + footage_per_part]
        if len(part_footage) < 3:
            part_footage = all_footage[:footage_per_part]

        # Render Short
        short_path = VIDEO_DIR / f"{slug}_part{part_num}.mp4"
        create_short(
            audio_path=audio_path,
            subtitles=subs,
            footage_files=part_footage,
            output_path=short_path,
            hook_text=hook_text,
        )

        # Upload
        if upload:
            part_title = f"{topic} (Part {part_num}/{len(parts)})"
            part_desc = (
                f"{narration[:150]}...\n\n"
                f"Part {part_num} of {len(parts)}\n"
                f"Follow for the next part!\n\n"
                f"#Shorts #StoryTime #DarkHistory #Betrayal #Part{part_num}"
            )
            try:
                vid_id = upload_video(
                    str(short_path),
                    title=part_title,
                    description=part_desc,
                    tags=["story time", "dark history", "betrayal", "part " + str(part_num), "Shorts"],
                    privacy="public",
                    is_short=True,
                )
                print(f"  LIVE: https://youtube.com/shorts/{vid_id}")
                results.append({"part": part_num, "url": f"https://youtube.com/shorts/{vid_id}"})
            except Exception as e:
                print(f"  Upload failed: {e}")
                results.append({"part": part_num, "path": str(short_path), "error": str(e)})
        else:
            results.append({"part": part_num, "path": str(short_path)})

    print(f"\n===== {len(parts)}-PART SHORT SERIES COMPLETE =====")
    for r in results:
        if "url" in r:
            print(f"  Part {r['part']}: {r['url']}")
        else:
            print(f"  Part {r['part']}: {r.get('path', 'failed')}")

    return results


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "She Found The Black Box Of Her Marriage Hidden In A Drawer"
    parts = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    no_upload = "--no-upload" in sys.argv

    generate_multipart_shorts(topic, num_parts=parts, upload=not no_upload)
