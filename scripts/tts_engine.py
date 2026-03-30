"""
Text-to-Speech Engine — converts narration scripts to audio.
Uses edge-tts (FREE, high quality Microsoft Edge voices) as primary.
Google gTTS as fallback (also free).
"""

import asyncio
import sys
from pathlib import Path

from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import AUDIO_DIR, TTS_PROVIDER, EDGE_TTS_VOICE


def _add_dramatic_ssml(text: str) -> str:
    """Add SSML markup for dramatic narration — pauses, emphasis, pacing."""
    import re

    # Add pauses after ellipsis (dramatic beats)
    text = re.sub(r'\.\.\.', '... <break time="800ms"/>', text)

    # Add longer pause before "But" / "However" / "Then" (plot twists)
    text = re.sub(r'([.!?])\s+(But |However |Then |Suddenly |What )',
                  r'\1 <break time="600ms"/> \2', text)

    # Add pause after questions (let it sink in)
    text = re.sub(r'\?\s+', '? <break time="500ms"/> ', text)

    # Slow down for emphasis on ALL CAPS words
    def slow_caps(match):
        word = match.group(0)
        return f'<prosody rate="slow" pitch="-5%">{word.title()}</prosody>'
    text = re.sub(r'\b[A-Z]{4,}\b', slow_caps, text)

    # Add micro-pause before numbers/dates for weight
    text = re.sub(r'(\s)(1[89]\d{2}|20[0-2]\d)(\b)', r'\1<break time="200ms"/>\2\3', text)

    return text


def tts_edge(text: str, output_path: Path, voice: str = None) -> Path:
    """Generate speech using edge-tts with SSML for dramatic narration."""
    import edge_tts

    voice = voice or EDGE_TTS_VOICE
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Add dramatic SSML markup
    dramatic_text = _add_dramatic_ssml(text)

    async def _generate():
        communicate = edge_tts.Communicate(dramatic_text, voice)
        await communicate.save(str(output_path))

    asyncio.run(_generate())
    return output_path


def tts_google(text: str, output_path: Path) -> Path:
    """Generate speech using Google gTTS (free, no API key needed)."""
    from gtts import gTTS

    tts = gTTS(text=text, lang="en", slow=False)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tts.save(str(output_path))
    return output_path


TTS_PROVIDERS = {
    "edge": tts_edge,
    "google": tts_google,
}

# Available edge-tts voices for dark/narrator content:
EDGE_VOICES = {
    "guy": "en-US-GuyNeural",          # Deep male — best for dark history
    "eric": "en-US-EricNeural",         # Authoritative male
    "davis": "en-US-DavisNeural",       # Calm narrator
    "tony": "en-US-TonyNeural",         # Dramatic male
    "andrew": "en-US-AndrewNeural",     # Documentary style
    "brian": "en-US-BrianNeural",       # News anchor style
    "jenny": "en-US-JennyNeural",       # Female narrator
    "aria": "en-US-AriaNeural",         # Female dramatic
}


def generate_audio(text: str, output_path: Path, provider: str = None) -> Path:
    """Generate audio using the configured TTS provider."""
    provider = provider or TTS_PROVIDER
    tts_func = TTS_PROVIDERS.get(provider)
    if not tts_func:
        raise ValueError(f"Unknown TTS provider: {provider}. Use: {list(TTS_PROVIDERS.keys())}")
    return tts_func(text, Path(output_path))


def generate_section_audio(sections: list, base_name: str, provider: str = None) -> list:
    """Generate separate audio files for each script section.
    Returns list of audio file paths.
    """
    audio_files = []
    for i, section in enumerate(sections):
        narration = section.get("narration", "")
        if not narration.strip():
            continue
        filename = AUDIO_DIR / f"{base_name}_section_{i:02d}.mp3"
        generate_audio(narration, filename, provider)
        audio_files.append(filename)
        print(f"  Generated audio: {filename.name}")
    return audio_files


def combine_audio(audio_files: list, output_path: Path, pause_ms: int = 500, sections: list = None) -> Path:
    """Combine multiple audio files with variable pauses — longer after cliffhangers."""
    combined = AudioSegment.empty()

    for i, audio_file in enumerate(audio_files):
        segment = AudioSegment.from_file(str(audio_file))
        combined += segment
        if i < len(audio_files) - 1:
            # Variable pause: check if section ends with a cliffhanger
            section_pause = pause_ms
            if sections and i < len(sections):
                narration = sections[i].get("narration", "")
                # Longer pause after questions, ellipsis, dramatic endings
                if narration.rstrip().endswith(("?", "...", "!")):
                    section_pause = 1200  # dramatic beat
                elif any(w in narration.lower()[-50:] for w in ["dead", "gone", "never", "disappeared", "worse"]):
                    section_pause = 900   # tension pause
            combined += AudioSegment.silent(duration=section_pause)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3")
    print(f"  Combined audio: {output_path.name} ({len(combined) / 1000:.1f}s)")
    return output_path


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds."""
    audio = AudioSegment.from_file(str(audio_path))
    return len(audio) / 1000.0


if __name__ == "__main__":
    test_text = "In 1959, nine hikers ventured into the Ural Mountains. None of them came back alive."
    out = AUDIO_DIR / "test_narration.mp3"
    generate_audio(test_text, out)
    duration = get_audio_duration(out)
    print(f"Generated: {out} ({duration:.1f}s)")
