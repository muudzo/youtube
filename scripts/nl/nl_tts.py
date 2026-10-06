"""
Dutch narration synthesis.

scripts/tts_engine.py's dramatic-SSML pass keys on English trigger words
("But", "However", "Suddenly"), so on Dutch text it does essentially nothing —
the narration comes out flat, which is fatal for retention. This module is the
Dutch equivalent, plus per-video voice/rate/pitch from the VideoVariant.

Note that edge-tts applies rate and pitch as synthesis parameters rather than
inline SSML, and rejects a percentage pitch — it must be in Hz.
"""

import asyncio
import re
import sys
from pathlib import Path

from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.nl.voices import Voice

# Dutch pivot words. A beat before these is what makes a turn land.
_PIVOTS = (
    "Maar", "Toch", "Alleen", "Behalve", "Dan", "Plotseling", "Ineens",
    "En toen", "Tot", "Want", "Sterker nog", "Het punt is",
)

# Dutch emphasis words that carry the weight of a sentence.
_EMPHASIS = (
    "nooit", "niemand", "niets", "altijd", "iedereen", "alles",
    "geen enkele", "volledig", "compleet",
)


def add_dutch_prosody(text: str) -> str:
    """Insert SSML breaks and emphasis suited to Dutch narration."""
    # Ellipsis is an explicit beat.
    text = text.replace("...", '... <break time="700ms"/>')

    # Pause before a pivot, so the turn registers.
    pivots = "|".join(re.escape(p) for p in _PIVOTS)
    text = re.sub(rf"([.!?])\s+({pivots})\b", r'\1 <break time="550ms"/> \2', text)

    # Let a question land before the answer.
    text = re.sub(r"\?\s+", '? <break time="450ms"/> ', text)

    # Slow the absolutes — in Dutch these are where the claim actually sits.
    emphasis = "|".join(re.escape(w) for w in _EMPHASIS)
    text = re.sub(
        rf"\b({emphasis})\b",
        r'<prosody rate="slow">\1</prosody>',
        text,
        flags=re.IGNORECASE,
    )

    # A beat before a year gives the number weight.
    text = re.sub(r"(\s)(1[5-9]\d{2}|20[0-4]\d)(\b)", r'\1<break time="200ms"/>\2\3', text)
    return text


def synthesize(text: str, output_path: Path, voice: Voice) -> Path:
    """Render Dutch narration to mp3 with the variant's voice settings."""
    import edge_tts

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        communicate = edge_tts.Communicate(
            add_dutch_prosody(text),
            voice.id,
            rate=voice.rate,
            pitch=voice.pitch,
        )
        await communicate.save(str(output_path))

    asyncio.run(_run())
    return output_path


def synthesize_sections(sections: list, slug: str, voice: Voice,
                        audio_dir: Path) -> list[Path]:
    """Render each section to its own file so pauses can vary between them."""
    paths: list[Path] = []
    for i, section in enumerate(sections):
        narration = section.get("narration", "").strip()
        if not narration:
            continue
        path = audio_dir / f"{slug}_sectie_{i:02d}.mp3"
        synthesize(narration, path, voice)
        paths.append(path)
        print(f"  Audio: {path.name}")
    return paths


def combine(audio_files: list, output_path: Path, pause_ms: int = 350,
            sections: list = None) -> Path:
    """Concatenate section audio, holding longer after a cliffhanger."""
    combined = AudioSegment.empty()

    for i, audio_file in enumerate(audio_files):
        combined += AudioSegment.from_file(str(audio_file))
        if i >= len(audio_files) - 1:
            continue

        gap = pause_ms
        if sections and i < len(sections):
            tail = sections[i].get("narration", "").rstrip()
            if tail.endswith(("?", "...", "!")):
                gap = int(pause_ms * 2.6)   # the section ended on a hook
            elif any(w in tail.lower()[-60:] for w in
                     ("nooit", "verdwenen", "dood", "voorgoed", "te laat")):
                gap = int(pause_ms * 1.9)
        combined += AudioSegment.silent(duration=gap)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3")
    print(f"  Narratie samengevoegd: {output_path.name} ({len(combined) / 1000:.1f}s)")
    return output_path


def duration_of(audio_path: Path) -> float:
    """Duration of an audio file in seconds."""
    return len(AudioSegment.from_file(str(audio_path))) / 1000.0
