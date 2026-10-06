"""
Anti-template variation engine.

YouTube's inauthentic-content policy (renamed from "repetitious content" in
July 2025, expanded July 2026) demonetizes content that is "generic,
repetitive, or template-based" and "reproduced at scale with little variation".
Enforcement reportedly keys on a fingerprint: one synthetic narrator, one
thumbnail template, stock-footage loops, and a superhuman upload pace.

This module breaks that fingerprint. Every observable property of a video —
narrator, hook shape, narrative architecture, caption treatment, cut rhythm,
thumbnail styling — is drawn per video from a seed derived from the topic.
Seeding (rather than global randomness) keeps a topic reproducible: re-running
the same topic yields the same video, so reruns after a crash don't silently
produce a different cut.

This is a real mitigation, not a guarantee. Variation addresses the
"template-based" prong; the "original value" prong is handled by the angle
requirement in script_generator.py, and cadence by config.NL_MAX_UPLOADS_PER_DAY.
"""

import hashlib
import random
from dataclasses import dataclass

from scripts.nl.voices import Voice, pick_contrasting_voice, pick_voice


# ══════════════════════════════════════════════════════════
# Rotation pools
# ══════════════════════════════════════════════════════════
# Instructions are written in Dutch because they are injected into a Dutch
# system prompt — mixing languages mid-prompt measurably degrades output.

@dataclass(frozen=True)
class HookArchetype:
    """An opening shape. The first 2 seconds decide the video."""

    name: str
    instruction: str


HOOK_ARCHETYPES: tuple[HookArchetype, ...] = (
    HookArchetype(
        "schokcijfer",
        "Open met één concreet, verifieerbaar cijfer dat de kijker niet ziet "
        "aankomen. Geen aanloop, geen begroeting — het cijfer staat in de "
        "eerste zin.",
    ),
    HookArchetype(
        "tegenintuitief",
        "Open met een bewering die ingaat tegen wat vrijwel iedereen aanneemt, "
        "en beloof direct het bewijs. Bijvoorbeeld: 'Alles wat je hierover "
        "geleerd hebt, klopt niet — en dat is aantoonbaar.'",
    ),
    HookArchetype(
        "alledaags_detail",
        "Open met een volstrekt alledaags detail dat de kijker herkent, en "
        "draai het binnen twee zinnen om naar iets verontrustends.",
    ),
    HookArchetype(
        "directe_inzet",
        "Open door de kijker rechtstreeks aan te spreken over wat dit voor "
        "hém of háár betekent. Tweede persoon, concrete inzet, geen abstractie.",
    ),
    HookArchetype(
        "open_mysterie",
        "Open met de onbeantwoorde vraag zelf, scherp geformuleerd, en maak "
        "expliciet dat het antwoord pas later komt.",
    ),
    HookArchetype(
        "omgekeerde_onthulling",
        "Open met de afloop — het eindresultaat, de uitkomst — en laat de "
        "kijker zich afvragen hoe het in vredesnaam zover kwam.",
    ),
    HookArchetype(
        "confrontatie",
        "Open met een directe uitdaging aan de aanname van de kijker. "
        "Kort, bijna bot, en meteen gevolgd door onderbouwing.",
    ),
    HookArchetype(
        "stille_start",
        "Open rustig en bijna terloops met één feit, en laat de tweede zin "
        "de bodem eronder wegslaan. Het contrast is de hook.",
    ),
)


@dataclass(frozen=True)
class NarrativeStructure:
    """How the body of the video is architected."""

    name: str
    instruction: str
    section_range: tuple[int, int]


NARRATIVE_STRUCTURES: tuple[NarrativeStructure, ...] = (
    NarrativeStructure(
        "chronologisch",
        "Bouw de video chronologisch op, maar begin halverwege het verhaal en "
        "vul de aanloop pas in als de kijker al vastzit.",
        (6, 8),
    ),
    NarrativeStructure(
        "omgekeerd",
        "Begin bij de uitkomst en werk stap voor stap terug naar de oorzaak. "
        "Elke sectie beantwoordt 'ja maar hoe kwam dat dan?'.",
        (6, 7),
    ),
    NarrativeStructure(
        "mythe_versus_feit",
        "Structureer als opeenvolgende paren: eerst de breed gedeelde aanname, "
        "dan wat er werkelijk klopt. Elk paar is één sectie.",
        (6, 8),
    ),
    NarrativeStructure(
        "casus_dan_patroon",
        "Begin met één concreet geval in detail, en zoom daarna uit naar het "
        "bredere patroon waar dat geval een symptoom van is.",
        (6, 8),
    ),
    NarrativeStructure(
        "vraagketen",
        "Elke sectie beantwoordt de vraag die de vorige sectie opriep, en "
        "eindigt met een scherpere vraag.",
        (7, 9),
    ),
    NarrativeStructure(
        "oplopende_inzet",
        "Rangschik de secties op oplopende impact: elke sectie moet zwaarder "
        "wegen dan de vorige. De laatste is de zwaarste.",
        (6, 8),
    ),
)


