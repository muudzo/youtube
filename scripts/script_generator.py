"""
Script Generator — generates narration scripts for Dark History / Rabbit Hole videos.
Uses Groq (FREE) with Llama 3.3 70B for fast, high-quality scripts.
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GROQ_API_KEY, SCRIPT_MODEL, TARGET_VIDEO_LENGTH_MINUTES, WORDS_PER_MINUTE

SYSTEM_PROMPT = """You are an expert YouTube scriptwriter specializing in betrayal stories,
revenge narratives, dark history, and true stories that shock. You write scripts that are:

- Hook-heavy: First 10 seconds must be impossible to skip
- Conversational but authoritative — like a smart friend telling you something insane
- Full of "wait, it gets worse" moments to maintain retention
- Structured with mini-cliffhangers every 60-90 seconds
- Factually accurate but presented in the most compelling way possible

You write for faceless YouTube channels with narration over stock footage.

CRITICAL — visual_keywords rules:
- Keywords are used to search Pexels.com for stock VIDEO footage
- They MUST match the cultural/geographic context of the story
- For African stories: use "Africa", "African village", "African landscape", "savanna", "African city" etc.
- For Zimbabwe stories: use "Zimbabwe", "African prison", "African landscape", "savanna sunset", "African drums", "colonial Africa", "African market" etc.
- NEVER use generic Western keywords for non-Western stories
- Be specific: "prison cell bars" not just "prison", "dusty African road" not just "road"
- Each section needs 2-3 keywords that a stock footage site would actually have

OUTPUT FORMAT — respond with ONLY valid JSON, no markdown:
{
  "title": "YouTube title (clickable but not clickbait)",
  "description": "YouTube description with keywords",
  "tags": ["tag1", "tag2"],
  "hook": "The first 2 sentences — the hook that stops the scroll",
  "sections": [
    {
      "section_title": "Section name (not shown in video, for organization)",
      "narration": "The actual narration text for this section",
      "visual_keywords": ["keyword1", "keyword2"]
    }
  ],
  "thumbnail_text": "Short punchy text for thumbnail (2-5 words)"
}"""


def _load_research(topic: str) -> str:
    """Check if we have researched facts for this topic."""
    research_file = Path(__file__).parent.parent / "assets" / "zim_research.json"
    if not research_file.exists():
        return ""

    import json as _json
    with open(research_file) as f:
        research = _json.load(f)

    topic_lower = topic.lower()
    for key, data in research.items():
        # Match if any keyword from the research key appears in the topic
        key_words = key.replace("_", " ").split()
        if any(word in topic_lower for word in key_words if len(word) > 3):
            facts = data.get("key_facts", [])
            hook = data.get("hook", "")
            context = f"\n\nVERIFIED FACTS — use these as the basis for the script, do NOT make up details:\n"
            if hook:
                context += f"Suggested hook: {hook}\n"
            context += "\n".join(f"- {f}" for f in facts)
            return context

    return ""


def generate_script(topic: str, style: str = "documentary") -> dict:
    """Generate a full video script from a topic using Groq.

    Automatically fact-checks every topic before writing:
    1. Checks local research file (assets/zim_research.json)
    2. Searches Wikipedia + DuckDuckGo for verified facts
    3. Feeds verified facts into the script prompt
    """
    from scripts.fact_checker import research_topic

    target_words = TARGET_VIDEO_LENGTH_MINUTES * WORDS_PER_MINUTE

    # Step 1: Check local research (Zim stories, etc.)
    local_research = _load_research(topic)

    # Step 2: ALWAYS research online — combine with local
    online_research = ""
    print("  Fact-checking online sources...")
    online_brief = research_topic(topic)
    if online_brief:
        online_research = f"\n\nVERIFIED FACTS FROM ONLINE SOURCES — base your script on these, do NOT make up details:\n{online_brief}"

    # Combine both sources
    research = local_research + online_research
    if not research.strip():
        print("  WARNING: No verified facts found. Script quality may be low.")

    user_prompt = f"""Create a YouTube script about: {topic}

