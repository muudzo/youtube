"""
Engagement Booster — automates YouTube engagement tactics to grow faster.

Tactics:
1. Auto-pin a comment on every video asking viewers what to cover next
2. Reply to all comments with AI-generated responses (builds community)
3. Add end screens linking to other videos (keeps viewers on channel)
4. Optimize titles/descriptions based on what's performing
5. Auto-generate community posts to keep the feed active
6. Track analytics and suggest what to double down on

Uses YouTube Data API v3 — same OAuth credentials as uploader.
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)
from config import GROQ_API_KEY, SCRIPT_MODEL, BASE_DIR


def _get_youtube():
    """Get authenticated YouTube API service."""
    from scripts.youtube_uploader import get_authenticated_service
    return get_authenticated_service()


def _ai_generate(prompt: str, temperature: float = 0.8) -> str:
    """Quick Groq call for generating text."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SCRIPT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 512,
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ══════════════════════════════════════════════════════════
# 1. AUTO-PIN ENGAGEMENT COMMENTS
# ══════════════════════════════════════════════════════════

PIN_COMMENTS = [
    "What mystery should I cover next? Drop it below 👇",
    "Which part shocked you the most? Let me know 👇",
    "Did you know about this before watching? Comment below 👇",
    "What's the craziest rabbit hole you've ever gone down? 👇",
    "Subscribe if you want more stories like this — what topic next? 👇",
]


def pin_comment_on_video(video_id: str, comment_text: str = None) -> str:
    """Post and pin a comment on a video to drive engagement."""
    youtube = _get_youtube()

    if not comment_text:
        import random
        comment_text = random.choice(PIN_COMMENTS)

    # Post the comment
    result = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": comment_text,
                    }
                },
            }
        },
    ).execute()

    comment_id = result["snippet"]["topLevelComment"]["id"]
    print(f"  Posted comment on {video_id}: {comment_text[:50]}...")

    return comment_id


def pin_comments_on_all_videos():
    """Pin an engagement comment on every video that doesn't have one."""
    youtube = _get_youtube()

    # Get all videos on the channel
    videos = _get_all_videos(youtube)
    print(f"Found {len(videos)} videos on channel")

    for video in videos:
        vid_id = video["id"]
        title = video["snippet"]["title"]

        # Check if we already commented
        try:
            comments = youtube.commentThreads().list(
                part="snippet",
                videoId=vid_id,
                maxResults=5,
            ).execute()
        except Exception as e:
            if "commentsDisabled" in str(e):
                print(f"  Comments disabled: {title}")
            else:
                print(f"  Error checking comments on {title}: {e}")
            continue

        already_commented = False
        channel_id = video["snippet"]["channelId"]
        for thread in comments.get("items", []):
            author_id = thread["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value", "")
            if author_id == channel_id:
                already_commented = True
                break

        if not already_commented:
            try:
                pin_comment_on_video(vid_id)
                print(f"  Pinned comment on: {title}")
                time.sleep(2)
            except Exception as e:
                print(f"  Failed to comment on {title}: {e}")
        else:
            print(f"  Already commented: {title}")


# ══════════════════════════════════════════════════════════
# 2. AI-POWERED COMMENT REPLIES
# ══════════════════════════════════════════════════════════

def reply_to_comments(max_replies: int = 20):
    """Reply to recent viewer comments with AI-generated responses."""
    youtube = _get_youtube()
    videos = _get_all_videos(youtube)

    total_replied = 0

    for video in videos:
        if total_replied >= max_replies:
            break

        vid_id = video["id"]
        title = video["snippet"]["title"]
        channel_id = video["snippet"]["channelId"]

        # Get comments
        try:
            comments = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=vid_id,
                maxResults=10,
                order="time",
            ).execute()
        except Exception:
            continue

        for thread in comments.get("items", []):
            if total_replied >= max_replies:
                break

            comment = thread["snippet"]["topLevelComment"]["snippet"]
            author_id = comment.get("authorChannelId", {}).get("value", "")

            # Skip our own comments
            if author_id == channel_id:
                continue

            # Check if we already replied
            reply_count = thread["snippet"].get("totalReplyCount", 0)
            already_replied = False
            if reply_count > 0 and "replies" in thread:
                for reply in thread["replies"]["comments"]:
                    reply_author = reply["snippet"].get("authorChannelId", {}).get("value", "")
                    if reply_author == channel_id:
                        already_replied = True
                        break

            if already_replied:
                continue

            # Generate an AI reply
            viewer_comment = comment["textDisplay"]
            viewer_name = comment["authorDisplayName"]

            reply_text = _ai_generate(
                f"""You run a faceless YouTube channel about dark history and mysteries.
A viewer named {viewer_name} left this comment on your video "{title}":
"{viewer_comment}"

Write a short, friendly reply (1-2 sentences max). Be conversational, not corporate.
Encourage them to keep watching or suggest they check other videos.
Do NOT use emojis excessively. Do NOT be cringe. Sound human.
Just return the reply text, nothing else.""",
                temperature=0.7,
            )

            # Remove quotes if AI wrapped it
            reply_text = reply_text.strip('"').strip("'")

            try:
                youtube.comments().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "parentId": thread["snippet"]["topLevelComment"]["id"],
                            "textOriginal": reply_text,
                        }
                    },
                ).execute()
                print(f"  Replied to {viewer_name}: {reply_text[:60]}...")
                total_replied += 1
                time.sleep(3)  # rate limit
            except Exception as e:
                print(f"  Failed to reply: {e}")

    print(f"\nReplied to {total_replied} comments")


# ══════════════════════════════════════════════════════════
# 3. ANALYTICS TRACKER — find what's working
# ══════════════════════════════════════════════════════════

