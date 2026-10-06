"""
Dutch SEO.

The English scripts/seo_optimizer.py queries YouTube autocomplete without
locale parameters, so it ranks against English search demand. For a Dutch
channel that is worse than useless — it optimises the title toward phrases no
Dutch viewer types. This module reuses the hl=nl&gl=NL suggest call from
topics.py and works entirely in Dutch.

The description builder also writes the synthetic-media disclosure line.
Disclosure is what keeps AI-narrated content monetizable; the API flag in
produce.py is the formal declaration, and this is the human-readable half.
"""

import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import GROQ_API_KEY, SCRIPT_MODEL
from scripts.nl.topics import youtube_suggest_nl

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Dutch modifiers that mirror how viewers narrow a search.
_MODIFIERS = ("uitgelegd", "documentaire", "waargebeurd", "hoe werkt", "feiten")

# Dutch function words carry no topical signal, so they are ignored when
# deciding whether a suggestion is actually about the topic.
# Generic verbs are included deliberately: "hoe werken de deltawerken" and
# "hoe werken de longen" share only "werken", and treating that as topical
# relevance pulls lung anatomy into a video about flood defences.
_STOPWORDS = frozenset({
    "de", "het", "een", "van", "en", "in", "op", "te", "voor", "met", "dat",
    "die", "is", "zijn", "wordt", "worden", "hoe", "wat", "waarom", "wie",
    "waar", "wanneer", "welke", "er", "je", "we", "ik", "u", "ze", "hij",
    "werken", "werkt", "werk", "staan", "staat", "komen", "komt", "gaan",
    "gaat", "maken", "maakt", "doen", "doet", "hebben", "heeft", "kunnen",
    "kan", "moeten", "moet", "willen", "wil", "zitten", "zit", "krijgen",
    "gebeurde", "gebeurt", "betekent", "bestaat", "eigenlijk", "echt",
})

# Shorter prefixes than this return generic completions rather than topical
# ones — querying "hoe" yields "hoe maak je een squishy".
_MIN_PREFIX_CHARS = 12

DISCLOSURE_NL = (
    "Deze video gebruikt een AI-stem voor de voice-over. "
    "Research, invalshoek en montage zijn menselijk werk."
)


def _content_words(text: str) -> set[str]:
    """Meaningful words in a phrase, lowercased."""
    return {
        w for w in re.findall(r"[a-zà-ü]+", text.lower())
        if len(w) > 3 and w not in _STOPWORDS
    }


def _is_relevant(suggestion: str, topic_words: set[str]) -> bool:
    """True when a suggestion actually concerns the topic.

    Autocomplete answers whatever prefix it is given, so a query built from
    the topic's leading words still returns completions about something else
    entirely. Without this check those land in the tags and description and
    actively dilute the video's SEO.

    A single shared word is too weak a test on a topic with several content
    words — "waarom staan amsterdamse huizen scheef" and "waarom staan
    amsterdamse psv fan" share "amsterdamse" and nothing else. So richer
    topics require two overlapping words.
    """
    if not topic_words:
        return False
    overlap = _content_words(suggestion) & topic_words
    required = 2 if len(topic_words) >= 3 else 1
    return len(overlap) >= required


def research_terms_nl(topic: str) -> dict:
    """Collect Dutch search terms that are genuinely related to a topic."""
    topic_words = _content_words(topic)
    direct = youtube_suggest_nl(topic)

    related: list[str] = []
    words = topic.split()
    for i in range(2, min(len(words), 5)):
        prefix = " ".join(words[:i])
        if len(prefix) < _MIN_PREFIX_CHARS:
            continue
        related.extend(youtube_suggest_nl(prefix))
        time.sleep(0.2)

    # Modify the full topic, not just its first word: "hoe uitgelegd" is noise.
    for modifier in _MODIFIERS:
        related.extend(youtube_suggest_nl(f"{topic} {modifier}")[:3])
        time.sleep(0.2)

    relevant = [s for s in dict.fromkeys(direct + related)
                if _is_relevant(s, topic_words)]
    return {"direct": direct, "related": relevant[:25], "top": direct[:5]}


