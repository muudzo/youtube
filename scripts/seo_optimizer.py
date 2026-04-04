"""
YouTube SEO Optimizer — maximize discoverability for free.

Optimizes: titles, descriptions, tags, hashtags, and upload timing.
Uses YouTube autocomplete (free) to find what people actually search for.
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)
from config import GROQ_API_KEY, SCRIPT_MODEL


# ══════════════════════════════════════════════════════════
# 1. YOUTUBE AUTOCOMPLETE — find what people actually search
# ══════════════════════════════════════════════════════════

def get_youtube_suggestions(query: str) -> list:
    """Get YouTube search autocomplete suggestions — this is what people are typing."""
    try:
        url = "https://suggestqueries-clients6.youtube.com/complete/search"
        params = {
            "client": "youtube",
            "q": query,
            "ds": "yt",
        }
        resp = requests.get(url, params=params, timeout=10)
        # Response is JSONP, need to extract JSON
        text = resp.text
        # Extract the JSON array from the JSONP callback
        match = re.search(r'\[.*\]', text)
        if match:
            data = json.loads(match.group())
            if len(data) > 1 and isinstance(data[1], list):
                suggestions = [item[0] if isinstance(item, list) else item for item in data[1]]
                return suggestions[:10]
    except Exception as e:
        print(f"  Autocomplete failed: {e}")
    return []


def research_search_terms(topic: str) -> dict:
    """Find the best search terms for a topic using YouTube autocomplete."""
    print(f"  Researching search terms for: {topic}")

    # Get direct suggestions
    direct = get_youtube_suggestions(topic)

    # Get partial suggestions (what people type before completing)
    words = topic.split()
    partial_suggestions = []
    for i in range(1, min(len(words), 4)):
        partial = " ".join(words[:i])
        sug = get_youtube_suggestions(partial)
        partial_suggestions.extend(sug)

    # Get "topic + modifier" suggestions
    modifiers = ["explained", "documentary", "true story", "what happened", "mystery", "full story"]
    modifier_suggestions = []
    for mod in modifiers:
        sug = get_youtube_suggestions(f"{topic.split()[0]} {mod}")
        modifier_suggestions.extend(sug[:3])

    all_suggestions = list(set(direct + partial_suggestions + modifier_suggestions))

    return {
        "direct": direct,
        "related": all_suggestions[:20],
        "top_terms": direct[:5],
    }


# ══════════════════════════════════════════════════════════
# 2. TITLE OPTIMIZER — craft the most clickable title
# ══════════════════════════════════════════════════════════

def optimize_title(topic: str, current_title: str, search_data: dict = None) -> list:
    """Generate SEO-optimized title variations."""
    if not search_data:
        search_data = research_search_terms(topic)

    top_terms = ", ".join(search_data.get("top_terms", [])[:5])

    prompt = f"""You are a YouTube SEO expert. Optimize this video title for maximum clicks AND search ranking.

Current title: "{current_title}"
Topic: {topic}
What people search on YouTube: {top_terms}

Write 5 title variations that:
1. Include a high-volume search term naturally
2. Use curiosity gap (make people NEED to click)
3. Are under 70 characters (YouTube truncates longer ones)
4. Front-load the most important keyword (YouTube weighs first words more)
5. Do NOT use ALL CAPS or excessive punctuation

Format: numbered list, one per line. Just the titles, nothing else."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 512,
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]

    titles = [line.strip().lstrip("0123456789.)-) ") for line in text.strip().split("\n") if line.strip()]
    return titles[:5]


# ══════════════════════════════════════════════════════════
# 3. DESCRIPTION OPTIMIZER — keyword-rich descriptions
# ══════════════════════════════════════════════════════════

