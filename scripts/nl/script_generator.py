"""
Dutch script generation.

Two things make this different from the English scripts/script_generator.py:

1. The narration is Dutch but ``visual_keywords`` must stay ENGLISH. Pexels'
   library is indexed in English; Dutch queries return almost nothing, which
   silently degrades every video to gradient fallbacks.

2. Every script must commit to an ``eigen_invalshoek`` — a specific arguable
   position the video defends, not a neutral recitation. This is the
   "original value" prong of YouTube's inauthentic-content policy: a video
   that only restates retrievable facts in synthetic narration is exactly
   what the policy demonetizes. A video that argues something is not.

The hook shape, narrative architecture and section count all come from the
per-video VideoVariant, so no two scripts share a skeleton.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import (
    GROQ_API_KEY,
    NL_SECTION_WORD_TOLERANCE,
    NL_TARGET_VIDEO_LENGTH_MINUTES,
    NL_WORDS_PER_MINUTE,
    SCRIPT_MODEL,
)
from scripts.nl.research import research_topic_nl
from scripts.nl.variation import VideoVariant

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """Je bent een Nederlandstalige YouTube-scriptschrijver. Je schrijft
voor een kanaal dat Nederlandse kijkers vasthoudt met hoog tempo, harde feiten en
een duidelijke eigen mening.

Toon:
- Spreektaal, geen schrijftaal. Zoals een slimme vriend die iets uitlegt in de kroeg.
- Korte zinnen. Gemiddeld onder de 14 woorden.
- Direct. Geen "welkom bij dit kanaal", geen "in deze video gaan we kijken naar".
- Nederlands van Nederland, geen vertaald Engels. Vermijd anglicismen.
- Je mag stellig zijn, maar nooit feiten verzinnen.

Structuur:
- Elke sectie eindigt met iets dat de kijker dwingt door te kijken.
- Concrete cijfers, jaartallen en namen — die houden mensen vast.
- Geen opsomming zonder standpunt. Het script verdedigt een these.

KRITIEK — visual_keywords:
- Deze worden gebruikt om op Pexels.com naar STOCK VIDEO te zoeken.
- Pexels is in het ENGELS geïndexeerd. Schrijf de keywords dus in het ENGELS,
  ook al is de narration Nederlands. Nederlandse keywords leveren niets op.
- Wees specifiek en filmbaar: "flooded street aerial" niet "disaster",
  "dutch canal houses" niet "Netherlands".
- Kies beelden die echt bestaan als stockmateriaal. Geen historische archiefbeelden.
- 2 tot 3 keywords per sectie.

KRITIEK — eigen_invalshoek:
- Dit is de these die de video verdedigt. Eén zin, stellig, aanvechtbaar.
- Niet: "de watersnood was een ramp". Wel: "de watersnood was geen natuurramp
  maar een bezuinigingsramp die al twintig jaar was aangekondigd".
- Elke sectie moet aan die these bijdragen.

