"""
YouTube Shorts Generator v2 — polished, high-retention vertical clips.
- Fast cuts (3-5s per clip) for Shorts pacing
- Ken Burns effects (zoom/pan) on every clip
- Bold animated subtitles at bottom-third with highlight box
- Hook text overlay in first 3 seconds
- Brightness filtering — no dark clips
- Fade transitions between clips
- Professional feel that converts viewers to subscribers
"""

import json
import random
import sys
from pathlib import Path

import numpy as np
import requests
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    ColorClip,
    concatenate_videoclips,
    vfx,
)
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.video_assembler import caption_box_size
from config import (
    SHORTS_WIDTH,
    SHORTS_HEIGHT,
    SHORTS_FPS,
    GROQ_API_KEY,
    SCRIPT_MODEL,
    VIDEO_DIR,
    AUDIO_DIR,
)


def extract_hook_for_short(script: dict) -> dict:
    """Extract the most engaging 45-60 seconds of content for a Short using Groq."""
    full_text = script.get("hook", "") + "\n"
    for section in script.get("sections", [])[:3]:
        full_text += section.get("narration", "") + "\n"

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Extract the most hook-worthy 60-second segment from a script for a YouTube Short. Return ONLY valid JSON.",
            },
            {
                "role": "user",
                "content": f"""Pick the section that would make someone STOP scrolling.
The first sentence MUST be a jaw-dropping hook.
Return JSON: {{"narration": "the 45-60 second narration", "visual_keywords": ["keyword1", "keyword2"], "hook_text": "2-5 word hook for text overlay"}}

Script:
{full_text}""",
            },
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return json.loads(text)


# ─── Ken Burns for vertical clips ──────────────────────
_short_effect_idx = 0
_SHORT_EFFECTS = ["zoom_in", "zoom_out", "pan_up", "pan_down"]


def _short_ken_burns(clip, effect=None):
    """Apply Ken Burns to a vertical clip — zoom or pan."""
    global _short_effect_idx
    if effect is None:
        effect = _SHORT_EFFECTS[_short_effect_idx % len(_SHORT_EFFECTS)]
        _short_effect_idx += 1

    w, h = clip.size
    scale = random.uniform(1.08, 1.15)

    def motion(get_frame, t):
        progress = t / max(clip.duration, 0.1)
        if effect == "zoom_in":
            s = 1.0 + (scale - 1.0) * progress
        elif effect == "zoom_out":
            s = scale - (scale - 1.0) * progress
        else:
            s = scale  # constant zoom for pan

        frame = get_frame(t)
        new_w, new_h = int(w * s), int(h * s)
        img = Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)

        if effect == "pan_up":
            left = (new_w - w) // 2
            top = int((new_h - h) * (1 - progress))
        elif effect == "pan_down":
            left = (new_w - w) // 2
            top = int((new_h - h) * progress)
        else:
            left = (new_w - w) // 2
            top = (new_h - h) // 2

        img = img.crop((left, top, left + w, top + h))
        return np.array(img)

    return clip.transform(motion)


def _measure_brightness(clip):
    """Quick brightness check — sample middle frame."""
    try:
        frame = clip.get_frame(clip.duration / 2)
        return float(frame.mean())
    except Exception:
        return 0.0