@dataclass(frozen=True)
class CaptionStyle:
    """Burned-in caption treatment. Brainrot pacing needs them; sameness kills."""

    name: str
    font_size: int
    position: float       # relative y, 0.0 top → 1.0 bottom
    color: str
    stroke_width: int
    uppercase: bool
    box: bool


CAPTION_STYLES: tuple[CaptionStyle, ...] = (
    CaptionStyle("laag_wit_blok", 85, 0.78, "white", 4, True, True),
    CaptionStyle("midden_geel", 92, 0.62, "#FFD400", 5, True, False),
    CaptionStyle("laag_zacht", 78, 0.80, "#F5F5F5", 3, False, True),
    CaptionStyle("hoog_wit", 88, 0.24, "white", 4, True, False),
    CaptionStyle("midden_mint", 90, 0.66, "#9FFFCB", 5, True, False),
    CaptionStyle("laag_groot", 100, 0.74, "white", 6, True, False),
)


@dataclass(frozen=True)
class PacingProfile:
    """Cut rhythm. Brainrot reads as fast, but identical rhythm reads as a template."""

    name: str
    min_cut: float
    max_cut: float
    section_pause_ms: int
    fade: float


PACING_PROFILES: tuple[PacingProfile, ...] = (
    PacingProfile("hard", 2.0, 3.2, 260, 0.12),
    PacingProfile("strak", 2.6, 4.0, 340, 0.18),
    PacingProfile("wisselend", 2.2, 5.0, 300, 0.15),
    PacingProfile("ademend", 3.4, 5.6, 460, 0.25),
)


@dataclass(frozen=True)
class ThumbnailTreatment:
    """Thumbnail styling. A shared template across uploads is a loud signal."""

    name: str
    text_color: str
    style: str
    font: str


# Colour alone was not enough: rendered in one typeface, the whole set still
# read as a single template. Each treatment carries its own face. All four ship
# with macOS; thumbnail_generator falls back to its own chain elsewhere.
_FONT_DIR = "/System/Library/Fonts/Supplemental"

THUMBNAIL_TREATMENTS: tuple[ThumbnailTreatment, ...] = (
    ThumbnailTreatment("wit_hard", "white", "bright", f"{_FONT_DIR}/Impact.ttf"),
    ThumbnailTreatment("geel_schok", "yellow", "bright", f"{_FONT_DIR}/Arial Black.ttf"),
    ThumbnailTreatment("mint_koel", "#9FFFCB", "bright", f"{_FONT_DIR}/Verdana Bold.ttf"),
    ThumbnailTreatment("rood_alarm", "#FF5A5A", "bright", f"{_FONT_DIR}/Trebuchet MS Bold.ttf"),
)


# ══════════════════════════════════════════════════════════
# The variant
# ══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VideoVariant:
    """Every per-video choice, resolved. Immutable — pass it, don't mutate it."""

    seed: str
    voice: Voice
    short_voice: Voice
    hook: HookArchetype
    structure: NarrativeStructure
    section_count: int
    captions: CaptionStyle
    short_captions: CaptionStyle
    pacing: PacingProfile
    thumbnail: ThumbnailTreatment
    use_music: bool

    def summary(self) -> str:
        """One-line description for logs, so a run is traceable to its knobs."""
        return (
            f"voice={self.voice.label} short_voice={self.short_voice.label} "
            f"hook={self.hook.name} structure={self.structure.name}"
            f"({self.section_count}) captions={self.captions.name} "
            f"pacing={self.pacing.name} thumb={self.thumbnail.name} "
            f"music={'ja' if self.use_music else 'nee'}"
        )


def _seed_for(topic: str, salt: str = "") -> tuple[str, random.Random]:
    """Derive a stable seed from the topic.

    Uses blake2b rather than hash() because Python randomizes str hashing per
    process — without this, the same topic would vary between runs.
    """
    digest = hashlib.blake2b(f"{topic}|{salt}".encode(), digest_size=8).hexdigest()
    return digest, random.Random(int(digest, 16))


def build_variant(topic: str, salt: str = "") -> VideoVariant:
    """Resolve every per-video knob deterministically from the topic.

    ``salt`` lets you deliberately re-roll a topic (e.g. a second take on the
    same subject months later) without colliding with the first version.
    """
    seed, rng = _seed_for(topic, salt)

    voice = pick_voice(rng)
    structure = rng.choice(NARRATIVE_STRUCTURES)
    captions = rng.choice(CAPTION_STYLES)

    return VideoVariant(
        seed=seed,
        voice=voice,
        short_voice=pick_contrasting_voice(rng, voice),
        hook=rng.choice(HOOK_ARCHETYPES),
        structure=structure,
        section_count=rng.randint(*structure.section_range),
        captions=captions,
        # The Short gets a different caption treatment from its parent so the
        # pair doesn't read as one template rendered twice.
        short_captions=rng.choice([c for c in CAPTION_STYLES if c != captions]),
        pacing=rng.choice(PACING_PROFILES),
        thumbnail=rng.choice(THUMBNAIL_TREATMENTS),
        # Music on most but not all — a constant audio bed across a channel is
        # itself a fingerprint.
        use_music=rng.random() < 0.65,
    )
