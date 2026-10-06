#!/usr/bin/env python3
"""
AUTOPILOT — Fully automated YouTube money printer.

Runs on a schedule: researches topics, generates videos, uploads,
and cross-promotes. Set it and forget it.

Usage:
    python autopilot.py                    # Run once (1 video + short)
    python autopilot.py --videos 3         # Produce 3 videos
    python autopilot.py --daemon           # Run forever on schedule
    python autopilot.py --research-only    # Just find topics, don't produce
    python autopilot.py --topic "Custom Topic Here"  # Use a specific topic
"""

import argparse
import json
import sys
import time
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(override=True)

from pipeline import run_pipeline
from scripts.topic_researcher import research_topics, save_topics
from config import (
    DAILY_UPLOAD_UNIT_BUDGET,
    UPLOAD_UNIT_COST,
    THUMBNAIL_UNIT_COST,
    QUOTA_RESET_UTC_HOUR,
    PRODUCTION_COOLDOWN_SECONDS,
)

# Units spent per uploaded asset: one videos.insert + one thumbnails.set.
COST_PER_UPLOAD = UPLOAD_UNIT_COST + THUMBNAIL_UNIT_COST


# ─── State tracking ─────────────────────────────────────
STATE_FILE = Path("output") / "autopilot_state.json"
LOG_FILE = Path("output") / "autopilot_log.json"


def load_state() -> dict:
    """Load autopilot state (tracks what's been produced)."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"produced_topics": [], "total_videos": 0, "total_shorts": 0}


def save_state(state: dict):
    """Save autopilot state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log_event(event: dict):
    """Append to the autopilot log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logs = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            logs = json.load(f)
    event["timestamp"] = datetime.now().isoformat()
    logs.append(event)
    # Keep last 100 entries
    logs = logs[-100:]
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)


# ─── YouTube API quota tracking ─────────────────────────
def _quota_window() -> str:
    """Key for the current daily quota window (resets at QUOTA_RESET_UTC_HOUR UTC)."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(hours=QUOTA_RESET_UTC_HOUR)).date().isoformat()


