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


# ── Theme multipliers for 4kMUDZO's actual audience (100% age 55+, 72% male)
# These are resonance boosts, not hard filters — they nudge the generator toward
# themes that historically convert for this demographic without killing outliers.
AGE_55_PLUS_THEMES = {
    "long_marriage":           1.25,  # 20+ year marriages, decades-long relationships
    "inheritance_dispute":     1.30,  # wills, estates, family money
    "adult_children_conflict": 1.20,  # grown kids, family fractures
    "late_life_betrayal":      1.35,  # discoveries after decades
    "retirement_finance":      1.20,  # retirement, savings, late-life money
    "aging_parents":           1.25,  # elder care, parent-child inversions
    "regret_reconciliation":   1.30,  # deathbed, reunion, lifelong regret
    "lifelong_secret":         1.30,  # 20+ years of hidden truth
    "moral_justice":           1.15,  # karma, consequences, eventual justice
}

YOUTH_LEANING_THEMES = {
    "dating_drama":            0.80,
    "college_relationships":   0.75,
    "social_media_conflict":   0.70,
    "viral_trend_hook":        0.85,
    "gen_z_slang":             0.70,
}


def classify_themes(text: str) -> list:
    """Detect which themes apply to a post. Returns a list of theme tags.
    A single post can match multiple themes."""
    import re as _re
    t = text.lower()
    tags = []

    # Long marriage — explicit multi-decade relationship
    years = [int(y) for y in _re.findall(r"(\d+)\s*year", t)]
    long_years = any(y >= 20 for y in years)
    very_long_years = any(y >= 35 for y in years)

    marriage_terms = ["husband", "wife", "marriage", "married", "spouse"]
    if long_years and any(w in t for w in marriage_terms):
        tags.append("long_marriage")
    if very_long_years:
        tags.append("lifelong_secret")

    # Inheritance / estate
    if any(w in t for w in ["inheritance", "will", "estate", "heir", "widow", "widower"]):
        tags.append("inheritance_dispute")

    # Adult children conflict
    if any(w in t for w in ["adult son", "adult daughter", "grown son", "grown daughter",
                             "her children", "his children", "my kids"]):
        tags.append("adult_children_conflict")

    # Late-life betrayal — discovery after long time
    if any(phrase in t for phrase in ["after decades", "after 20 years", "after 30 years",
                                        "after 40 years", "for years", "all along",
                                        "never told", "kept secret"]):
        tags.append("late_life_betrayal")

    # Retirement / late-life finance
    if any(w in t for w in ["retirement", "pension", "retired", "savings", "401k"]):
        tags.append("retirement_finance")

    # Aging parents
    if any(w in t for w in ["aging parent", "elderly mother", "elderly father",
                              "caring for", "dementia", "nursing home", "hospice"]):
        tags.append("aging_parents")

    # Regret / reconciliation
    if any(w in t for w in ["regret", "deathbed", "funeral", "reconciled",
                              "last wish", "reunion", "before she died", "before he died"]):
        tags.append("regret_reconciliation")

    # Moral justice
    if any(w in t for w in ["karma", "justice", "finally paid", "consequences",
                              "got what he deserved", "got what she deserved"]):
        tags.append("moral_justice")

    # Youth-leaning (negative)
    if any(w in t for w in ["tiktok", "instagram", "snapchat", "viral", "trending"]):
        tags.append("social_media_conflict")
    if any(w in t for w in ["college", "dorm", "roommate", "university"]):
        tags.append("college_relationships")
    if any(w in t for w in ["dating app", "tinder", "hinge", "bumble", "swipe"]):
        tags.append("dating_drama")

    return tags


def score_topic(post: dict) -> float:
    """Score a topic: base virality × theme resonance multipliers.

    Base score comes from Reddit engagement signals. Theme multipliers
    nudge toward 55+ resonance without hard-filtering outliers.
    """
    score = post.get("score", 0)
    comments = post.get("comments", 0)
    upvote_ratio = post.get("upvote_ratio", 0.5)

    # ── Base score (preserves the original virality signal)
    engagement = min(score / 1000, 1.0) * 0.35
    discussion = min(comments / 200, 1.0) * 0.25
    controversy_bonus = 0.15 if 0.6 <= upvote_ratio <= 0.85 else 0.05

    title = post.get("title", "").lower()
    hook_words = ["secret", "found", "discovered", "betrayed", "revenge",
                  "truth", "caught", "destroyed", "hidden", "lied"]
    hook_score = min(sum(0.03 for w in hook_words if w in title), 0.25)

    base_score = engagement + discussion + controversy_bonus + hook_score

    # ── Apply theme multipliers
    text = post.get("title", "") + " " + post.get("selftext", "")
    tags = classify_themes(text)
    post["themes"] = tags  # store for debugging / downstream use

    score_out = base_score
    for tag in tags:
        if tag in AGE_55_PLUS_THEMES:
            score_out *= AGE_55_PLUS_THEMES[tag]
        elif tag in YOUTH_LEANING_THEMES:
            score_out *= YOUTH_LEANING_THEMES[tag]

    return score_out


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