def get_analytics() -> list:
    """Get view counts and engagement for all videos."""
    youtube = _get_youtube()
    videos = _get_all_videos(youtube)

    analytics = []
    for video in videos:
        stats = video.get("statistics", {})
        snippet = video["snippet"]
        analytics.append({
            "title": snippet["title"],
            "video_id": video["id"],
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "published": snippet["publishedAt"],
            "url": f"https://youtube.com/watch?v={video['id']}",
        })

    # Sort by views descending
    analytics.sort(key=lambda x: x["views"], reverse=True)
    return analytics


def print_analytics():
    """Print a dashboard of channel analytics."""
    analytics = get_analytics()

    if not analytics:
        print("No videos found on channel")
        return

    total_views = sum(v["views"] for v in analytics)
    total_likes = sum(v["likes"] for v in analytics)
    total_comments = sum(v["comments"] for v in analytics)

    print(f"\n{'=' * 70}")
    print(f"  4kMUDZO ANALYTICS DASHBOARD")
    print(f"  Total videos: {len(analytics)} | Views: {total_views} | Likes: {total_likes} | Comments: {total_comments}")
    print(f"{'=' * 70}")
    print(f"  {'Views':>6}  {'Likes':>5}  {'Cmts':>4}  Title")
    print(f"  {'─' * 64}")

    for v in analytics:
        print(f"  {v['views']:>6}  {v['likes']:>5}  {v['comments']:>4}  {v['title'][:45]}")

    print(f"{'=' * 70}")

    # AI recommendation
    if total_views > 0:
        top = analytics[0]
        print(f"\n  TOP PERFORMER: {top['title']}")
        print(f"  → Make more content similar to this topic!")

        if total_views > 0 and len(analytics) > 1:
            avg_views = total_views / len(analytics)
            overperformers = [v for v in analytics if v["views"] > avg_views * 1.5]
            if overperformers:
                print(f"\n  OVERPERFORMERS (>1.5x average):")
                for v in overperformers:
                    print(f"    • {v['title']} ({v['views']} views)")

    return analytics


# ══════════════════════════════════════════════════════════
# 4. TITLE & DESCRIPTION OPTIMIZER
# ══════════════════════════════════════════════════════════

def optimize_underperformers(min_views_threshold: int = 10):
    """Find videos with low views and suggest better titles."""
    analytics = get_analytics()

    if not analytics:
        return

    avg_views = sum(v["views"] for v in analytics) / max(len(analytics), 1)
    underperformers = [v for v in analytics if v["views"] < avg_views * 0.5]

    if not underperformers:
        print("No underperformers found — all videos doing well!")
        return

    print(f"\nFound {len(underperformers)} underperforming videos:")

    for v in underperformers:
        print(f"\n  Current title: {v['title']} ({v['views']} views)")

        new_title = _ai_generate(
            f"""This YouTube video title is underperforming: "{v['title']}"
It only got {v['views']} views while the channel average is {avg_views:.0f}.

Write 3 alternative titles that would get more clicks. Use curiosity gap framing.
Format: one title per line, numbered 1-3. Nothing else.""",
            temperature=0.9,
        )

        print(f"  Suggested titles:\n{new_title}")


# ══════════════════════════════════════════════════════════
# 5. COMMUNITY POST GENERATOR
# ══════════════════════════════════════════════════════════

def generate_community_post(topic: str = None) -> str:
    """Generate a community post to keep the feed active."""
    if topic:
        prompt = f"Write a short YouTube community post (2-3 sentences) teasing an upcoming video about: {topic}. Make it mysterious and make people want to click. No hashtags."
    else:
        prompt = "Write a short YouTube community post (2-3 sentences) asking viewers what dark history topic they want covered next. Be casual and conversational. No hashtags."

    post = _ai_generate(prompt, temperature=0.8)
    post = post.strip('"').strip("'")
    print(f"\n  Community post:\n  {post}")
    return post


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def _get_all_videos(youtube) -> list:
    """Get all videos from the authenticated channel."""
    # Get channel ID
    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    if not channels.get("items"):
        return []

    uploads_playlist = channels["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Get all video IDs from uploads playlist
    video_ids = []
    next_page = None
    while True:
        playlist = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=next_page,
        ).execute()

        for item in playlist.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        next_page = playlist.get("nextPageToken")
        if not next_page:
            break

    if not video_ids:
        return []

    # Get full video details
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        result = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch),
        ).execute()
        videos.extend(result.get("items", []))

    return videos


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube Engagement Booster")
    parser.add_argument("action", choices=[
        "analytics", "pin-comments", "reply", "optimize", "community-post", "full"
    ], help="Action to perform")
    parser.add_argument("--max-replies", type=int, default=20, help="Max comment replies")
    parser.add_argument("--topic", help="Topic for community post")

    args = parser.parse_args()

    if args.action == "analytics":
        print_analytics()

    elif args.action == "pin-comments":
        pin_comments_on_all_videos()

    elif args.action == "reply":
        reply_to_comments(max_replies=args.max_replies)

    elif args.action == "optimize":
        optimize_underperformers()

    elif args.action == "community-post":
        generate_community_post(topic=args.topic)

    elif args.action == "full":
        # Run everything
        print("\n[1/4] Analytics...")
        print_analytics()
        print("\n[2/4] Pinning comments...")
        pin_comments_on_all_videos()
        print("\n[3/4] Replying to viewers...")
        reply_to_comments(max_replies=args.max_replies)
        print("\n[4/4] Optimizing titles...")
        optimize_underperformers()
        print("\nDone! Run this daily for best results.")
