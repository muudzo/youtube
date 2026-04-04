"""
Topic Researcher — AI-powered trending topic discovery.
Finds viral-potential topics in your niche using Groq.
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)
from config import GROQ_API_KEY, SCRIPT_MODEL


def research_topics(niche: str = "dark history mysteries rabbit holes", count: int = 10) -> list:
    """Generate trending, high-CTR topic ideas for the niche."""

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
                "content": """You are a YouTube growth strategist specializing in faceless channels.
You find topics that maximize clicks, watch time, and subscriber growth.

Rules for topic selection:
- Use CURIOSITY GAP framing ("The X that Y" — makes people NEED to click)
- Pick topics with built-in mystery or shock value
- Avoid oversaturated topics (no Bermuda Triangle, no Area 51)
- Focus on lesser-known but fascinating stories
- Each topic should work as both a 10-min video AND a 60s Short
- Topics should be searchable (people actually Google these)

Return a JSON array of objects with:
[{"title": "curiosity gap title", "why": "why this will get clicks", "search_volume": "high/medium/low"}]""",
            },
            {
                "role": "user",
                "content": f"Generate {count} viral topic ideas for a faceless YouTube channel in the niche: {niche}\n\nFocus on topics that are trending RIGHT NOW or have evergreen search volume. Return ONLY the JSON array.",
            },
        ],
        "temperature": 0.9,
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

    # Handle both {"topics": [...]} and direct [...] formats
    if isinstance(result, dict):
        topics = result.get("topics", result.get("ideas", list(result.values())[0]))
    else:
        topics = result

    return topics


def save_topics(topics: list, output_path: Path = None) -> Path:
    """Save researched topics to a file."""
    if output_path is None:
        output_path = Path("output") / "researched_topics.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(topics, f, indent=2)
    return output_path


def topics_to_txt(topics: list, output_path: Path = None) -> Path:
    """Convert topics to the topics.txt format for batch processing."""
    if output_path is None:
        output_path = Path("topics_generated.txt")
    lines = ["# Auto-generated trending topics\n"]
    for t in topics:
        title = t["title"] if isinstance(t, dict) else t
        lines.append(title)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    return output_path


if __name__ == "__main__":
    print("Researching trending topics...")
    topics = research_topics(count=10)
    for i, t in enumerate(topics, 1):
        title = t["title"] if isinstance(t, dict) else t
        why = t.get("why", "") if isinstance(t, dict) else ""
        print(f"  {i}. {title}")
        if why:
            print(f"     → {why}")
    save_topics(topics)
    topics_to_txt(topics)
    print(f"\nSaved {len(topics)} topics")
