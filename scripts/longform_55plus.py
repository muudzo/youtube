"""Long-form script generator tuned for 4kMUDZO's 55+ audience.

This is NOT a stretched Short. It's a 6-act narrated documentary designed
for the YouTube TV app, where 65+ viewers spend most of their time.

Structure (12-15 minutes, ~1800-2200 words):
  Act 1 — Setup: relationship history, characters, era (2-3 min)
  Act 2 — Subtle inconsistencies: foreshadowing, small tells (2 min)
  Act 3 — The discovery: the moment everything changes (2-3 min)
  Act 4 — Confrontation: direct scene, dialogue (2-3 min)
  Act 5 — Family fallout: consequences, children, wider circle (2 min)
  Act 6 — Reflection / resolution: lesson, regret, what remained (1-2 min)

Tone principles (from the strategy brief):
  - Respectful pacing, not condescending
  - 55+ prefers CLARITY and RESOLUTION
  - No manipulation, no Gen Z slang
  - Documentary feel, not TikTok
  - Slower speech rhythm (render at 0.9x rate in TTS)
"""

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)
from config import GROQ_API_KEY, SCRIPT_MODEL


LONGFORM_SYSTEM_PROMPT = """You are a documentary scriptwriter for a YouTube
channel whose audience is 100% age 55+, mostly 65+ males watching on TV apps.

You write narrated long-form documentaries — 12-15 minutes, 1800-2200 words.
NOT stretched Shorts. These are proper narrative arcs with chapter beats.

AUDIENCE PRINCIPLES:
- 55+ prefers clarity and resolution over clever hooks
- They value respectful pacing — NOT condescension. They are not slow.
- They tolerate longer emotional buildup if the payoff is real
- They dislike manipulation, fake urgency, Gen Z slang, and TikTok energy
- They relate to stories about long marriages, adult children, inheritance,
  aging parents, regret, and reconciliation
- They watch on TV — the video must feel like an evening documentary

STRUCTURE (6 acts — STRICT WORD COUNTS, THIS IS NOT OPTIONAL):

Act 1 — Setup — MINIMUM 320 WORDS: Introduce the people, the era, the
        long relationship. Establish what seemed normal for decades. No
        hook tricks. Use specific years, ages, cities, jobs. Describe
        the texture of their life together in detail.

Act 2 — Inconsistencies — MINIMUM 280 WORDS: Walk through subtle tells
        year by year. Small things that didn't add up. Moments ignored
        in the moment. Give at least 4-5 concrete examples.

Act 3 — Discovery — MINIMUM 380 WORDS: The precise moment it all came
        out. Slow this down. Describe what was on the table, what the
        weather was, what she was holding. Let it land.

Act 4 — Confrontation — MINIMUM 320 WORDS: The scene where it's spoken
        aloud. Use real dialogue in at least 3 exchanges. Show silences.

Act 5 — Fallout — MINIMUM 280 WORDS: Children on both sides, their
        reactions, money, legal, friends, the wider circle.

Act 6 — Reflection — MINIMUM 220 WORDS: What remained one year later.
        What was learned. Resolution, not sequel tease.

TOTAL TARGET: 1800-2200 words across all six acts combined.
If your draft is under 1800 words TOTAL, you have failed the task and
must expand. Count your words before returning.

LANGUAGE RULES:
- Narration reads naturally aloud at 0.9x speech pacing
- Vary sentence length — longer reflective sentences, short impact lines
- Use concrete detail: year, age, place, object
- No "you won't believe" or "wait till you hear"
- No metaphor hooks — say what happened
- First sentence of Act 1 should be a clear statement, not a tease

OUTPUT FORMAT — respond with ONLY valid JSON, no markdown:
{
  "title": "Clear chronological title under 70 chars (use 'After X years' or 'At age X' style)",
  "description": "YouTube description — first 2 lines most important",
  "tags": ["tag1", "tag2"],
  "thumbnail_text": "3-5 words for thumbnail",
  "acts": [
    {
      "act_number": 1,
      "act_title": "Setup",
      "narration": "Full narration for this act",
      "visual_keywords": ["keyword1", "keyword2", "keyword3"]
    }
  ]
}
"""


def generate_longform_script(topic: str, context: str = "") -> dict:
    """Generate a 6-act documentary script for the 55+ audience."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    user_content = f"""Write a 6-act documentary script for this topic:

TOPIC: {topic}

"""
    if context:
        user_content += f"CONTEXT / VERIFIED FACTS:\n{context}\n\n"

    user_content += """Remember:
- 12-15 minutes total (1800-2200 words across all acts combined)
- 55+ audience, mostly 65+ males, watching on TV
- Respectful pacing, concrete detail, real resolution
- NO clickbait phrasing, NO manipulation
- Follow the 6-act structure exactly"""

    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {"role": "system", "content": LONGFORM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.6,
        "max_tokens": 6000,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    script = json.loads(text)

    # Flatten acts into the "sections" format the rest of the pipeline expects,
    # so we can reuse video_assembler, tts, etc. without modification.
    script["sections"] = [
        {
            "section_title": f"Act {a['act_number']}: {a.get('act_title', '')}",
            "narration": a["narration"],
            "visual_keywords": a.get("visual_keywords", []),
        }
        for a in script.get("acts", [])
    ]

    # Build a "hook" from the first sentence of Act 1 for pipeline compatibility
    if script.get("sections"):
        first_narration = script["sections"][0]["narration"]
        script["hook"] = first_narration.split(".")[0] + "."

    return script


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else \
        "After 38 Years Of Marriage, She Discovered He Had Another Family"

    context = """This is a betrayal discovery story. A woman in her early 60s,
married for nearly four decades, discovers after her husband's retirement
that he has maintained a second family in another city for over two decades.
Three adult children on each side. The discovery comes from a misdirected
letter. Focus on the slow realization, the 40-year relationship history,
the confrontation, the fallout with the grown children on both sides,
and what remained. Documentary tone. No sensationalism."""

    print(f"\nGenerating long-form prototype for: {topic}\n")
    script = generate_longform_script(topic, context)

    # Save
    slug = topic.lower().replace(" ", "_")[:60]
    out = Path("output") / f"{slug}_longform_script.json"
    out.write_text(json.dumps(script, indent=2))

    print(f"TITLE: {script.get('title')}")
    print(f"THUMB: {script.get('thumbnail_text')}")
    print(f"\nSaved to {out}")
    print(f"\nACT BREAKDOWN:")
    total_words = 0
    for sec in script.get("sections", []):
        wc = len(sec["narration"].split())
        total_words += wc
        print(f"  {sec['section_title']}: {wc} words")
    est_min = total_words / 150  # 150 wpm for documentary pacing
    print(f"\nTOTAL: {total_words} words ≈ {est_min:.1f} minutes at 0.9x pacing")
