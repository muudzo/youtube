"""
Dutch topic discovery.

The English pipeline mines Reddit for viral stories. That transfers badly to
Dutch: the Dutch subreddits are small, half-English, and Reddit now serves 403
to this host. So this works the other way round — it mines *demand* instead of
*stories*.

YouTube's autocomplete endpoint, queried with hl=nl&gl=NL, returns the actual
phrases Dutch people type into YouTube. A phrase that autocomplete surfaces has
demonstrated search volume; one it doesn't, has none. Cross-referencing Dutch
question prefixes against both evergreen seeds and today's NOS headlines turns
that into a free Dutch keyword-research engine with no API key.

Evergreen topics are weighted above news because a fresh channel earns from
search longevity, not from a one-day news spike.
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import OUTPUT_DIR
from scripts.nl import safety

SUGGEST_URL = "https://suggestqueries-clients6.youtube.com/complete/search"
NOS_FEED = "https://feeds.nos.nl/nosnieuwsalgemeen"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# Dutch question openers. These are how Dutch viewers phrase explainer intent.
QUESTION_PREFIXES: tuple[str, ...] = (
    "waarom",
    "hoe komt het dat",
    "wat gebeurde er met",
    "hoe werkt",
    "wat is er mis met",
    "waarom is nederland",
    "hoeveel kost",
    "wie betaalt",
)

# Seeds that reliably carry Dutch search demand and stay relevant for years.
# Deliberately excludes health and finance seeds ("de zorg", "de belasting",
# "de woningmarkt"): safety.py blocks those categories outright, so seeding
# them only burns autocomplete requests on topics that can never be produced.
EVERGREEN_SEEDS: tuple[str, ...] = (
    "nederland", "nederlandse", "amsterdam", "de randstad", "het water",
    "de dijken", "de boeren", "de trein", "schiphol", "de windmolens",
    "het onderwijs", "de energie", "de polder", "de nederlandse taal",
    "de deltawerken",
)

# Topic shapes that signal a video with a defensible angle rather than a listicle.
_HIGH_INTENT = ("waarom", "hoe komt", "wat gebeurde", "wie betaalt", "wat is er mis")


@dataclass(frozen=True)
class Topic:
    """A discovered topic with its demand evidence."""

    query: str
    consensus: int   # how many distinct seeds surfaced it
    is_evergreen: bool
    source: str

    @property
    def score(self) -> float:
        """Rank by demonstrated demand, weighted toward durable search traffic."""
        base = 1.0 + 0.6 * (self.consensus - 1)
        if self.is_evergreen:
            base *= 1.5          # search longevity beats a news spike
        if any(self.query.startswith(p) for p in _HIGH_INTENT):
            base *= 1.25         # explainer intent, not a listicle
        words = len(self.query.split())
        if words >= 4:
            base *= 1.15         # long-tail: less competition for a new channel
        elif words <= 2:
            base *= 0.7          # too broad to rank on
        return base


def youtube_suggest_nl(query: str) -> list[str]:
    """Fetch Dutch YouTube autocomplete suggestions for a query.

    Returns [] on any failure — one dead seed must not stop discovery.
    """
    try:
        response = requests.get(
            SUGGEST_URL,
            params={"client": "youtube", "q": query, "ds": "yt", "hl": "nl", "gl": "NL"},
            headers=HEADERS,
            timeout=10,
        )
        match = re.search(r"\[.*\]", response.text)
        if not match:
            return []
        data = json.loads(match.group())
        if len(data) < 2 or not isinstance(data[1], list):
            return []
        return [item[0] if isinstance(item, list) else item for item in data[1]]
    except (requests.RequestException, ValueError):
        return []


def nos_headlines() -> list[str]:
    """Pull today's NOS headlines as timely seed material."""
    try:
        response = requests.get(NOS_FEED, headers=HEADERS, timeout=12)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  NOS-feed mislukt: {e}")
        return []

    pairs = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>",
                       response.text)
    titles = [(a or b).strip() for a, b in pairs]
    # First entry is the channel title, not a story.
    return [t for t in titles[1:] if len(t) > 20]


