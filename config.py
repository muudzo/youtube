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
# Groq decommissioned the Llama models; llama-3.3-70b-versatile now 404s.
# Verified 2026-09-14 against the live catalogue: qwen3.8-27b is the pick.
# It honours the per-section length requirement (1552 words / 10 min on the
# Deltawerken test), returns clean JSON at max_tokens=8192, and produces
# specific English visual keywords. openai/gpt-oss-120b is a reasoning model
# that spends the token budget on reasoning and returns truncated JSON at
# 8192, needing 16384+ — which does not fit the free tier's 8000 TPM.
SCRIPT_MODEL = "qwen/qwen3.8-27b"

# Groq free tier is 8000 tokens/minute across all models. One video makes three
# Groq calls (script, SEO title, Short hook) back to back, so they contend for
# the same minute's budget — hence the 429 backoff in the callers.
GROQ_TPM_LIMIT = 8000
NICHE = "dark_history_rabbit_holes"
TARGET_VIDEO_LENGTH_MINUTES = 10  # aim for 8-15 min for algorithm
WORDS_PER_MINUTE = 150  # narration pace

# ─── Subtitle Settings ──────────────────────────────────
SUBTITLE_FONT_SIZE = 78           # bigger for mobile readability
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_STROKE_COLOR = "black"
SUBTITLE_STROKE_WIDTH = 4
SUBTITLE_POSITION = "bottom"      # bottom-third placement
# Pillow's rgba() specifier takes an INTEGER alpha (0-255), not a 0-1 float.
# This previously read "rgba(0,0,0,0.6)", which PIL rejects; create_subtitle_clips
# swallows the failure, so every boxed subtitle was silently dropped and videos
# rendered with no captions at all. 153 is 0.6 * 255.
SUBTITLE_BG_COLOR = "rgba(0,0,0,153)"  # semi-transparent dark box
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

# ─── Local Storage / Cleanup ────────────────────────────
# After a confirmed YouTube upload, delete the heavy local artifacts
# (rendered video/short, audio, subtitles, thumbnails, downloaded footage)
# so videos are never stored on the machine. Only the small script JSON
# and logs are kept. Override per-run with --keep-local.
KEEP_LOCAL_AFTER_UPLOAD = os.getenv("KEEP_LOCAL_AFTER_UPLOAD", "false").lower() == "true"

# ─── YouTube API Quota (units/day) ──────────────────────
# The Data API v3 grants 10,000 units/day by default. Each videos.insert
# costs 1,600 units; a thumbnails.set costs ~50. The autopilot tracks
# spend per day and stops producing once the budget is exhausted, then
# resumes after the quota resets at midnight US/Pacific.
DAILY_UPLOAD_UNIT_BUDGET = int(os.getenv("DAILY_UPLOAD_UNIT_BUDGET", "10000"))
UPLOAD_UNIT_COST = 1600        # videos.insert
THUMBNAIL_UNIT_COST = 50       # thumbnails.set
# Quota resets at 00:00 US/Pacific (UTC-8, ignoring DST for a safe margin).
QUOTA_RESET_UTC_HOUR = 8

# ─── Autopilot Pacing ───────────────────────────────────
# Seconds to wait between back-to-back productions in continuous mode.
PRODUCTION_COOLDOWN_SECONDS = int(os.getenv("PRODUCTION_COOLDOWN_SECONDS", "120"))


# ══════════════════════════════════════════════════════════
# DUTCH BRAINROT CHANNEL (nl)
# ══════════════════════════════════════════════════════════
# A separate surface from the English dark-history pipeline above: fresh
# channel, Dutch narration, brainrot pacing. Implementation lives in
# scripts/nl/. Nothing here affects the English pipeline.
#
# Why Dutch: NL CPM sits around $5.50 and nearly every Dutch creator makes
# English content, so the Dutch-language lane is underserved. Brainrot Shorts
# themselves pay $0.02-$0.12 RPM — they are the funnel, not the revenue.
# Long-form past 8 minutes unlocks mid-rolls and is where the money actually is.

NL_LANGUAGE_CODE = "nl"
NL_DEFAULT_REGION = "NL"

# Long-form target, chosen against the 8-minute mid-roll threshold.
NL_TARGET_VIDEO_LENGTH_MINUTES = 10

# Measured, and deliberately NOT the average. Two generated scripts on the same
# topic rendered at 94.8 and 121.8 wpm: Dutch compound nouns
# ("stormvloedkering") eat far more time per word than short ones, so the rate
# swings ~28% with vocabulary alone. Budget at the fast end, because the error
# is asymmetric -- a 13-minute video costs nothing, a 7:50 video loses every
# mid-roll and with it the entire revenue case.
#
#   10 min x 125 = 1250 words -> 10.2 min at the fast end, 13.2 at the slow end.
NL_WORDS_PER_MINUTE = 125

# The model reliably overshoots a stated minimum, so the prompt states a band.
# Upper bound = lower bound * this.
NL_SECTION_WORD_TOLERANCE = 1.3

# ─── Upload cadence governor ────────────────────────────
# YouTube's inauthentic-content policy flags "an upload pace no human
# editorial process could sustain". The English daemon runs until the API
# quota is gone (~3 pairs/day); this channel is deliberately capped lower
# and jittered so the cadence reads as human.
NL_MAX_UPLOADS_PER_DAY = int(os.getenv("NL_MAX_UPLOADS_PER_DAY", "2"))
NL_MIN_HOURS_BETWEEN_UPLOADS = float(os.getenv("NL_MIN_HOURS_BETWEEN_UPLOADS", "5"))
NL_UPLOAD_JITTER_MINUTES = int(os.getenv("NL_UPLOAD_JITTER_MINUTES", "90"))

# ─── Synthetic media disclosure ─────────────────────────
# Sets status.containsSyntheticMedia on videos.insert. Required for AI
# narration to stay monetizable; undisclosed synthetic content is the
# fastest route to a strike.
NL_DECLARE_SYNTHETIC_MEDIA = True

# ─── Channel identity ───────────────────────────────────
# The Dutch channel is a separate YouTube channel with its own OAuth token.
# scripts/youtube_uploader.py reads YOUTUBE_TOKEN_FILE; brainrot.py sets it.
NL_TOKEN_FILE = "token_nl.json"

# ─── State ──────────────────────────────────────────────
NL_STATE_FILE = OUTPUT_DIR / "nl_autopilot_state.json"