def _seconds_until_quota_reset() -> int:
    """Seconds until the next quota reset (QUOTA_RESET_UTC_HOUR UTC)."""
    now = datetime.now(timezone.utc)
    reset = now.replace(hour=QUOTA_RESET_UTC_HOUR, minute=0, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    return int((reset - now).total_seconds())


def quota_remaining(state: dict) -> int:
    """Units left in the current window. Resets the counter on day rollover."""
    window = _quota_window()
    if state.get("quota_window") != window:
        state["quota_window"] = window
        state["quota_units_used"] = 0
    return DAILY_UPLOAD_UNIT_BUDGET - state.get("quota_units_used", 0)


def charge_quota(state: dict, result: dict) -> int:
    """Add units actually spent by a run to the counter. Returns units charged."""
    quota_remaining(state)  # ensure the window is current first
    spent = 0
    if result.get("video_id"):
        spent += COST_PER_UPLOAD
    if result.get("short_id"):
        spent += COST_PER_UPLOAD
    state["quota_units_used"] = state.get("quota_units_used", 0) + spent
    return spent


def _interruptible_sleep(seconds: int, is_running) -> None:
    """Sleep in 1s chunks so SIGINT/SIGTERM is honored promptly."""
    for _ in range(max(0, int(seconds))):
        if not is_running():
            return
        time.sleep(1)


def get_next_topic(state: dict) -> str:
    """Get the next topic to produce — researches new ones if needed."""
    produced = set(state.get("produced_topics", []))

    # Try topics.txt first
    topics_file = Path("topics.txt")
    if topics_file.exists():
        with open(topics_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and line not in produced:
                    return line

    # All topics.txt used up — research new ones
    print("All preset topics used. Researching new trending topics...")
    topics = research_topics(count=10)
    for t in topics:
        title = t["title"] if isinstance(t, dict) else t
        if title not in produced:
            return title

    # Absolute fallback
    return f"The Most Mysterious Event of {datetime.now().year}"


def produce_video(topic: str, upload: bool = True, keep_local: bool = None) -> dict:
    """Produce a single video + short and optionally upload."""
    print(f"\n{'=' * 60}")
    print(f"  AUTOPILOT — Producing: {topic}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 60}")

    try:
        result = run_pipeline(
            topic=topic,
            upload=upload,
            upload_short=True,
            privacy="public",
            keep_local=keep_local,
        )
        result["status"] = "success"
        return result
    except Exception as e:
        print(f"\n  ERROR: {e}")
        return {"topic": topic, "status": "failed", "error": str(e)}


def produce_one(state: dict, upload: bool = True, keep_local: bool = None) -> dict:
    """Pick the next topic, produce it, then update state, quota, and the log."""
    topic = get_next_topic(state)
    print(f"\n  Next topic: {topic}")

    result = produce_video(topic, upload=upload, keep_local=keep_local)

    state["produced_topics"].append(topic)
    state["total_videos"] += 1
    if result.get("short_path"):
        state["total_shorts"] += 1
    spent = charge_quota(state, result) if upload else 0
    save_state(state)

    log_event({
        "action": "video_produced",
        "topic": topic,
        "status": result.get("status", "unknown"),
        "video_url": result.get("video_url", ""),
        "short_url": result.get("short_url", ""),
        "quota_spent": spent,
    })
    return result


def run_batch(num_videos: int = 1, upload: bool = True, keep_local: bool = None):
    """Produce a fixed number of videos back-to-back."""
    state = load_state()

    for i in range(num_videos):
        print(f"\n[{i + 1}/{num_videos}]")
        produce_one(state, upload=upload, keep_local=keep_local)

        # Cool down between videos to avoid rate limits / CPU pinning
        if i < num_videos - 1:
            print(f"\n  Cooling down {PRODUCTION_COOLDOWN_SECONDS}s before next video...")
            time.sleep(PRODUCTION_COOLDOWN_SECONDS)

    print(f"\n{'=' * 60}")
    print(f"  AUTOPILOT BATCH COMPLETE")
    print(f"  Videos produced this run: {num_videos}")
    print(f"  Total lifetime videos: {state['total_videos']}")
    print(f"{'=' * 60}")


def run_daemon(keep_local: bool = None):
    """Run forever, producing as many videos as the daily quota allows.

    Produces back-to-back until the YouTube upload quota is exhausted, then
    sleeps until the quota resets and resumes. launchd keeps this process
    alive across reboots.
    """
    print(f"\n{'=' * 60}")
    print(f"  AUTOPILOT DAEMON — maximum throughput mode")
    print(f"  Daily upload budget: {DAILY_UPLOAD_UNIT_BUDGET} units "
          f"(~{DAILY_UPLOAD_UNIT_BUDGET // (COST_PER_UPLOAD * 2)} video+short pairs/day)")
    print(f"  Press Ctrl+C to stop")
    print(f"{'=' * 60}")

    running = True

    def handle_stop(sig, frame):
        nonlocal running
        print("\n  Stopping autopilot...")
        running = False

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    state = load_state()

    while running:
        remaining = quota_remaining(state)

        # Need at least one upload's worth of budget to do anything useful.
        if remaining < COST_PER_UPLOAD:
            wait = _seconds_until_quota_reset()
            print(f"\n  Daily upload quota spent "
                  f"({state.get('quota_units_used', 0)}/{DAILY_UPLOAD_UNIT_BUDGET} units).")
            print(f"  Sleeping {wait / 3600:.1f}h until quota reset...")
            save_state(state)
            _interruptible_sleep(wait, lambda: running)
            continue

        produce_one(state, upload=True, keep_local=keep_local)

        if running:
            _interruptible_sleep(PRODUCTION_COOLDOWN_SECONDS, lambda: running)

    save_state(state)
    print("  Autopilot stopped.")


def main():
    parser = argparse.ArgumentParser(description="YouTube Autopilot — automated video production")
    parser.add_argument("--videos", type=int, default=1, help="Number of videos to produce")
    parser.add_argument("--daemon", action="store_true",
                        help="Run forever, producing as many videos as the daily quota allows")
    parser.add_argument("--auth", action="store_true",
                        help="One-time Google login for THIS (English) channel -> token.json")
    parser.add_argument("--research-only", action="store_true", help="Just research topics")
    parser.add_argument("--topic", help="Use a specific topic instead of auto-selecting")
    parser.add_argument("--no-upload", action="store_true", help="Generate but don't upload")
    parser.add_argument("--keep-local", action="store_true",
                        help="Keep local files after upload (default: delete to save space)")

    args = parser.parse_args()
    keep_local = True if args.keep_local else None

    if args.auth:
        # No YOUTUBE_TOKEN_FILE override here, so this writes token.json --
        # the English channel. The Dutch channel uses brainrot.py auth.
        from scripts.youtube_uploader import TOKEN_FILE, get_authenticated_service
        get_authenticated_service()
        print(f"  Authenticated. Token written to {TOKEN_FILE}")
        return

    if args.research_only:
        topics = research_topics(count=15)
        for i, t in enumerate(topics, 1):
            title = t["title"] if isinstance(t, dict) else t
            why = t.get("why", "") if isinstance(t, dict) else ""
            vol = t.get("search_volume", "") if isinstance(t, dict) else ""
            print(f"  {i:2d}. {title}")
            if why:
                print(f"      → {why} [{vol}]")
        save_topics(topics)
        return

    if args.topic:
        result = produce_video(args.topic, upload=not args.no_upload, keep_local=keep_local)
        if result.get("video_url"):
            print(f"\n  YouTube: {result['video_url']}")
        return

    if args.daemon:
        run_daemon(keep_local=keep_local)
    else:
        run_batch(num_videos=args.videos, upload=not args.no_upload, keep_local=keep_local)


if __name__ == "__main__":
    main()
