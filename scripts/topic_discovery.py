"""
Topic Discovery — finds proven viral stories from Reddit + Hacker News.
Stolen pattern from last30days-skill: search public APIs, score by engagement,
feed winners into the pipeline. NO API keys needed.

Subreddits mined:
- r/UnresolvedMysteries, r/TodayILearned, r/CreepyWikipedia
- r/DarkHistory, r/MorbidReality, r/TrueCrime
- r/NuclearRevenge, r/ProRevenge, r/BestofRedditorUpdates
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUT_DIR

# Subreddits that align with our niches
DARK_HISTORY_SUBS = [
    "UnresolvedMysteries",
    "CreepyWikipedia",
    "todayilearned",
    "Damnthatsinteresting",
    "morbidreality",
]

BETRAYAL_REVENGE_SUBS = [
    "NuclearRevenge",
    "ProRevenge",
    "BestofRedditorUpdates",
    "relationship_advice",
    "TrueOffMyChest",
]

AFRICAN_HISTORY_SUBS = [
    "africa",
    "Zimbabwe",
    "AskHistorians",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) 4kMUDZO-Research/1.0"
}


def search_reddit(query: str = "", subreddit: str = "", sort: str = "top", time_filter: str = "month", limit: int = 25) -> list:
    """Search Reddit public JSON — no API key needed."""
    if subreddit:
        url = f"https://www.reddit.com/r/{subreddit}/top.json"
        params = {"t": time_filter, "limit": limit}
    else:
        url = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": sort, "t": time_filter, "limit": limit}

    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if response.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if response.status_code == 403:
                print(f"  Reddit blocked request for r/{subreddit}")
                return []
            response.raise_for_status()
            break
        except requests.RequestException as e:
            print(f"  Reddit request failed: {e}")
            return []
    else:
        return []

    data = response.json()
    posts = []

    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("is_self", True) or post.get("selftext", ""):
            posts.append({
                "title": post.get("title", ""),
                "score": post.get("score", 0),
                "comments": post.get("num_comments", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
                "subreddit": post.get("subreddit", ""),
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "selftext": post.get("selftext", "")[:500],
                "created_utc": post.get("created_utc", 0),
            })

    return posts


def search_hacker_news(query: str, limit: int = 10) -> list:
    """Search Hacker News via Algolia API — completely free, no auth."""
    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": "points>50",
        "hitsPerPage": limit,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return []

    data = response.json()
    return [
        {
            "title": hit.get("title", ""),
            "score": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "url": hit.get("url", ""),
            "source": "hackernews",
        }
        for hit in data.get("hits", [])
    ]


def score_topic(post: dict) -> float:
    """Score a topic by proven engagement — higher = more likely to perform on YouTube.
    Formula: relevance (45%) + engagement (30%) + virality (25%)"""
    score = post.get("score", 0)
    comments = post.get("comments", 0)
    upvote_ratio = post.get("upvote_ratio", 0.5)

    # Engagement score (normalized)
    engagement = min(score / 1000, 1.0) * 0.30

    # Comment activity = strong signal of discussion-worthy content
    discussion = min(comments / 200, 1.0) * 0.25

    # Upvote ratio — controversial posts (0.6-0.8) actually perform well on YouTube
    controversy_bonus = 0.15 if 0.6 <= upvote_ratio <= 0.85 else 0.05

    # Title quality — does it have a hook?
    title = post.get("title", "").lower()
    hook_words = ["never", "secret", "found", "discovered", "worst", "killed",
                  "disappeared", "betrayed", "revenge", "nobody", "truth",
                  "insane", "terrifying", "shocking", "caught", "destroyed"]
    hook_score = sum(0.05 for w in hook_words if w in title)
    hook_score = min(hook_score, 0.25)

    return engagement + discussion + controversy_bonus + hook_score


def discover_topics(niche: str = "all", limit: int = 20) -> list:
    """Discover high-potential video topics from Reddit + HN.

    Returns sorted list of topics with engagement scores.
    """
    all_posts = []

    # Select subreddits based on niche
    if niche == "dark_history":
        subs = DARK_HISTORY_SUBS
    elif niche == "betrayal":
        subs = BETRAYAL_REVENGE_SUBS
    elif niche == "african":
        subs = AFRICAN_HISTORY_SUBS
    else:
        subs = DARK_HISTORY_SUBS + BETRAYAL_REVENGE_SUBS

    print(f"Searching {len(subs)} subreddits for viral topics...")

    for sub in subs:
        print(f"  Scanning r/{sub}...")
        posts = search_reddit(subreddit=sub, time_filter="month", limit=25)
        all_posts.extend(posts)
        time.sleep(2)  # respect rate limits

    # Also search HN for dark history content
    print("  Scanning Hacker News...")
    hn_posts = search_hacker_news("mystery unsolved history", limit=10)
    all_posts.extend(hn_posts)

    # Score and sort
    for post in all_posts:
        post["topic_score"] = score_topic(post)

    # Sort by score, deduplicate similar titles
    all_posts.sort(key=lambda p: p["topic_score"], reverse=True)

    # Deduplicate — remove similar titles
    seen = set()
    unique = []
    for post in all_posts:
        title_key = " ".join(post["title"].lower().split()[:5])
        if title_key not in seen:
            seen.add(title_key)
            unique.append(post)

    return unique[:limit]


def format_for_pipeline(topics: list) -> list:
    """Convert discovered topics into pipeline-ready format."""
    pipeline_topics = []
    for t in topics:
        # Clean title for video topic
        title = t["title"]
        # Remove Reddit prefixes like "TIL that", "[OC]", etc
        for prefix in ["TIL that ", "TIL ", "[OC] ", "CMV: "]:
            if title.startswith(prefix):
                title = title[len(prefix):]

        pipeline_topics.append({
            "topic": title,
            "source": f"r/{t.get('subreddit', 'unknown')}",
            "engagement_score": t["topic_score"],
            "reddit_score": t.get("score", 0),
            "reddit_comments": t.get("comments", 0),
            "url": t.get("url", ""),
        })

    return pipeline_topics


def save_discovered_topics(topics: list, output_path: Path = None) -> Path:
    """Save discovered topics to JSON."""
    output_path = output_path or OUTPUT_DIR / "discovered_topics.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(topics, f, indent=2)

    print(f"\nSaved {len(topics)} topics to {output_path}")
    return output_path


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "all"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    print(f"=== TOPIC DISCOVERY ({niche}) ===\n")
    raw = discover_topics(niche=niche, limit=limit)
    topics = format_for_pipeline(raw)

    print(f"\n{'Score':>6}  {'Reddit':>6}  {'Cmts':>5}  Source          Topic")
    print(f"{'─'*6}  {'─'*6}  {'─'*5}  {'─'*14}  {'─'*50}")

    for t in topics:
        print(f"{t['engagement_score']:>6.2f}  {t['reddit_score']:>6}  {t['reddit_comments']:>5}  {t['source']:<14}  {t['topic'][:55]}")

    save_discovered_topics(topics)
    print("\nDone! Use these topics with: python3 pipeline.py '<topic>'")