OUTPUT — antwoord met UITSLUITEND geldige JSON, geen markdown:
{
  "title": "Nederlandse titel, onder 70 tekens, geen clickbait-leugens",
  "description": "Nederlandse beschrijving met zoekwoorden",
  "tags": ["nederlandse tag", "tag2"],
  "eigen_invalshoek": "De these die deze video verdedigt, één zin",
  "hook": "De eerste 2 zinnen — Nederlands, stopt het scrollen",
  "short_hook": "2-5 woorden Nederlands voor tekstoverlay in de Short",
  "sections": [
    {
      "section_title": "Naam van de sectie (niet in beeld, alleen ordening)",
      "narration": "De daadwerkelijke Nederlandse narratietekst",
      "visual_keywords": ["english keyword", "english keyword"]
    }
  ],
  "thumbnail_text": "2-4 Nederlandse woorden voor de thumbnail"
}"""

# Phrases that signal the model padded because it had no grounding.
_FILLER_NL = (
    "er is weinig bekend",
    "de details zijn schaars",
    "dit blijft onduidelijk",
    "volgens sommige bronnen",
    "het precieze verloop is onbekend",
    "daar is geen informatie over",
)

# Anglicisms that betray English-brain output rather than native Dutch.
_ANGLICISMS = ("awesome", "insane", "crazy", "literally", "basically", "actually")


# Sentence boundary: terminal punctuation followed by a capitalised word. The
# capital is what keeps "ca. 22 meter" and "nr. 4" from splitting mid-sentence.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[\"\'“(]?[A-ZÀ-Þ])")

# Abbreviations that end in a dot and legitimately precede a capitalised word,
# which the regex above cannot tell apart from a real sentence end.
_ABBREVIATIONS = frozenset({
    "bijv.", "bijz.", "ca.", "dhr.", "dr.", "drs.", "enz.", "etc.", "evt.",
    "excl.", "fig.", "incl.", "ing.", "ir.", "mevr.", "mln.", "mld.", "nl.",
    "nr.", "o.a.", "ong.", "prof.", "resp.", "St.", "zgn.",
})


def section_word_budget(variant: VideoVariant) -> int:
    """Words of narration each section may keep.

    Sized so ``section_count`` sections add up to the target runtime at the
    measured Dutch TTS rate. The floor of 100 stops a high section count from
    producing sections too short to say anything.
    """
    target_words = NL_TARGET_VIDEO_LENGTH_MINUTES * NL_WORDS_PER_MINUTE
    return max(100, target_words // max(1, variant.section_count))


def _split_sentences(text: str) -> list[str]:
    """Split Dutch prose into sentences, keeping abbreviations intact."""
    parts = _SENTENCE_BREAK.split(text)

    merged: list[str] = []
    for part in parts:
        last_word = merged[-1].split()[-1].lower() if merged and merged[-1].split() else ""
        if merged and last_word in _ABBREVIATIONS:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


def trim_sections_to_budget(sections: list[dict], ceiling: int) -> list[dict]:
    """Return sections whose narration fits ``ceiling`` words, cut at sentences.

    The prompt asks for a word band and the model ignores it — a stated ceiling
    of 193 came back as 406 words per section, a 30-minute video. Runtime is
    revenue-critical in both directions: under 8 minutes YouTube serves no
    mid-rolls, and much past ~12 minutes retention collapses on a faceless
    channel. So the budget is enforced here rather than requested in the prompt.

    A section is never emptied: if its opening sentence alone busts the budget
    it is kept whole, because a section with no narration would desync the
    section-to-footage mapping downstream.
    """
    trimmed: list[dict] = []
    for section in sections:
        narration = section.get("narration", "")
        if not narration.strip() or len(narration.split()) <= ceiling:
            trimmed.append(section)
            continue

        kept: list[str] = []
        used = 0
        for sentence in _split_sentences(narration):
            cost = len(sentence.split())
            if kept and used + cost > ceiling:
                break
            kept.append(sentence)
            used += cost

        trimmed.append({**section, "narration": " ".join(kept)})
    return trimmed


def _build_user_prompt(topic: str, variant: VideoVariant, research: str) -> str:
    """Assemble the per-video prompt from the variant's rotation choices."""
    target_words = NL_TARGET_VIDEO_LENGTH_MINUTES * NL_WORDS_PER_MINUTE

    grounding = (
        f"\n\nGEVERIFIEERDE FEITEN — baseer het script hierop. Verzin niets:\n{research}"
        if research
        else "\n\nLET OP: er zijn geen bronnen gevonden. Blijf strikt bij wat je "
        "zeker weet en schrijf liever korter dan dat je details verzint."
    )

    floor = section_word_budget(variant)
    ceiling = int(floor * NL_SECTION_WORD_TOLERANCE)

    return f"""Schrijf een Nederlands YouTube-script over: {topic}

LENGTE — dit is een harde eis, geen richtlijn:
- Exact {variant.section_count} secties.
- ELKE sectie tussen {floor} en {ceiling} woorden narratie. Tel ze.
- Totaal dus ongeveer {target_words} woorden (~{NL_TARGET_VIDEO_LENGTH_MINUTES} minuten spreektijd).
- Een sectie van drie zinnen is te kort en onbruikbaar. Werk elk punt uit met
  een concreet voorbeeld, een cijfer, of een gevolg voor de kijker.
- Ga ook niet over {ceiling} woorden per sectie heen: langer is niet beter,
  het verslapt het tempo.

HOOK-OPDRACHT ({variant.hook.name}):
{variant.hook.instruction}

STRUCTUUR-OPDRACHT ({variant.structure.name}):
{variant.structure.instruction}
{grounding}

Onthoud:
- Bepaal eerst je eigen_invalshoek, schrijf daarna de secties die hem onderbouwen.
- visual_keywords in het ENGELS, narration in het NEDERLANDS.
- Geen verzonnen feiten. Twijfel je? Laat het weg.
- Geen begroeting, geen "vergeet niet te abonneren" in de narratie zelf.

Antwoord met UITSLUITEND het JSON-object."""