def optimize_description(topic: str, current_desc: str, search_data: dict = None) -> str:
    """Generate an SEO-optimized description."""
    if not search_data:
        search_data = research_search_terms(topic)

    related = ", ".join(search_data.get("related", [])[:10])

    prompt = f"""Write an SEO-optimized YouTube video description for a video about: {topic}

Current description: "{current_desc}"

Related search terms to include naturally: {related}

Rules:
- First 2 lines are the most important (shown before "Show more")
- Include the main keyword in the first sentence
- 150-300 words total
- Include 3-5 relevant hashtags at the end
- Add a call to action (subscribe, comment, etc.)
- Include timestamps if possible (make up logical ones based on the topic)
- Do NOT stuff keywords unnaturally

Just return the description text, nothing else."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ══════════════════════════════════════════════════════════
# 4. TAG GENERATOR — maximize discoverability
# ══════════════════════════════════════════════════════════

def generate_tags(topic: str, search_data: dict = None) -> list:
    """Generate optimized tags from search data."""
    if not search_data:
        search_data = research_search_terms(topic)

    tags = set()

    # Add direct search suggestions as tags
    for term in search_data.get("direct", []):
        tags.add(term.lower())

    # Add related terms
    for term in search_data.get("related", []):
        if len(term) < 50:  # YouTube tag limit
            tags.add(term.lower())

    # Add topic words and combinations
    words = topic.lower().split()
    tags.add(topic.lower())
    for i in range(len(words)):
        for j in range(i + 1, min(i + 4, len(words) + 1)):
            phrase = " ".join(words[i:j])
            if len(phrase) > 2:
                tags.add(phrase)

    # Add standard niche tags
    niche_tags = ["dark history", "unsolved mysteries", "true story",
                  "documentary", "rabbit hole", "conspiracy", "history"]
    tags.update(niche_tags)

    # Clean tags — YouTube rejects special characters and angle brackets
    cleaned_tags = set()
    for tag in tags:
        # Remove characters YouTube doesn't allow in tags
        tag = re.sub(r'[<>]', '', tag)
        tag = tag.strip().strip('"').strip("'")
        if tag and len(tag) > 1 and len(tag) < 50:
            cleaned_tags.add(tag)

    # YouTube allows max 500 chars total in tags
    sorted_tags = sorted(cleaned_tags, key=len)
    final_tags = []
    total_chars = 0
    for tag in sorted_tags:
        if total_chars + len(tag) + 1 <= 500:
            final_tags.append(tag)
            total_chars += len(tag) + 1

    return final_tags


# ══════════════════════════════════════════════════════════
# 5. FULL SEO OPTIMIZATION — run on a script before upload
# ══════════════════════════════════════════════════════════

def optimize_script_seo(script: dict) -> dict:
    """Take a generated script and optimize all SEO fields."""
    topic = script.get("title", "")
    print(f"\n  SEO Optimizing: {topic}")

    # Research what people search for
    search_data = research_search_terms(topic)
    print(f"  Found {len(search_data.get('related', []))} related search terms")

    # Optimize title
    titles = optimize_title(topic, script.get("title", ""), search_data)
    if titles:
        script["title"] = titles[0]  # Use the top suggestion
        script["title_alternatives"] = titles[1:]
        print(f"  Optimized title: {script['title']}")

    # Optimize description
    optimized_desc = optimize_description(topic, script.get("description", ""), search_data)
    script["description"] = optimized_desc
    print(f"  Optimized description ({len(optimized_desc)} chars)")

    # Optimize tags
    tags = generate_tags(topic, search_data)
    script["tags"] = tags
    print(f"  Generated {len(tags)} SEO tags")

    return script


# ══════════════════════════════════════════════════════════
# 6. BEST UPLOAD TIMES
# ══════════════════════════════════════════════════════════

def get_best_upload_time() -> str:
    """Suggest the best upload time based on YouTube data."""
    # Best times based on YouTube analytics research:
    # - US audience: 2-4 PM EST (peak browse time)
    # - Global: Friday and Saturday have highest engagement
    # - Shorts: evenings perform best (6-9 PM local)

    now = datetime.now()
    day = now.strftime("%A")

    best_times = {
        "Monday": "2:00 PM EST — start of week, people browsing",
        "Tuesday": "2:00 PM EST — high engagement day",
        "Wednesday": "2:00 PM EST — midweek peak",
        "Thursday": "12:00 PM EST — pre-weekend browsing starts",
        "Friday": "3:00 PM EST — best day for watch time",
        "Saturday": "9:00 AM EST — weekend binge watchers",
        "Sunday": "9:00 AM EST — weekend binge watchers",
    }

    return best_times.get(day, "2:00 PM EST")


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube SEO Optimizer")
    parser.add_argument("action", choices=["research", "title", "description", "tags", "full", "upload-time"])
    parser.add_argument("--topic", required=False, help="Topic to optimize for")

    args = parser.parse_args()

    if args.action == "research":
        data = research_search_terms(args.topic or "dark history")
        print("\nTop search terms:")
        for term in data["top_terms"]:
            print(f"  • {term}")
        print(f"\nRelated ({len(data['related'])} terms):")
        for term in data["related"][:15]:
            print(f"  • {term}")

    elif args.action == "title":
        titles = optimize_title(args.topic or "dark history", args.topic or "dark history")
        print("\nOptimized titles:")
        for i, t in enumerate(titles, 1):
            print(f"  {i}. {t}")

    elif args.action == "tags":
        tags = generate_tags(args.topic or "dark history")
        print(f"\nTags ({len(tags)}):")
        print(", ".join(tags))

    elif args.action == "upload-time":
        print(f"\nBest upload time today: {get_best_upload_time()}")

    elif args.action == "full":
        data = research_search_terms(args.topic or "dark history")
        print(f"\nSearch terms: {len(data['related'])}")
        titles = optimize_title(args.topic, args.topic, data)
        print(f"\nBest title: {titles[0]}")
        tags = generate_tags(args.topic, data)
        print(f"Tags: {len(tags)}")
        desc = optimize_description(args.topic, "", data)
        print(f"\nDescription:\n{desc}")
        print(f"\nBest upload time: {get_best_upload_time()}")
