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
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(override=True)

from pipeline import run_pipeline
from scripts.topic_researcher import research_topics, save_topics


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


def produce_video(topic: str, upload: bool = True) -> dict:
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
        )
        result["status"] = "success"
        return result
    except Exception as e:
        print(f"\n  ERROR: {e}")
        return {"topic": topic, "status": "failed", "error": str(e)}


def run_batch(num_videos: int = 1, upload: bool = True):
    """Produce multiple videos."""
    state = load_state()

    for i in range(num_videos):
        topic = get_next_topic(state)
        print(f"\n[{i + 1}/{num_videos}] Next topic: {topic}")

        result = produce_video(topic, upload=upload)

        # Update state
        state["produced_topics"].append(topic)
        state["total_videos"] += 1
        if result.get("short_path"):
            state["total_shorts"] += 1
        save_state(state)

        log_event({
            "action": "video_produced",
            "topic": topic,
            "status": result.get("status", "unknown"),
            "video_url": result.get("video_url", ""),
            "short_url": result.get("short_url", ""),
        })

        # Wait between videos to avoid rate limits
        if i < num_videos - 1:
            print("\n  Cooling down 60s before next video...")
            time.sleep(60)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"  AUTOPILOT BATCH COMPLETE")
    print(f"  Videos produced: {num_videos}")
    print(f"  Total lifetime videos: {state['total_videos']}")
    print(f"{'=' * 60}")


def run_daemon(interval_hours: int = 8):
    """Run forever, producing videos on a schedule."""
    print(f"\n{'=' * 60}")
    print(f"  AUTOPILOT DAEMON MODE")
    print(f"  Producing 1 video + short every {interval_hours} hours")
    print(f"  Press Ctrl+C to stop")
    print(f"{'=' * 60}")

    running = True

    def handle_stop(sig, frame):
        nonlocal running
        print("\n  Stopping autopilot...")
        running = False

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    while running:
        run_batch(num_videos=1, upload=True)

        if not running:
            break

        next_run = datetime.now() + timedelta(hours=interval_hours)
        print(f"\n  Next video at: {next_run.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Sleeping {interval_hours} hours...")

        # Sleep in small chunks so we can respond to Ctrl+C
        sleep_seconds = interval_hours * 3600
        for _ in range(sleep_seconds):
            if not running:
                break
            time.sleep(1)

    print("  Autopilot stopped.")


def main():
    parser = argparse.ArgumentParser(description="YouTube Autopilot — automated video production")
    parser.add_argument("--videos", type=int, default=1, help="Number of videos to produce")
    parser.add_argument("--daemon", action="store_true", help="Run forever on schedule")
    parser.add_argument("--interval", type=int, default=8, help="Hours between videos in daemon mode")
    parser.add_argument("--research-only", action="store_true", help="Just research topics")
    parser.add_argument("--topic", help="Use a specific topic instead of auto-selecting")
    parser.add_argument("--no-upload", action="store_true", help="Generate but don't upload")

    args = parser.parse_args()

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
        result = produce_video(args.topic, upload=not args.no_upload)
        if result.get("video_url"):
            print(f"\n  YouTube: {result['video_url']}")
        return

    if args.daemon:
        run_daemon(interval_hours=args.interval)
    else:
        run_batch(num_videos=args.videos, upload=not args.no_upload)


if __name__ == "__main__":
    main()