def generate_script_nl(topic: str, variant: VideoVariant) -> dict:
    """Generate a Dutch script shaped by ``variant``.

    Raises RuntimeError if Groq stays rate-limited across all retries, so the
    caller can skip the topic rather than upload a half-built video.
    """
    research = research_topic_nl(topic)
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(topic, variant, research)},
        ],
        # Slightly warmer than the English pipeline's 0.6: the variant already
        # pins structure, so temperature can buy phrasing variety safely.
        "temperature": 0.75,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=120)
        if response.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"  Groq rate limit, {wait}s wachten (poging {attempt + 1}/3)...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError("Groq rate limit niet opgelost na 3 pogingen")

    script = json.loads(response.json()["choices"][0]["message"]["content"])

    budget = section_word_budget(variant)
    before = sum(len(x.get("narration", "").split()) for x in script.get("sections", []))
    script = {
        **script,
        "sections": trim_sections_to_budget(script.get("sections", []), budget),
    }
    after = sum(len(x.get("narration", "").split()) for x in script["sections"])
    if after < before:
        print(f"  Ingekort: {before} -> {after} woorden (budget {budget}/sectie)")

    return _validate_nl(script, variant)


def full_narration_nl(script: dict) -> str:
    """Concatenate hook + all section narration into one string."""
    parts = [script.get("hook", "")]
    parts += [s.get("narration", "") for s in script.get("sections", [])]
    return "\n\n".join(p for p in parts if p)


def _validate_nl(script: dict, variant: VideoVariant) -> dict:
    """Quality-gate and sanitize. Returns a new dict; never mutates the input."""
    checked = dict(script)
    narration = full_narration_nl(checked).lower()

    filler = [p for p in _FILLER_NL if p in narration]
    if len(filler) >= 3:
        print(f"  WAARSCHUWING: {len(filler)} vulzinnen — script is slecht gegrond.")

    anglicisms = [w for w in _ANGLICISMS if re.search(rf"\b{w}\b", narration)]
    if anglicisms:
        print(f"  WAARSCHUWING: anglicismen gevonden: {', '.join(anglicisms)}")

    if not checked.get("eigen_invalshoek", "").strip():
        print("  WAARSCHUWING: geen eigen invalshoek — dit is precies wat het "
              "inauthentic-content beleid afstraft.")

    # Dates and proper nouns are the retention backbone; flag when thin.
    dates = re.findall(r"\b(1[5-9]\d{2}|20[0-4]\d)\b", narration)
    if len(dates) < 3:
        print(f"  WAARSCHUWING: lage feitdichtheid (jaartallen={len(dates)}).")

    sections = checked.get("sections", [])
    if len(sections) != variant.section_count:
        print(f"  Let op: {len(sections)} secties, {variant.section_count} gevraagd.")

    # Pexels is English-indexed — a Dutch keyword that slips through costs a
    # whole section its footage, so surface it loudly.
    dutch_leak = _detect_dutch_keywords(sections)
    if dutch_leak:
        print(f"  WAARSCHUWING: Nederlandse visual_keywords: {', '.join(dutch_leak[:5])}")

    checked["tags"] = _clean_tags(checked.get("tags", []))
    checked["description"] = re.sub(
        r"\d{1,2}:\d{2}\s*[-–—]\s*", "", checked.get("description", "")
    ).strip()
    return checked


# Dutch words that are NOT also valid English words. Membership here must be
# exclusive: "water", "van", "boot" and "polder" are all real English too, and
# including them flagged perfectly good keywords like "river water level gauge"
# as Dutch. A false positive here is worse than a miss — it trains you to
# ignore the warning.
_DUTCH_MARKERS = frozenset({
    "het", "een", "en", "met", "voor", "door", "bij", "naar", "voorbij",
    "huis", "huizen", "straat", "stad", "dorp", "fiets", "fietsen",
    "molen", "molens", "dijk", "dijken", "gracht", "grachten", "brug",
    "kerk", "lucht", "zee", "wolken", "weiland", "sneeuw", "regen",
    "nacht", "ochtend", "zonsondergang", "landschap", "gebouw",
})


def _detect_dutch_keywords(sections: list) -> list[str]:
    """Find visual_keywords that look Dutch rather than English."""
    leaked = []
    for section in sections:
        for keyword in section.get("visual_keywords", []):
            words = {w.lower() for w in re.findall(r"[a-zA-Zé]+", str(keyword))}
            if words & _DUTCH_MARKERS:
                leaked.append(str(keyword))
    return leaked


def _clean_tags(tags: list) -> list[str]:
    """Strip punctuation, drop Dutch stopwords, dedupe, cap at 15."""
    stop = {"de", "het", "een", "van", "en", "of", "in", "op", "te", "voor", "met"}
    seen: set[str] = set()
    cleaned: list[str] = []
    for tag in tags:
        tag = re.sub(r"[^a-zA-Z0-9\sàáäèéëïíöóüú-]", "", str(tag)).strip()
        key = tag.lower()
        if len(tag) > 2 and key not in stop and key not in seen:
            seen.add(key)
            cleaned.append(tag)
    return cleaned[:15]


def save_script(script: dict, output_path: Path) -> Path:
    """Write the script JSON to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(script, indent=2, ensure_ascii=False))
    return output_path
