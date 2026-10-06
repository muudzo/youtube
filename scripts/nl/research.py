"""
Dutch-language fact research.

The shared scripts/fact_checker.py is hardcoded to en.wikipedia.org. Dutch
topics — Nederlandse geschiedenis, lokale rampen, wetgeving — are frequently
better covered on nl.wikipedia, and the Dutch article carries the Dutch proper
nouns and spellings the narration needs. So this searches nl first and only
falls back to en when nl has nothing.

Scripts are grounded in retrieved facts rather than model recall. That serves
retention (specifics hold viewers) and it is also the difference between a
video with original informational value and one that reads as filler.
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

WIKI_HEADERS = {"User-Agent": "NLBrainrotPipeline/1.0 (educational research)"}
_EXTRACT_CHARS = 3500


def _wiki_search(topic: str, lang: str) -> str:
    """Fetch the best-matching article extract from a language's Wikipedia.

    Returns an empty string on any failure — research is best-effort, and a
    Wikipedia outage should degrade script quality, not kill the run.
    """
    api = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        hits = requests.get(
            api,
            params={
                "action": "query",
                "list": "search",
                "srsearch": topic,
                "srlimit": 3,
                "format": "json",
            },
            headers=WIKI_HEADERS,
            timeout=10,
        )
        hits.raise_for_status()
        results = hits.json().get("query", {}).get("search", [])
        if not results:
            return ""

        title = results[0]["title"]
        page = requests.get(
            api,
            params={
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "explaintext": True,
                "exsectionformat": "plain",
                "format": "json",
            },
            headers=WIKI_HEADERS,
            timeout=10,
        )
        page.raise_for_status()
        for data in page.json().get("query", {}).get("pages", {}).values():
            extract = data.get("extract", "")
            if extract:
                label = "Wikipedia NL" if lang == "nl" else "Wikipedia EN"
                return f"BRON: {label} — {title}\n\n{extract[:_EXTRACT_CHARS]}"
        return ""
    except requests.RequestException as e:
        print(f"  Wikipedia ({lang}) mislukt: {e}")
        return ""


def research_topic_nl(topic: str) -> str:
    """Gather verifiable facts for a Dutch topic.

    Tries nl.wikipedia, then en.wikipedia. Returns a combined brief, or an
    empty string if nothing was found (the caller decides whether to proceed).
    """
    print(f"  Feiten zoeken voor: {topic}")

    nl = _wiki_search(topic, "nl")
    if nl:
        print(f"  nl.wikipedia: {len(nl)} tekens")

    # Always try EN too — it often carries figures and dates the NL article omits.
    en = _wiki_search(topic, "en")
    if en:
        print(f"  en.wikipedia: {len(en)} tekens")

    brief = "\n\n---\n\n".join(part for part in (nl, en) if part)
    if not brief:
        print("  WAARSCHUWING: geen bronnen gevonden — script wordt niet gegrond.")
    return brief


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Watersnoodramp 1953"
    print(research_topic_nl(query)[:1200])