def _groq(prompt: str, temperature: float, max_tokens: int) -> str:
    """Single Groq completion, retrying on rate limits.

    The free tier allows 8000 tokens/minute and a video makes three Groq calls
    in quick succession, so a 429 here is routine rather than exceptional.
    Without the retry the title silently falls back to the unoptimised one.
    Raises on any other HTTP failure so the caller can fall back.
    """
    for attempt in range(3):
        response = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": SCRIPT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=90,
        )
        if response.status_code == 429:
            wait = 20 * (attempt + 1)
            print(f"  Groq TPM-limiet, {wait}s wachten (poging {attempt + 1}/3)...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    raise requests.HTTPError("Groq rate limit niet opgelost na 3 pogingen")


def optimize_title_nl(topic: str, current: str, terms: dict) -> list[str]:
    """Generate Dutch title candidates ranked by the model's own ordering."""
    prompt = f"""Je bent een Nederlandse YouTube-SEO-specialist. Verbeter deze titel.

Huidige titel: "{current}"
Onderwerp: {topic}
Wat Nederlanders echt zoeken: {", ".join(terms.get("top", [])[:5])}

Schrijf 5 Nederlandse titelvarianten die:
1. Een echt gezocht Nederlands zoekwoord natuurlijk bevatten
2. Nieuwsgierigheid opwekken zonder te liegen
3. Onder de 70 tekens blijven
4. Het belangrijkste zoekwoord vooraan zetten
5. GEEN hoofdletters-geschreeuw en geen overdreven leestekens gebruiken
6. Natuurlijk Nederlands zijn, geen vertaald Engels

Alleen de titels, genummerd, één per regel."""

    text = _groq(prompt, temperature=0.85, max_tokens=512)
    titles = [
        line.strip().lstrip("0123456789.)- ").strip('"')
        for line in text.splitlines()
        if line.strip()
    ]
    return [t for t in titles if 10 < len(t) <= 100][:5]


def build_description_nl(script: dict, terms: dict) -> str:
    """Assemble the Dutch description: hook, angle, keywords, disclosure."""
    angle = script.get("eigen_invalshoek", "").strip()
    body = script.get("description", "").strip()
    tags = script.get("tags", [])
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])
    related = ", ".join(terms.get("related", [])[:8])

    parts = [body]
    if angle:
        # The angle is the video's original claim — stating it up front helps
        # both the viewer and the "original value" case.
        parts.append(f"De stelling van deze video: {angle}")
    if related:
        parts.append(f"In deze video: {related}.")
    parts.append(hashtags)
    parts.append("―" * 20)
    parts.append(DISCLOSURE_NL)
    parts.append("Vragen of aanvullingen? Zet ze in de reacties — die lees ik.")

    return "\n\n".join(p for p in parts if p).strip()


def optimize_script_seo_nl(script: dict) -> dict:
    """Return a new script dict with Dutch title, description and tags.

    Never mutates the input. On any failure the original fields survive —
    a weaker title is much better than a dead pipeline run.
    """
    optimized = dict(script)
    topic = optimized.get("title", "")
    print(f"\n  Nederlandse SEO: {topic}")

    terms = research_terms_nl(topic)
    print(f"  {len(terms.get('related', []))} verwante zoektermen")

    try:
        titles = optimize_title_nl(topic, topic, terms)
        if titles:
            optimized["title"] = titles[0]
            optimized["title_alternatives"] = titles[1:]
            print(f"  Titel: {optimized['title']}")
    except (requests.RequestException, KeyError) as e:
        print(f"  Titeloptimalisatie overgeslagen: {e}")

    optimized["description"] = build_description_nl(optimized, terms)
    optimized["tags"] = _merge_tags(optimized.get("tags", []), terms)
    print(f"  {len(optimized['tags'])} tags, beschrijving {len(optimized['description'])} tekens")
    return optimized


def _merge_tags(existing: list, terms: dict) -> list[str]:
    """Blend script tags with real Dutch search terms, within YouTube's limits."""
    candidates = list(existing) + terms.get("related", [])
    seen: set[str] = set()
    merged: list[str] = []
    budget = 0
    for tag in candidates:
        tag = str(tag).strip().strip('"').replace("<", "").replace(">", "")
        key = tag.lower()
        if not (2 < len(tag) < 50) or key in seen:
            continue
        # YouTube caps total tag length at 500 characters.
        if budget + len(tag) + 1 > 500:
            break
        seen.add(key)
        merged.append(tag)
        budget += len(tag) + 1
    return merged[:15]
