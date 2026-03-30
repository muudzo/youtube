"""
Configuration for the Faceless YouTube Video Pipeline.
Dark History / Rabbit Holes niche.
ALL FREE — no paid APIs required.
"""

import os
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
VIDEO_DIR = OUTPUT_DIR / "videos"
THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails"
AUDIO_DIR = OUTPUT_DIR / "audio"
SUBTITLE_DIR = OUTPUT_DIR / "subtitles"
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"
STOCK_DIR = ASSETS_DIR / "stock_footage"
TEMPLATES_DIR = BASE_DIR / "templates"

# ─── API Keys (all free tier) ───────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")      # Free: https://console.groq.com/keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")   # Free: https://aistudio.google.com/apikey
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")   # Free: https://www.pexels.com/api/

# ─── Video Settings ─────────────────────────────────────
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30
VIDEO_FORMAT = "mp4"

# Shorts settings
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_FPS = 30

# ─── Audio / TTS Settings ───────────────────────────────
TTS_PROVIDER = "edge"  # "edge" (free, best quality), "google" (free fallback)
EDGE_TTS_VOICE = "en-US-GuyNeural"  # deep male narrator — perfect for dark history

# ─── Script Generation ──────────────────────────────────
SCRIPT_MODEL = "llama-3.3-70b-versatile"  # Groq free tier — fast + smart
NICHE = "dark_history_rabbit_holes"
TARGET_VIDEO_LENGTH_MINUTES = 10  # aim for 8-15 min for algorithm
WORDS_PER_MINUTE = 150  # narration pace

# ─── Subtitle Settings ──────────────────────────────────
SUBTITLE_FONT_SIZE = 78           # bigger for mobile readability
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_STROKE_COLOR = "black"
SUBTITLE_STROKE_WIDTH = 4
SUBTITLE_POSITION = "bottom"      # bottom-third placement
SUBTITLE_BG_COLOR = "rgba(0,0,0,0.6)"  # semi-transparent dark box
MAX_WORDS_PER_SUBTITLE = 5       # short punchy subtitles

# ─── Thumbnail Settings ─────────────────────────────────
THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720
THUMBNAIL_FONT_SIZE = 80

# ─── Background Music ───────────────────────────────────
BG_MUSIC_VOLUME = 0.08  # keep it low, narration is king

# ─── Pexels Stock Footage ───────────────────────────────
PEXELS_VIDEO_ORIENTATION = "landscape"
PEXELS_VIDEO_SIZE = "large"  # "large", "medium", "small"
MIN_CLIP_DURATION = 5  # seconds per stock clip
MAX_CLIP_DURATION = 10
