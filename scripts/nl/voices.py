"""
Dutch edge-tts voice roster.

Only these five Dutch neural voices exist in edge-tts (verified against
`edge-tts --list-voices`). Rotating across them is the single cheapest way to
break the "one synthetic narrator across every upload" fingerprint.

Belgian (nl-BE) voices read as Flemish to a Dutch ear. They are kept in the
roster but weighted down, so the channel sounds predominantly Netherlands-Dutch
without every video sharing a narrator.
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    """One narrator option."""

    id: str
    label: str
    gender: str
    region: str
    weight: float  # relative selection likelihood
    rate: str      # edge-tts prosody rate, "+N%"
    pitch: str     # edge-tts pitch offset, "+NHz" — edge-tts rejects percentages


# Weights: nl-NL carries the channel, nl-BE adds variety without dominating.
VOICE_ROSTER: tuple[Voice, ...] = (
    Voice("nl-NL-MaartenNeural", "maarten", "male", "NL", 1.0, "+8%", "-3Hz"),
    Voice("nl-NL-ColetteNeural", "colette", "female", "NL", 0.9, "+10%", "+0Hz"),
    Voice("nl-NL-FennaNeural", "fenna", "female", "NL", 0.9, "+6%", "+4Hz"),
    Voice("nl-BE-ArnaudNeural", "arnaud", "male", "BE", 0.4, "+8%", "-4Hz"),
    Voice("nl-BE-DenaNeural", "dena", "female", "BE", 0.4, "+7%", "+3Hz"),
)

VOICES_BY_LABEL = {v.label: v for v in VOICE_ROSTER}


def pick_voice(rng: random.Random) -> Voice:
    """Pick a weighted-random voice using a seeded RNG.

    Takes an RNG rather than using the global one so the choice is
    reproducible from a topic seed — see variation.build_variant.
    """
    weights = [v.weight for v in VOICE_ROSTER]
    return rng.choices(VOICE_ROSTER, weights=weights, k=1)[0]


def pick_contrasting_voice(rng: random.Random, avoid: Voice) -> Voice:
    """Pick a voice that differs from ``avoid`` in gender or region.

    Used for the Short so a topic's long-form and Short are not obviously
    the same synthetic narrator reading the same script twice.
    """
    candidates = [
        v for v in VOICE_ROSTER
        if v.gender != avoid.gender or v.region != avoid.region
    ]
    if not candidates:
        return avoid
    weights = [v.weight for v in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]