Style: {style}
Target length: ~{target_words} words of narration (about {TARGET_VIDEO_LENGTH_MINUTES} minutes)

Break it into 6-10 sections. Each section should have its own mini-arc.
Include visual keywords for each section so we can find matching stock footage.
{research}

Remember:
- Start with an absolute banger hook
- Every section should end with something that makes viewers need to hear the next part
- Include specific dates, names, and details for credibility
- End with a mind-blowing conclusion or unresolved mystery
- Do NOT invent facts — only use verified information from the sources above
- If you're unsure about a detail, present it as "according to reports" or "some historians believe"

Respond with ONLY the JSON object, no markdown code blocks."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }

    # Retry with backoff for rate limits
    for attempt in range(3):
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1}/3)...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        break
    else:
        raise Exception("Groq API rate limit — try again in a minute")

    data = response.json()
    text = data["choices"][0]["message"]["content"]

    script = json.loads(text)

    # ── Quality gate: reject scripts with no substance ──
    script = _validate_and_sanitize(script, topic)

    return script


def _validate_and_sanitize(script: dict, topic: str) -> dict:
    """Quality gate — reject filler, sanitize tags, validate descriptions."""
    narration = get_full_narration(script)
    words = narration.split()

    # Check for filler phrases that signal the LLM had nothing real
    filler_phrases = [
        "we don't have verified",
        "information is limited",
        "details are scarce",
        "according to some reports",
        "the exact details remain unclear",
        "not much is known",
    ]
    filler_count = sum(1 for phrase in filler_phrases if phrase in narration.lower())
    if filler_count >= 3:
        print(f"  WARNING: Script has {filler_count} filler phrases — low quality")

    # Count specific facts (names, dates, places)
    import re
    # Dates like 1959, 2003, January, March etc.
    dates = re.findall(r'\b(1[89]\d{2}|20[0-2]\d|January|February|March|April|May|June|July|August|September|October|November|December)\b', narration)
    # Proper nouns (capitalized words not at start of sentence)
    proper_nouns = re.findall(r'(?<!\. )\b[A-Z][a-z]{2,}\b', narration)

    fact_score = len(dates) + len(set(proper_nouns)) // 3
    if fact_score < 3:
        print(f"  WARNING: Script has low fact density (score={fact_score}). May need better research.")

    # Sanitize tags — strip special characters, remove stopwords, enforce min length
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'it'}
    clean_tags = []
    for tag in script.get("tags", []):
        tag = re.sub(r'[^a-zA-Z0-9\s-]', '', str(tag)).strip()
        if len(tag) > 2 and tag.lower() not in stopwords:
            clean_tags.append(tag)
    # Deduplicate and cap at 15
    seen = set()
    unique_tags = []
    for t in clean_tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_tags.append(t)
    script["tags"] = unique_tags[:15]

    # Sanitize description — remove hallucinated timestamps
    desc = script.get("description", "")
    desc = re.sub(r'\d{1,2}:\d{2}\s*[-–—]\s*', '', desc)  # Remove "10:45 - " style
    desc = re.sub(r'extended trial balance', '', desc, flags=re.IGNORECASE)
    script["description"] = desc.strip()

    return script


def save_script(script: dict, output_path: Path) -> Path:
    """Save the generated script to a JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(script, f, indent=2)
    return output_path


def get_full_narration(script: dict) -> str:
    """Extract the full narration text from a script."""
    parts = [script.get("hook", "")]
    for section in script.get("sections", []):
        parts.append(section.get("narration", ""))
    return "\n\n".join(parts)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "The Dyatlov Pass Incident"
    print(f"Generating script for: {topic}")

    script = generate_script(topic)
    narration = get_full_narration(script)
    word_count = len(narration.split())

    out_path = save_script(script, Path("output") / f"{topic.replace(' ', '_').lower()}_script.json")

    print(f"Title: {script['title']}")
    print(f"Word count: {word_count} (~{word_count // WORDS_PER_MINUTE} min)")
    print(f"Sections: {len(script['sections'])}")
    print(f"Saved to: {out_path}")
