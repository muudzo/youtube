"""
Thumbnail Generator — creates BRIGHT, high-contrast, clickable YouTube thumbnails.
Uses stock footage frames as backgrounds with bold text overlays.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv; load_dotenv(override=True)
from config import THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, THUMBNAIL_DIR, THUMBNAIL_FONT_SIZE, STOCK_DIR


# ─── Font config ──────────────────────────────────────────
# Prefer Impact (the classic YouTube thumbnail font), fall back to Arial Bold
_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "arial.ttf",
]

# Boost font size well beyond the config default for maximum impact
_FONT_SIZE = max(THUMBNAIL_FONT_SIZE, 100)


def _load_font(size: int, preferred: str = None) -> ImageFont.FreeTypeFont:
    """Load ``preferred`` if it resolves, else the best available bold font."""
    candidates = [preferred, *_FONT_PATHS] if preferred else _FONT_PATHS
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ─── Frame extraction ─────────────────────────────────────

def extract_frame_from_video(video_path: Path, time_seconds: float = 1.0) -> Image.Image | None:
    """Extract a single frame from a video file using ffmpeg."""
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(time_seconds),
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                tmp_path,
            ],
            capture_output=True,
            timeout=15,
        )
        if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
            img = Image.open(tmp_path).convert("RGB")
            return img
    except Exception:
        pass
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return None


def _find_stock_clip(keywords: list[str]) -> Path | None:
    """Find a stock footage clip matching any of the given keywords."""
    if not STOCK_DIR.exists():
        return None

    clips = list(STOCK_DIR.glob("*.mp4"))
    # Try each keyword
    for kw in keywords:
        kw_lower = kw.lower()
        for clip in clips:
            if kw_lower in clip.stem.lower():
                return clip
    # Fall back to first clip available
    return clips[0] if clips else None


# ─── Background generators ────────────────────────────────

def _create_bold_gradient() -> Image.Image:
    """Create a BRIGHT, bold gradient background (not dark)."""
    img = Image.new("RGB", (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
    draw = ImageDraw.Draw(img)

    # Bold red-to-dark-orange gradient — eye-catching
    for y in range(THUMBNAIL_HEIGHT):
        ratio = y / THUMBNAIL_HEIGHT
        r = int(200 + ratio * 55)   # 200 → 255
        g = int(30 + ratio * 60)    # 30 → 90
        b = int(10 + ratio * 30)    # 10 → 40
        draw.line([(0, y), (THUMBNAIL_WIDTH, y)], fill=(r, g, b))

    return img


def _brighten_frame(img: Image.Image) -> Image.Image:
    """Ensure a video frame is bright and vibrant enough for a thumbnail."""
    # Boost brightness slightly
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.15)

    # Boost color saturation for vibrancy
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.3)

    # Increase contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.2)

    return img


# ─── Text rendering ───────────────────────────────────────

def _wrap_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        test_text = " ".join(current_line)
        bbox = draw.textbbox((0, 0), test_text, font=font)
        if bbox[2] - bbox[0] > max_width:
            current_line.pop()
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))

    return lines


def _parse_color(text_color: str) -> tuple[int, int, int]:
    """Resolve a CSS colour name or hex string to RGB.

    A name-only lookup used to collapse anything that was not "yellow" to
    white, which silently killed two of the four thumbnail treatments -- they
    pass hex. Pillow already knows both forms, so defer to it and keep white as
    the fallback for genuinely unparseable input.
    """
    try:
        return ImageColor.getrgb(text_color)[:3]
    except (ValueError, AttributeError):
        return (255, 255, 255)


def _add_text_overlay(img: Image.Image, text: str, text_color: str = "white",
                      font_path: str = None) -> Image.Image:
    """
    Add LARGE bold text with thick black stroke onto the thumbnail.
    A semi-transparent dark band is drawn behind the text area only,
    ensuring readability over any background.
    """
    text = text.upper()
    font = _load_font(_FONT_SIZE, font_path)

    # We work on a copy
    img = img.copy()
    draw = ImageDraw.Draw(img)

    # Wrap text
    max_text_width = THUMBNAIL_WIDTH - 100  # 50px padding each side
    lines = _wrap_text(draw, text, font, max_text_width)

    # Measure text block
    line_height = _FONT_SIZE + 14
    total_text_height = len(lines) * line_height
    y_start = (THUMBNAIL_HEIGHT - total_text_height) // 2

    # ── Draw semi-transparent dark overlay behind text area only ──
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    pad_x, pad_y = 40, 30
    overlay_draw.rounded_rectangle(
        [
            50 - pad_x,
            y_start - pad_y,
            THUMBNAIL_WIDTH - 50 + pad_x,
            y_start + total_text_height + pad_y,
        ],
        radius=20,
        fill=(0, 0, 0, 140),  # ~55% opacity black
    )
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    # Redraw after compositing
    draw = ImageDraw.Draw(img)

    fill = _parse_color(text_color)

    # Draw each line centered with thick black outline
    outline_width = 6
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (THUMBNAIL_WIDTH - text_w) // 2
        y = y_start + i * line_height

        # Thick black stroke (all directions)
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx * dx + dy * dy <= outline_width * outline_width:
                    draw.text((x + dx, y + dy), line, fill=(0, 0, 0), font=font)

        # Bright fill
        draw.text((x, y), line, fill=fill, font=font)

    return img


# ─── Public API ────────────────────────────────────────────

def create_thumbnail(
    text: str,
    video_path: Path = None,
    background_image_path: Path = None,
    output_path: Path = None,
    style: str = "bright",
    text_color: str = "white",
    stock_keywords: list[str] = None,
    font_path: str = None,
) -> Path:
    """
    Create a bright, high-contrast YouTube thumbnail.

    Priority for background:
      1. video_path  — extract a frame from this video
      2. stock_keywords — search assets/stock_footage/ for a matching clip
      3. background_image_path — use a static image
      4. Bold colored gradient fallback
    """

    img = None

    # 1) Try extracting frame from explicit video path
    if video_path and Path(video_path).exists():
        img = extract_frame_from_video(video_path)

    # 2) Try finding a stock clip by keywords
    if img is None and stock_keywords:
        clip = _find_stock_clip(stock_keywords)
        if clip:
            img = extract_frame_from_video(clip)

    # 3) Try static background image
    if img is None and background_image_path and Path(background_image_path).exists():
        img = Image.open(background_image_path).convert("RGB")

    # 4) Fallback: bold gradient
    if img is None:
        img = _create_bold_gradient()

    # Resize to thumbnail dimensions
    img = img.resize((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.LANCZOS)

    # Brighten & boost the background frame
    if style != "gradient_only":
        img = _brighten_frame(img)

    # Add text overlay
    img = _add_text_overlay(img, text, text_color=text_color, font_path=font_path)

    # Determine output path
    if output_path is None:
        safe_name = text.replace(" ", "_")[:40].lower()
        output_path = THUMBNAIL_DIR / f"{safe_name}_thumb.png"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), quality=95)
    print(f"  Thumbnail saved: {output_path}")
    return output_path


# ─── CLI / quick test ─────────────────────────────────────

if __name__ == "__main__":
    create_thumbnail(
        "DYATLOV PASS INCIDENT",
        stock_keywords=["snowy", "winter_landscape", "mountain_peak", "mountain"],
        output_path=THUMBNAIL_DIR / "the_dyatlov_pass_incident_thumb.png",
        text_color="white",
    )
    print("Thumbnail generated!")
