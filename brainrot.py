#!/usr/bin/env python3
"""
Nederlandse kanaal-entrypoint.

    python brainrot.py check                  # preflight: keys, deps, cadans
    python brainrot.py topics                 # live Nederlandse zoekvraag
    python brainrot.py produce "<onderwerp>"  # één video, geen upload
    python brainrot.py produce "<x>" --upload
    python brainrot.py daemon                 # continu, met cadansbegrenzer

Deliberately separate from autopilot.py: that daemon produces until the API
quota is dry, which is the upload pattern YouTube's inauthentic-content policy
flags. This one is governed by scripts/nl/cadence.py instead.
"""

import argparse
import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv

load_dotenv(override=True)

from config import NL_MAX_UPLOADS_PER_DAY, NL_STATE_FILE, NL_TOKEN_FILE, OUTPUT_DIR

# Point the uploader at THIS channel's OAuth token before anything imports it.
# scripts/youtube_uploader reads YOUTUBE_TOKEN_FILE at import time, and
# scripts/nl/produce imports it lazily inside _upload(), so setting it here is
# what keeps Dutch videos off the English channel.
os.environ.setdefault("YOUTUBE_TOKEN_FILE", NL_TOKEN_FILE)
from scripts.nl import cadence, safety
from scripts.nl.produce import UnsafeTopicError, produce
from scripts.nl.topics import discover_topics_nl, load_seed_topics, save_topics

LOG_FILE = OUTPUT_DIR / "nl_log.json"


