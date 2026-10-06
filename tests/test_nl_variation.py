"""Tests for the anti-template variation engine.

The whole point of variation.py is that videos do not share a fingerprint, so
these tests assert exactly that: same topic reproduces, different topics differ.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.nl.variation import CAPTION_STYLES, build_variant


def test_same_topic_produces_identical_variant():
    # Arrange
    topic = "Hoe de Deltawerken Nederland droog houden"

    # Act
    first = build_variant(topic)
    second = build_variant(topic)

    # Assert — reruns after a crash must not silently yield a different cut
    assert first == second


def test_determinism_survives_a_fresh_process():
    """str hashing is randomized per process; the seed must not depend on it."""
    import subprocess

    code = (
        "import sys; sys.path.insert(0, '.');"
        "from scripts.nl.variation import build_variant;"
        "print(build_variant('Hoe een polder werkt').seed)"
    )
    runs = {
        subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, cwd=Path(__file__).parent.parent).stdout.strip()
        for _ in range(2)
    }

    assert len(runs) == 1, f"seed differed between processes: {runs}"


def test_different_topics_produce_different_seeds():
    topics = [f"Waarom Nederlandse {n} anders zijn" for n in
              ("fietspaden", "trappen", "ramen", "dijken", "treinen")]

    seeds = {build_variant(t).seed for t in topics}

    assert len(seeds) == len(topics)


def test_salt_rerolls_the_same_topic():
    topic = "Hoe een polder werkt"

    assert build_variant(topic).seed != build_variant(topic, salt="v2").seed


def test_short_uses_a_different_voice_than_the_long_form():
    """A pair sharing one narrator reads as one template rendered twice."""
    topics = [f"Nederlands onderwerp nummer {i}" for i in range(40)]

    same = [t for t in topics
            if build_variant(t).voice == build_variant(t).short_voice]

    assert not same


def test_short_captions_differ_from_long_form_captions():
    topics = [f"Onderwerp {i}" for i in range(40)]

    for topic in topics:
        variant = build_variant(topic)
        assert variant.captions != variant.short_captions


def test_variation_spreads_across_the_available_pools():
    """A pool that always resolves to one value is not variation."""
    variants = [build_variant(f"Nederlands onderwerp {i}") for i in range(120)]

    voices = Counter(v.voice.label for v in variants)
    hooks = Counter(v.hook.name for v in variants)
    captions = Counter(v.captions.name for v in variants)

    assert len(voices) >= 4
    assert len(hooks) >= 6
    assert len(captions) == len(CAPTION_STYLES)


def test_summary_names_every_rotated_knob():
    summary = build_variant("Hoe werkt een sluis").summary()

    for field in ("voice=", "short_voice=", "hook=", "structure=",
                  "captions=", "pacing=", "thumb=", "music="):
        assert field in summary
