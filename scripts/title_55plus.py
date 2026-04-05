"""Title rewriter for 4kMUDZO's 55+ audience.

Older viewers dislike metaphor hooks and cryptic clickbait. They want
clear chronology and concrete subjects.

NOT wired into the upload path yet — this lives as a standalone module
so we can A/B test it cleanly against the current title style once the
pacing experiment has produced signal.

Formula:
  After [X Years / X Decades], [Clear Subject] Discovered [Concrete Revelation]
  At Age [X], [Subject] Finally Told [Audience] The Truth About [Specific Issue]

Principles:
  - Specific > clever
  - Chronology > mystery
  - Clarity > suspense
  - Concrete people and time scales > abstractions
"""

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)
from config import GROQ_API_KEY, SCRIPT_MODEL


TITLE_PROMPT = """You are a YouTube title writer for a channel whose audience
is 100% age 55+, mostly 65+ males.

Older viewers do NOT respond to metaphor hooks, cryptic clickbait, or
Gen Z phrasing. They want clear chronology and concrete subjects.

REWRITE the title below using one of these formulas:

  1. After [X Years / X Decades], [Clear Subject] Discovered [Concrete Revelation]
  2. At Age [X], [Subject] Finally Told [Audience] The Truth About [Specific Issue]
  3. [X] Years After [Event], [Subject] Found Out [Concrete Fact]

RULES:
  - Use a specific time scale (years, decades) when possible
  - Name the concrete relationship (husband, wife, son, daughter, parents)
  - State the revelation plainly — no metaphors, no "the truth that changed everything"
  - NO ALL CAPS, NO excessive punctuation
  - Under 70 characters if possible, under 90 max
  - Respectful tone — this audience hates being manipulated

DO NOT talk down to them. 55+ is not cognitively slow — they prefer
clarity and resolution over clever hooks.

ORIGINAL TITLE: {original}
ORIGINAL STORY CONTEXT (first 300 chars): {context}

Return JSON: {{"title": "the rewritten title", "rationale": "why this works for 55+"}}
"""


def rewrite_title_for_55plus(original_title: str, story_context: str = "") -> dict:
    """Rewrite a title using the 55+ formula. Returns dict with 'title' and 'rationale'."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": TITLE_PROMPT.format(
                    original=original_title,
                    context=story_context[:300],
                ),
            },
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return json.loads(text)


if __name__ == "__main__":
    # Quick demo
    samples = [
        ("She Found The Black Box Of Her Marriage Hidden In A Drawer",
         "After 35 years of marriage, a widow discovers a sealed box in her late husband's desk..."),
        ("He Tried To Cancel The Divorce Because Her Cancer Treatment",
         "Man files for divorce from wife of 28 years, then learns of her diagnosis..."),
        ("His Parents Lied About What Happened To Him As A Baby For 20 Years",
         "Adult son discovers the truth his parents hid since his birth..."),
    ]
    for original, ctx in samples:
        try:
            result = rewrite_title_for_55plus(original, ctx)
            print(f"\nORIGINAL: {original}")
            print(f"REWRITE:  {result['title']}")
            print(f"WHY:      {result['rationale']}")
        except Exception as e:
            print(f"FAIL on {original}: {e}")
