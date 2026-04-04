"""
Fact Checker — researches every topic online before script generation.
Uses Groq to summarize findings from Wikipedia and other public sources.
Ensures scripts are based on real, verifiable information.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)
from config import GROQ_API_KEY, SCRIPT_MODEL

# Cache research to avoid re-fetching for the same topic
RESEARCH_CACHE_DIR = Path(__file__).parent.parent / "output" / "research_cache"


def search_wikipedia(topic: str) -> str:
    """Search Wikipedia for a topic and return the article summary."""
    try:
        # Search for the most relevant article
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "srlimit": 3,
            "format": "json",
        }
        headers = {"User-Agent": "YouTubePipeline/1.0 (educational research)"}
        resp = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])

        if not results:
            return ""

        # Get the full extract of the top result
        page_title = results[0]["title"]
        extract_params = {
            "action": "query",
            "titles": page_title,
            "prop": "extracts",
            "exintro": False,
            "explaintext": True,
            "exsectionformat": "plain",
            "format": "json",
        }
        resp = requests.get(search_url, params=extract_params, headers=headers, timeout=10)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})

        for page_id, page_data in pages.items():
            extract = page_data.get("extract", "")
            if extract:
                # Truncate to ~3000 chars to fit in LLM context
                return f"SOURCE: Wikipedia — {page_title}\n\n{extract[:3000]}"

        return ""
    except Exception as e:
        print(f"  Wikipedia search failed: {e}")
        return ""


def search_duckduckgo(topic: str) -> str:
    """Search DuckDuckGo instant answers for quick facts."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": topic,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        parts = []
        if data.get("Abstract"):
            parts.append(f"SOURCE: {data.get('AbstractSource', 'DuckDuckGo')}\n{data['Abstract']}")
        if data.get("RelatedTopics"):
            for rt in data["RelatedTopics"][:5]:
                if isinstance(rt, dict) and rt.get("Text"):
                    parts.append(f"- {rt['Text'][:200]}")

        return "\n".join(parts) if parts else ""
    except Exception:
        return ""


def research_topic(topic: str) -> str:
    """Research a topic using multiple free public sources.
    Returns a compiled research brief with verified facts.
    """
    # Check cache first
    RESEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = re.sub(r"[^a-z0-9]+", "_", topic.lower())[:60]
    cache_file = RESEARCH_CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        with open(cache_file) as f:
            cached = json.load(f)
        print(f"  Using cached research for: {topic}")
        return cached.get("brief", "")

    print(f"  Researching: {topic}...")

    # Gather raw info from multiple sources
    raw_sources = []

    # Wikipedia
    wiki = search_wikipedia(topic)
    if wiki:
        raw_sources.append(wiki)
        print(f"  Found Wikipedia article")

    # Also search with key terms extracted
    key_terms = [w for w in topic.split() if len(w) > 3 and w[0].isupper()]
    if key_terms and len(key_terms) > 1:
        alt_query = " ".join(key_terms[:3])
        if alt_query.lower() != topic.lower():
            wiki2 = search_wikipedia(alt_query)
            if wiki2 and wiki2 != wiki:
                raw_sources.append(wiki2)
                print(f"  Found additional Wikipedia source")

    # DuckDuckGo
    ddg = search_duckduckgo(topic)
    if ddg:
        raw_sources.append(ddg)
        print(f"  Found DuckDuckGo results")

    if not raw_sources:
        print(f"  No online sources found — script will use LLM knowledge only")
        return ""

    # Use Groq to extract and verify key facts from raw sources
    combined_sources = "\n\n---\n\n".join(raw_sources)

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
                "content": "You are a fact-checker. Extract ONLY verified, factual information from the sources provided. Do NOT add information that isn't in the sources. List key facts as bullet points with dates, names, and specific details.",
            },
            {
                "role": "user",
                "content": f"Extract verified facts about '{topic}' from these sources. Only include facts that are clearly stated in the sources:\n\n{combined_sources}",
            },
        ],
        "temperature": 0.1,  # low temp for factual accuracy
        "max_tokens": 2048,
    }

    for attempt in range(3):
        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        resp.raise_for_status()
        break
    else:
        return ""

    brief = resp.json()["choices"][0]["message"]["content"]

    # Cache the result
    with open(cache_file, "w") as f:
        json.dump({"topic": topic, "brief": brief, "source_count": len(raw_sources)}, f, indent=2)

    print(f"  Research complete: {len(brief.split())} words of verified facts")
    return brief


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "The Dyatlov Pass Incident"
    print(f"Researching: {topic}\n")
    brief = research_topic(topic)
    print(f"\n{brief}")