def _log(event: dict) -> None:
    """Append an event, keeping the last 200."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if LOG_FILE.exists():
        try:
            history = json.loads(LOG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            history = []
    history.append({**event, "timestamp": datetime.now(timezone.utc).isoformat()})
    LOG_FILE.write_text(json.dumps(history[-200:], indent=2, ensure_ascii=False))


def next_topic(state: dict) -> str | None:
    """Pick the next unproduced, safe topic.

    Live discovery first (it reflects current demand), curated seeds as the
    floor when discovery returns nothing.
    """
    produced = set(state.get("produced", []))

    try:
        for topic in discover_topics_nl(limit=25):
            if topic.query not in produced and safety.is_safe(topic.query):
                return topic.query
    except Exception as e:
        print(f"  Ontdekking mislukt, val terug op topics_nl.txt: {e}")

    for topic in load_seed_topics():
        if topic not in produced and safety.is_safe(topic):
            return topic

    return None


def cmd_check() -> int:
    """Preflight. Reports what is missing rather than failing at upload time."""
    import os
    import shutil

    print("=" * 58)
    print("  PREFLIGHT — Nederlands kanaal")
    print("=" * 58)

    ok = True
    checks = [
        ("GROQ_API_KEY", bool(os.getenv("GROQ_API_KEY")), "scripts schrijven"),
        ("PEXELS_API_KEY", bool(os.getenv("PEXELS_API_KEY")), "beeldmateriaal"),
        ("client_secret.json", Path("client_secret.json").exists(), "OAuth-app"),
        (NL_TOKEN_FILE, Path(NL_TOKEN_FILE).exists(),
         "ingelogd NEDERLANDS kanaal"),
        ("ffmpeg", shutil.which("ffmpeg") is not None, "video renderen"),
    ]
    for name, present, purpose in checks:
        print(f"  [{'OK ' if present else 'MIS'}]  {name:<20} {purpose}")
        ok = ok and present

    state = cadence.load_state()
    print(f"\n  {cadence.describe(state)}")
    print(f"  Geproduceerd totaal: {len(state.get('produced', []))}")

    if not ok:
        print("\n  Ontbrekende onderdelen — zie DEPLOY.md. Zonder deze kan er")
        print("  wel gepland en ontdekt worden, maar niet gerenderd of geüpload.")
    return 0 if ok else 1


def cmd_topics(limit: int) -> int:
    """Show live Dutch search demand."""
    found = discover_topics_nl(limit=limit)
    print(f"\n{'Score':>6}  {'Cons':>4}  {'Type':<10}  Onderwerp")
    print(f"{'─' * 6}  {'─' * 4}  {'─' * 10}  {'─' * 50}")
    for topic in found:
        kind = "evergreen" if topic.is_evergreen else "actueel"
        print(f"{topic.score:>6.2f}  {topic.consensus:>4}  {kind:<10}  {topic.query[:55]}")
    print(f"\nOpgeslagen: {save_topics(found)}")
    return 0


def cmd_produce(topic: str, upload: bool, privacy: str, no_short: bool,
                keep_local: bool, salt: str) -> int:
    """Produce one video."""
    state = cadence.load_state()

    if upload:
        decision = cadence.check(state)
        if not decision.allowed:
            print(f"  Upload geblokkeerd door cadansbegrenzer: {decision.reason}")
            print(f"  Wacht {decision.wait_seconds / 3600:.1f} uur, of gebruik "
                  f"--no-upload om alleen te renderen.")
            return 2

    try:
        result = produce(
            topic=topic,
            upload=upload,
            make_short=not no_short,
            privacy=privacy,
            keep_local=keep_local or None,
            salt=salt,
        )
    except UnsafeTopicError as e:
        print(f"  {e}")
        return 3

    if result.get("video_id"):
        state = cadence.record_upload(state)
        state["produced"] = state.get("produced", []) + [topic]
        cadence.save_state(state)

    _log({
        "action": "produce",
        "topic": topic,
        "variant": result.get("variant"),
        "video_url": result.get("video_url", ""),
        "short_url": result.get("short_url", ""),
    })
    return 0


def cmd_daemon(keep_local: bool) -> int:
    """Produce continuously, governed by the cadence limiter."""
    print("=" * 58)
    print("  NEDERLANDS KANAAL — daemon")
    print(f"  Max {NL_MAX_UPLOADS_PER_DAY} uploads/dag, gejitterd")
    print(f"  State: {NL_STATE_FILE}")
    print("  Ctrl+C om te stoppen")
    print("=" * 58)

    running = True
    rng = random.Random()

    def stop(sig, frame):
        nonlocal running
        print("\n  Stoppen...")
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    def sleep_interruptibly(seconds: int) -> None:
        for _ in range(max(0, int(seconds))):
            if not running:
                return
            time.sleep(1)

    while running:
        state = cadence.load_state()
        decision = cadence.check(state)

        if not decision.allowed:
            print(f"\n  {decision.reason} — slaap "
                  f"{decision.wait_seconds / 3600:.1f}u")
            sleep_interruptibly(decision.wait_seconds + 60)
            continue

        # Wait for a Dutch viewing peak, then add jitter so the channel never
        # publishes on a detectable clock.
        delay = cadence.seconds_until_good_hour(rng=rng) + cadence.jitter_seconds(rng)
        if delay > 0:
            print(f"\n  Wacht {delay / 3600:.1f}u tot een goed uploadmoment...")
            sleep_interruptibly(delay)
            if not running:
                break

        topic = next_topic(state)
        if not topic:
            print("  Geen onderwerpen meer. Vul topics_nl.txt aan.")
            sleep_interruptibly(3600)
            continue

        print(f"\n  Volgend onderwerp: {topic}")
        try:
            result = produce(topic=topic, upload=True, keep_local=keep_local or None)
        except UnsafeTopicError as e:
            print(f"  Overgeslagen: {e}")
            state["produced"] = state.get("produced", []) + [topic]
            cadence.save_state(state)
            continue
        except Exception as e:
            print(f"  Productie mislukt: {e}")
            _log({"action": "failed", "topic": topic, "error": str(e)})
            sleep_interruptibly(600)
            continue

        state = cadence.load_state()
        if result.get("video_id"):
            state = cadence.record_upload(state)
        state["produced"] = state.get("produced", []) + [topic]
        cadence.save_state(state)

        _log({
            "action": "produce",
            "topic": topic,
            "variant": result.get("variant"),
            "video_url": result.get("video_url", ""),
        })
        print(f"  {cadence.describe(state)}")

    print("  Daemon gestopt.")
    return 0


def cmd_auth() -> int:
    """One-time Google login for THIS channel.

    Exists so nobody has to remember to set YOUTUBE_TOKEN_FILE by hand: the
    module sets it above, so the token lands in token_nl.json instead of
    overwriting the English channel's token.json.
    """
    from scripts.youtube_uploader import get_authenticated_service

    token = Path(NL_TOKEN_FILE)
    if token.exists():
        print(f"  {NL_TOKEN_FILE} bestaat al. Verwijder het eerst om opnieuw in te loggen.")
        return cmd_whoami()

    print("=" * 58)
    print("  INLOGGEN — NEDERLANDS KANAAL")
    print("=" * 58)
    print("\n  Er opent een browser. LET OP bij het kiezen:")
    print("  - Kies het NIEUWE kanaal, niet het bestaande.")
    print("  - Google toont eerst het account, daarna het kanaal.")
    print("  - Verkeerd gekozen? Sluit af en verwijder token_nl.json.\n")

    get_authenticated_service()
    print(f"\n  {NL_TOKEN_FILE} aangemaakt. Controle:\n")
    return cmd_whoami()


def cmd_whoami() -> int:
    """Show which channel token_nl.json controls, before anything is published."""
    from scripts.nl.channel_guard import WrongChannelError, assert_distinct_channels

    token = Path(NL_TOKEN_FILE)
    if not token.exists():
        print(f"  {NL_TOKEN_FILE} ontbreekt — nog niet ingelogd.")
        print("  Draai: ./setup.sh")
        return 1

    try:
        identity = assert_distinct_channels(token, Path("token.json"))
    except WrongChannelError as e:
        print("\n  FOUT — VERKEERD KANAAL\n")
        print(f"  {e}")
        return 1

    if identity is None:
        print("  Token geldig, maar dit account heeft geen kanaal.")
        return 1

    print(f"\n  Nederlands kanaal: {identity['title']}")
    print(f"  Kanaal-ID:         {identity['id']}")
    print(f"  https://youtube.com/channel/{identity['id']}\n")
    print("  Klopt dit NIET? Verwijder token_nl.json en log opnieuw in.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nederlands YouTube-kanaal — productie en publicatie"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Preflight: keys, deps, cadans")
    sub.add_parser("auth", help="Eenmalig inloggen op het Nederlandse kanaal")
    sub.add_parser("whoami", help="Welk kanaal bestuurt token_nl.json?")

    p_topics = sub.add_parser("topics", help="Live Nederlandse zoekvraag tonen")
    p_topics.add_argument("--limit", type=int, default=20)

    p_produce = sub.add_parser("produce", help="Eén video produceren")
    p_produce.add_argument("topic")
    p_produce.add_argument("--upload", action="store_true")
    p_produce.add_argument("--privacy", choices=["public", "unlisted", "private"],
                           default="public")
    p_produce.add_argument("--no-short", action="store_true")
    p_produce.add_argument("--keep-local", action="store_true")
    p_produce.add_argument("--salt", default="",
                           help="Forceer een andere variant voor hetzelfde onderwerp")

    p_daemon = sub.add_parser("daemon", help="Continu produceren")
    p_daemon.add_argument("--keep-local", action="store_true")

    args = parser.parse_args()

    if args.command == "check":
        return cmd_check()
    if args.command == "auth":
        return cmd_auth()
    if args.command == "whoami":
        return cmd_whoami()
    if args.command == "topics":
        return cmd_topics(args.limit)
    if args.command == "produce":
        return cmd_produce(args.topic, args.upload, args.privacy,
                           args.no_short, args.keep_local, args.salt)
    if args.command == "daemon":
        return cmd_daemon(args.keep_local)
    return 1


if __name__ == "__main__":
    sys.exit(main())