def _crop_to_vertical(clip):
    """Crop a landscape clip to 9:16 vertical — center crop."""
    target_ratio = SHORTS_WIDTH / SHORTS_HEIGHT  # 0.5625

    if clip.w / clip.h > target_ratio:
        # Wider than target — crop sides
        clip = clip.resized(height=SHORTS_HEIGHT)
        x_center = clip.w // 2
        clip = clip.cropped(
            x1=x_center - SHORTS_WIDTH // 2,
            x2=x_center + SHORTS_WIDTH // 2,
        )
    else:
        # Taller or equal — crop top/bottom
        clip = clip.resized(width=SHORTS_WIDTH)
        y_center = clip.h // 2
        clip = clip.cropped(
            y1=max(0, y_center - SHORTS_HEIGHT // 2),
            y2=y_center + SHORTS_HEIGHT // 2,
        )
    return clip


def create_short(
    audio_path: Path,
    subtitles: list,
    footage_files: list,
    output_path: Path,
    hook_text: str = "",
    caption_style=None,
    cut_range: tuple = None,
) -> Path:
    """Create a polished vertical 9:16 YouTube Short.

    ``caption_style`` and ``cut_range`` are optional per-video overrides used
    by the Dutch pipeline so Shorts don't all share one caption treatment and
    cut rhythm. Both default to the previous fixed behaviour.
    """
    global _short_effect_idx
    _short_effect_idx = 0

    narration = AudioFileClip(str(audio_path))
    duration = min(narration.duration, 59.0)
    narration = narration.subclipped(0, duration)

    # ── Text-only impact frame — first 1.5s is a dark screen
    # with giant hook text to stop the scroll BEFORE footage begins.
    # This directly fights swipe-away in the first 1-2 seconds.
    IMPACT_DURATION = 1.5
    impact_bg = ColorClip(
        (SHORTS_WIDTH, SHORTS_HEIGHT), (8, 8, 12), duration=IMPACT_DURATION
    )

    footage_duration = max(0.1, duration - IMPACT_DURATION)

    # ── Build footage sequence ────────────────────────
    if footage_files:
        # Filter dark clips
        bright_files = []
        for fp in footage_files:
            try:
                c = VideoFileClip(str(fp))
                b = _measure_brightness(c)
                c.close()
                if b >= 55:
                    bright_files.append(fp)
            except Exception:
                pass

        if len(bright_files) < 3:
            bright_files = footage_files  # fallback if too few bright

        # Deduplicate
        bright_files = list(dict.fromkeys(str(f) for f in bright_files))
        random.shuffle(bright_files)

        # Measured cuts for 55+ audience: 5-8 seconds per clip.
        # Older viewers need more time per visual to reduce cognitive load —
        # faster cuts (3-5s) were tanking retention.
        clip_durations = []
        remaining = footage_duration
        lo, hi = cut_range if cut_range else (5.0, 8.0)
        while remaining > 0:
            d = random.uniform(lo, hi)
            d = min(d, remaining)
            clip_durations.append(d)
            remaining -= d

        clips = []
        for i, clip_dur in enumerate(clip_durations):
            fp = bright_files[i % len(bright_files)]
            try:
                c = VideoFileClip(str(fp))
                c = _crop_to_vertical(c)

                # Random start point within the clip
                if c.duration > clip_dur:
                    max_start = c.duration - clip_dur
                    start = random.uniform(0, max(0, max_start))
                    c = c.subclipped(start, start + clip_dur)
                else:
                    c = c.subclipped(0, min(c.duration, clip_dur))

                # Apply Ken Burns effect
                c = _short_ken_burns(c)

                # Fade transition
                if c.duration > 0.6:
                    c = c.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.3)])

                clips.append(c)
            except Exception:
                clips.append(
                    ColorClip((SHORTS_WIDTH, SHORTS_HEIGHT), (15, 15, 20), duration=clip_dur)
                )

        footage_seq = concatenate_videoclips(clips).subclipped(0, footage_duration)
        video = concatenate_videoclips([impact_bg, footage_seq]).subclipped(0, duration)
    else:
        video = ColorClip((SHORTS_WIDTH, SHORTS_HEIGHT), (15, 15, 20), duration=duration)

    # ── Subtitle overlays — bold, bottom-third, with bg box ──
    cap_size = getattr(caption_style, "font_size", 85)
    cap_color = getattr(caption_style, "color", "white")
    cap_stroke = getattr(caption_style, "stroke_width", 4)
    cap_y = getattr(caption_style, "position", 0.78)
    cap_upper = getattr(caption_style, "uppercase", True)
    # Integer alpha, not a float — PIL rejects "rgba(0,0,0,0.65)" and the
    # subtitle clip is then silently dropped. 166 is 0.65 * 255.
    cap_bg = "rgba(0,0,0,166)" if getattr(caption_style, "box", True) else None

    sub_clips = []
    for sub in subtitles:
        if sub["end"] > duration:
            break
        dur = sub["end"] - sub["start"]
        if dur <= 0:
            continue
        try:
            cap_text = sub["text"].upper() if cap_upper else sub["text"]
            cap_font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            cap_box = caption_box_size(cap_text, cap_font, cap_size,
                                       cap_stroke, SHORTS_WIDTH - 120)
            txt = (
                TextClip(
                    text=cap_text,
                    font_size=cap_size,
                    color=cap_color,
                    bg_color=cap_bg,
                    stroke_color="black",
                    stroke_width=cap_stroke,
                    font=cap_font,
                    method="caption",
                    size=cap_box,
                    text_align="center",
                    transparent=True,
                )
                .with_position(("center", cap_y), relative=True)
                .with_start(sub["start"])
                .with_duration(dur)
            )
            sub_clips.append(txt)
        except Exception:
            pass

    # ── Hook text overlay — GIANT impact text during text-only intro,
    # then a smaller sustain version once footage begins.
    hook_overlays = []
    if hook_text:
        try:
            # 1) Giant centered impact text during the dark intro (0 → 1.5s)
            impact_clip = (
                TextClip(
                    text=hook_text.upper(),
                    font_size=150,
                    color="#FFD700",  # gold
                    stroke_color="black",
                    stroke_width=6,
                    font="/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                    method="caption",
                    size=(SHORTS_WIDTH - 60, None),
                    text_align="center",
                    transparent=True,
                )
                .with_position("center")
                .with_start(0)
                .with_duration(IMPACT_DURATION)
                .with_effects([vfx.FadeIn(0.15)])
            )
            hook_overlays.append(impact_clip)

            # 2) Smaller sustain hook once footage appears (1.5 → 3.0s)
            sustain_clip = (
                TextClip(
                    text=hook_text.upper(),
                    font_size=95,
                    color="#FFD700",
                    stroke_color="black",
                    stroke_width=5,
                    font="/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                    method="caption",
                    size=(SHORTS_WIDTH - 100, None),
                    text_align="center",
                    transparent=True,
                )
                .with_position(("center", 0.22), relative=True)
                .with_start(IMPACT_DURATION)
                .with_duration(1.5)
                .with_effects([vfx.FadeIn(0.2), vfx.FadeOut(0.4)])
            )
            hook_overlays.append(sustain_clip)
        except Exception:
            pass

    # ── Compose everything ──────────────────────────────
    final = CompositeVideoClip(
        [video] + sub_clips + hook_overlays,
        size=(SHORTS_WIDTH, SHORTS_HEIGHT),
    ).with_audio(narration)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(output_path),
        fps=SHORTS_FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        preset="medium",
        threads=4,
    )

    final.close()
    narration.close()
    print(f"  Short saved: {output_path} ({duration:.1f}s)")
    return output_path


if __name__ == "__main__":
    print("Shorts generator v2 ready. Use extract_hook_for_short() + create_short().")
