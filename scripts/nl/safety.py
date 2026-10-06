"""
Topic safety gate.

Two independent reasons this exists.

Policy: YouTube's July 2026 inauthentic-content update names a third category
outright — content "where AI personas are used to discuss sensitive topics,
like health and finance". A synthetic Dutch narrator explaining medication,
pensions or investments is not a grey area; it is the named case. Those topics
are blocked regardless of how much search demand they carry.

Judgment: discovery mines raw autocomplete, which surfaces whatever people
type. A live run of scripts/nl/topics.py returned "wat zijn joden" purely on
search volume. Nothing downstream of discovery has a human in the loop before
upload, so the filter has to sit here. Identity, religion, ethnicity, named
private individuals and active tragedies are not topics an unattended pipeline
should decide how to frame.

This is a blocklist, so it is a floor and not a guarantee. Anything it lets
through is still your editorial responsibility.
"""

import re

# Protected characteristics and identity topics. An unattended generator has no
# business choosing the framing on any of these.
_IDENTITY = (
    "joden", "jodendom", "moslims", "islam", "christenen", "kerk en staat",
    "homo", "lhbt", "transgender", "geslachtsverandering", "ras", "rassen",
    "allochtoon", "buitenlanders", "asielzoekers", "vluchtelingen", "migranten",
    "zwarte piet", "slavernijverleden", "antisemitisme", "discriminatie",
    "jews", "muslims", "immigrants", "refugees", "race",
)

# The policy's named sensitive categories: health and finance.
_HEALTH = (
    "medicijn", "medicatie", "symptomen", "diagnose", "kanker", "behandeling",
    "vaccin", "vaccinatie", "zelfmoord", "suicide", "depressie", "afvallen",
    "dieet", "supplementen", "euthanasie", "abortus", "zorgverzekering",
    "ggz", "verslaving", "bijwerkingen",
)

_FINANCE = (
    "beleggen", "aandelen", "crypto", "bitcoin", "pensioen", "hypotheek",
    "lening", "schulden", "sparen rente", "belastingaangifte", "toeslagen aanvragen",
    "geld verdienen", "rijk worden", "investeren", "koersen", "verzekering afsluiten",
)

# Active tragedy and violence — wrong for an unattended synthetic narrator.
_TRAGEDY = (
    "aanslag", "aanslagen", "schietpartij", "moord op", "vermoord", "ontvoering",
    "misbruik", "verkrachting", "oorlog in", "slachtoffers van", "neergestort",
    "overleden", "dodelijke", "terrorisme", "gijzeling",
)

# Live party politics. Evergreen civics ("hoe werkt de Tweede Kamer") is fine;
# telling Dutch viewers what to think about a sitting party is not.
_PARTY_POLITICS = (
    "pvv", "vvd", "d66", "geert wilders", "verkiezingsuitslag", "stemadvies",
    "kabinetsformatie", "motie van wantrouwen", "moet je stemmen",
)

BLOCKED_TERMS: tuple[str, ...] = (
    _IDENTITY + _HEALTH + _FINANCE + _TRAGEDY + _PARTY_POLITICS
)

# Categories reported back to the caller, so a rejection explains itself.
_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("identiteit", _IDENTITY),
    ("gezondheid", _HEALTH),
    ("financieel", _FINANCE),
    ("tragedie", _TRAGEDY),
    ("partijpolitiek", _PARTY_POLITICS),
)


def classify(topic: str) -> str | None:
    """Return the blocking category for a topic, or None if it is allowed."""
    text = f" {topic.lower().strip()} "
    for category, terms in _CATEGORIES:
        for term in terms:
            # Word-boundary match so "ras" does not trip on "terras".
            if re.search(rf"(?<![a-zà-ü]){re.escape(term)}(?![a-zà-ü])", text):
                return category
    return None


def is_safe(topic: str) -> bool:
    """True when a topic is safe for unattended production."""
    return classify(topic) is None


def filter_topics(topics: list, key=lambda t: t) -> tuple[list, list]:
    """Split topics into (allowed, rejected).

    ``key`` extracts the text from whatever the caller is holding, so this
    works on plain strings and on Topic objects alike.
    """
    allowed, rejected = [], []
    for topic in topics:
        (rejected if classify(key(topic)) else allowed).append(topic)
    return allowed, rejected


if __name__ == "__main__":
    samples = [
        "wat zijn joden",
        "hoe werkt een polder",
        "beste manier om te beleggen in 2026",
        "waarom staan Amsterdamse huizen scheef",
        "symptomen van een burn-out",
        "hoe werkt het Nederlandse onderwijs",
        "de aanslag op het Binnenhof",
        "waarom alle wereldkaarten verkeerd zijn",
    ]
    for s in samples:
        verdict = classify(s)
        print(f"  {'GEBLOKKEERD (' + verdict + ')' if verdict else 'toegestaan':<26} {s}")
