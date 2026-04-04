#!/usr/bin/env python3
"""
Batch Video Generator — produce multiple videos from a topic list.

Usage:
    python batch.py topics.txt
    python batch.py topics.txt --tts google --no-footage

topics.txt format (one topic per line):
    The Dyatlov Pass Incident
    MK Ultra CIA Mind Control
    The Lost Colony of Roanoke
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(override=True)

from pipeline import run_pipeline


def load_topics(filepath: str) -> list:
    """Load topics from a text file, one per line."""
    topics = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                topics.append(line)
    return topics


def run_batch(
    topics: list,
    tts_provider: str = None,
    thumbnail_style: str = "dark_mystery",
    skip_footage: bool = False,
    skip_video: bool = False,
):
    """Run the pipeline for multiple topics."""
    results = []
    total = len(topics)

    print(f"\n{'=' * 60}")
    print(f"  BATCH MODE — {total} videos queued")
    print(f"{'=' * 60}\n")

    for i, topic in enumerate(topics, 1):
        print(f"\n{'─' * 60}")
        print(f"  [{i}/{total}] {topic}")
        print(f"{'─' * 60}")

        try:
            result = run_pipeline(
                topic=topic,
                tts_provider=tts_provider,
                thumbnail_style=thumbnail_style,
                skip_footage=skip_footage,
                skip_video=skip_video,
            )
            result["status"] = "success"
            results.append(result)
        except Exception as e:
            print(f"\n  ERROR: {e}")
            results.append({"topic": topic, "status": "failed", "error": str(e)})

    # Save batch report
    report_path = Path("output") / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = total - success

    print(f"\n{'=' * 60}")
    print(f"  BATCH COMPLETE")
    print(f"  Success: {success}/{total} | Failed: {failed}")
    print(f"  Report:  {report_path}")
    print(f"{'=' * 60}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Batch video generator")
    parser.add_argument("topics_file", help="Path to topics file (one topic per line)")
    parser.add_argument("--tts", choices=["openai", "elevenlabs", "google"], help="TTS provider")
    parser.add_argument("--style", choices=["dark_mystery", "red_alert"], default="dark_mystery")
    parser.add_argument("--no-footage", action="store_true", help="Skip stock footage")
    parser.add_argument("--no-video", action="store_true", help="Skip video assembly")

    args = parser.parse_args()
    topics = load_topics(args.topics_file)

    if not topics:
        print("No topics found in file!")
        sys.exit(1)

    run_batch(
        topics=topics,
        tts_provider=args.tts,
        thumbnail_style=args.style,
        skip_footage=args.no_footage,
        skip_video=args.no_video,
    )


if __name__ == "__main__":
    main()