def _headline_seed(headline: str) -> str:
    """Reduce a headline to a short seed phrase for autocomplete.

    Autocomplete matches prefixes, so a full headline returns nothing. The
    first few content words carry the subject.
    """
    cleaned = re.sub(r"[^\w\s]", " ", headline.lower())
    stop = {"de", "het", "een", "van", "en", "in", "op", "bij", "na", "voor",
            "met", "dat", "die", "is", "zijn", "wordt", "worden", "ook", "over"}
    words = [w for w in cleaned.split() if w not in stop and len(w) > 3]
    return " ".join(words[:2])


def discover_topics_nl(limit: int = 20, include_news: bool = True) -> list[Topic]:
    """Mine Dutch search demand and return ranked topics.

    Each candidate is counted once per seed that surfaced it; a phrase that
    several different seeds all lead to has broader demand than a one-off.
    """
    hits: dict[str, dict] = {}

    def record(query: str, evergreen: bool, source: str) -> None:
        query = query.strip().lower()
        if len(query) < 8:
            return
        entry = hits.setdefault(
            query, {"consensus": 0, "evergreen": evergreen, "source": source}
        )
        entry["consensus"] += 1
        # Evergreen provenance wins: it drives the durability weighting.
        entry["evergreen"] = entry["evergreen"] or evergreen

    print("Zoekvraag mijnen via YouTube-autocomplete (NL)...")

    # Autocomplete answers the prefix even when the seed matches nothing, so
    # "wat gebeurde er met wim" comes back for all fifteen seeds and looks like
    # unanimous demand. Query each prefix bare first and subtract those echoes,
    # otherwise consensus measures prefix popularity instead of topic demand.
    echoes: set[str] = set()
    for prefix in QUESTION_PREFIXES:
        echoes.update(s.strip().lower() for s in youtube_suggest_nl(prefix))
    print(f"  {len(echoes)} prefix-echo's uitgefilterd")

    for prefix in QUESTION_PREFIXES:
        for seed in EVERGREEN_SEEDS:
            for suggestion in youtube_suggest_nl(f"{prefix} {seed}"):
                if suggestion.strip().lower() in echoes:
                    continue
                record(suggestion, True, f"autocomplete:{prefix}")

    print(f"  {len(hits)} evergreen zoekvragen gevonden")

    if include_news:
        headlines = nos_headlines()
        print(f"  {len(headlines)} NOS-koppen als actuele seeds")
        for headline in headlines:
            seed = _headline_seed(headline)
            if not seed:
                continue
            for prefix in ("waarom", "hoe komt het dat", "wat gebeurde er met"):
                for suggestion in youtube_suggest_nl(f"{prefix} {seed}"):
                    if suggestion.strip().lower() in echoes:
                        continue
                    record(suggestion, False, "nos")

    topics = [
        Topic(query=q, consensus=d["consensus"], is_evergreen=d["evergreen"],
              source=d["source"])
        for q, d in hits.items()
    ]

    # Raw autocomplete ranks by volume alone and will happily surface topics no
    # unattended pipeline should produce. Gate before ranking, not after.
    topics, rejected = safety.filter_topics(topics, key=lambda t: t.query)
    if rejected:
        print(f"  {len(rejected)} onderwerpen geblokkeerd door de veiligheidsfilter")

    topics.sort(key=lambda t: t.score, reverse=True)
    return topics[:limit]


def load_seed_topics(path: Path | None = None) -> list[str]:
    """Read the curated fallback topic list.

    Discovery depends on two external services. When both are down, the
    channel still needs something to produce, so this file is the floor.
    """
    path = path or Path(__file__).parent.parent.parent / "topics_nl.txt"
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def save_topics(topics: list[Topic], output_path: Path | None = None) -> Path:
    """Persist discovered topics for inspection and reuse."""
    output_path = output_path or OUTPUT_DIR / "nl_discovered_topics.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "topic": t.query,
            "score": round(t.score, 3),
            "consensus": t.consensus,
            "evergreen": t.is_evergreen,
            "source": t.source,
        }
        for t in topics
    ]
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return output_path


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    found = discover_topics_nl(limit=count)

    print(f"\n{'Score':>6}  {'Cons':>4}  {'Type':<10}  Onderwerp")
    print(f"{'─' * 6}  {'─' * 4}  {'─' * 10}  {'─' * 50}")
    for t in found:
        kind = "evergreen" if t.is_evergreen else "actueel"
        print(f"{t.score:>6.2f}  {t.consensus:>4}  {kind:<10}  {t.query[:55]}")

    print(f"\nOpgeslagen: {save_topics(found)}")
