"""
Dutch Shorts.

Shorts are the funnel, not the revenue — Shorts RPM sits around $0.02-$0.12
per thousand views, so a Short earns roughly nothing on its own. Its job is to
put the channel in front of Dutch viewers who then watch the long-form, where
mid-rolls actually pay.

That changes what the Short should be. It is not a trailer for the video; it
is a self-contained Dutch clip that resolves its own hook, and only then
suggests there is more. A Short that ends on "kijk de hele video" converts
badly and is the shape YouTube reads as template-produced.
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import GROQ_API_KEY, SCRIPT_MODEL
from scripts.nl.variation import VideoVariant

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def extract_short_hook_nl(script: dict, variant: VideoVariant) -> dict:
    """Pull a self-contained 45-60 second Dutch segment out of a long-form script.

    Raises requests.HTTPError on API failure so the caller can skip the Short
    and still ship the long-form, which is the part that earns.
    """
    source = script.get("hook", "") + "\n"
    for section in script.get("sections", [])[:4]:
        source += section.get("narration", "") + "\n"

    angle = script.get("eigen_invalshoek", "")

    prompt = f"""Haal het sterkste fragment uit dit Nederlandse script en maak er een
zelfstandige Short van.

De stelling van de video: {angle}

Eisen:
- 45 tot 60 seconden gesproken Nederlands (ongeveer 110-150 woorden).
- De eerste zin moet het scrollen stoppen. Geen aanloop.
- Het fragment moet op zichzelf kloppen: de kijker die alleen dit ziet, heeft
  iets geleerd. Eindig NIET met "kijk de hele video".
- Gebruik alleen informatie die al in het script staat. Verzin niets.
- visual_keywords in het ENGELS (Pexels is Engelstalig geïndexeerd).
- hook_text: 2 tot 5 Nederlandse woorden voor de tekstoverlay in beeld.

Antwoord met UITSLUITEND JSON:
{{"narration": "...", "visual_keywords": ["english keyword"], "hook_text": "..."}}

Script:
{source}"""

    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {"role": "system",
             "content": "Je bent een Nederlandse video-editor. Antwoord uitsluitend "
                        "met geldige JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}",
               "Content-Type": "application/json"}

    # This is the third Groq call for a single video, so it is the one most
    # likely to land on an exhausted per-minute token budget.
    for attempt in range(3):
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        if response.status_code == 429:
            wait = 20 * (attempt + 1)
            print(f"  Groq TPM-limiet, {wait}s wachten (poging {attempt + 1}/3)...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])
    raise requests.HTTPError("Groq rate limit niet opgelost na 3 pogingen")


def short_title_nl(script: dict) -> str:
    """Build the Short's title.

    Deliberately not the long-form title: two uploads sharing a title is both
    a duplicate-content signal and a wasted second search listing.
    """
    thumb = script.get("thumbnail_text", "").strip()
    title = script.get("title", "").strip()
    base = thumb if len(thumb) > 8 else title
    return base[:90]
