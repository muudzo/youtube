"""
YouTube Uploader — auto-upload videos, thumbnails, and Shorts to YouTube.
Uses YouTube Data API v3 with OAuth 2.0.

Security:
- OAuth 2.0 flow (no raw API keys for YouTube)
- Credentials stored with 600 permissions (owner-only)
- Token auto-refreshes, never stored in code or logs
- client_secret.json and token.json are gitignored

First run will open a browser for Google login — after that, the token is cached.
"""

import os
import stat
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BASE_DIR

# Minimum required scopes — principle of least privilege
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"

# Which channel this process uploads to. One OAuth token authorises exactly one
# channel, so a second channel needs its own token file — otherwise the Dutch
# daemon would publish onto the English channel. brainrot.py sets
# YOUTUBE_TOKEN_FILE=token_nl.json before any upload happens.
TOKEN_FILE = BASE_DIR / os.getenv("YOUTUBE_TOKEN_FILE", "token.json")


def _sanitize_text(text: str) -> str:
    """Remove any file paths, API keys, or system info from text before uploading."""
    import re
    # Remove absolute file paths
    text = re.sub(r"/Users/\S+", "", text)
    text = re.sub(r"[A-Z]:\\[^\s]+", "", text)
    # Remove anything that looks like an API key (long alphanumeric strings)
    text = re.sub(r"(?:sk-|gsk_|AIza)[A-Za-z0-9_-]{20,}", "[REDACTED]", text)
    return text.strip()


def _secure_file_permissions(filepath: Path):
    """Set file to owner-only read/write (chmod 600)."""
    filepath.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _validate_credentials_file(filepath: Path):
    """Validate that a credentials file exists and has safe permissions."""
    if not filepath.exists():
        return False
    # Check permissions — warn if too open
    file_stat = filepath.stat()
    mode = file_stat.st_mode
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        print(f"  Warning: {filepath.name} is readable by others, fixing permissions...")
        _secure_file_permissions(filepath)
    return True

# YouTube category IDs
CATEGORIES = {
    "education": "27",
    "entertainment": "24",
    "science": "28",
    "people": "22",
    "howto": "26",
    "news": "25",
}


def get_authenticated_service():
    """Authenticate and return a YouTube API service object."""
    creds = None

    # Load cached token if it exists and has safe permissions
    if TOKEN_FILE.exists():
        _validate_credentials_file(TOKEN_FILE)
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"Missing {CLIENT_SECRET_FILE}\n"
                    "Download OAuth credentials from Google Cloud Console:\n"
                    "  1. console.cloud.google.com → APIs & Services → Credentials\n"
                    "  2. Create OAuth 2.0 Client ID (Desktop app)\n"
                    "  3. Download JSON → rename to client_secret.json\n"
                    "  4. Place in project root"
                )
            _validate_credentials_file(CLIENT_SECRET_FILE)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            # Use loopback redirect (localhost) — never expose on network
            creds = flow.run_local_server(
                port=8080,
                open_browser=True,
                bind_addr="127.0.0.1",  # localhost only, not 0.0.0.0
            )

        # Save token with restricted permissions
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        _secure_file_permissions(TOKEN_FILE)

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    category: str = "education",
    privacy: str = "public",
    is_short: bool = False,
    publish_at: str = None,
    synthetic_media: bool = False,
    language: str = None,
) -> str:
    """
    Upload a video to YouTube.

    Args:
        video_path: Path to the video file
        title: Video title
        description: Video description
        tags: List of tags
        category: Category name (education, entertainment, etc.)
        privacy: "public", "unlisted", or "private"
        is_short: If True, adds #Shorts to title
        publish_at: ISO 8601 datetime for scheduled publish (e.g. "2026-03-25T15:00:00Z")
        synthetic_media: Declares altered/synthetic content via
            status.containsSyntheticMedia. Set this whenever the narration is
            AI-generated — undisclosed synthetic content is the fastest route
            to an inauthentic-content strike.
        language: BCP-47 code (e.g. "nl") set as both the video's default
            language and its default audio language, so YouTube surfaces it to
            the right audience instead of guessing from an English-heavy channel.

    Returns:
        Video ID of the uploaded video
    """
    youtube = get_authenticated_service()

    # Sanitize inputs — strip file paths, keys, or system info that could leak
    title = _sanitize_text(title)
    description = _sanitize_text(description)

    # Sanitize tags — YouTube rejects special chars, stopwords, and overly long tags
    import re
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'it'}
    clean_tags = []
    for t in (tags or []):
        t = re.sub(r'[^a-zA-Z0-9\s-]', '', _sanitize_text(t)).strip()
        if len(t) > 2 and t.lower() not in stopwords and len(t) < 50:
            clean_tags.append(t)
    # Deduplicate and cap at 15
    seen = set()
    tags = []
    for t in clean_tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
        if len(tags) >= 15:
            break

    if is_short and "#Shorts" not in title:
        title = f"{title} #Shorts"

    # Truncate title to YouTube's 100 char limit
    if len(title) > 100:
        title = title[:97] + "..."

    category_id = CATEGORIES.get(category, "27")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy if not publish_at else "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    if language:
        body["snippet"]["defaultLanguage"] = language
        body["snippet"]["defaultAudioLanguage"] = language

    if synthetic_media:
        body["status"]["containsSyntheticMedia"] = True

    # Schedule for later if publish_at is set
    if publish_at:
        body["status"]["publishAt"] = publish_at
        body["status"]["privacyStatus"] = "private"

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"  Uploading: {title}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload progress: {pct}%")

    video_id = response["id"]
    print(f"  Uploaded! Video ID: {video_id}")
    print(f"  URL: https://youtube.com/watch?v={video_id}")

    return video_id


def set_thumbnail(video_id: str, thumbnail_path: str) -> bool:
    """Upload a custom thumbnail for a video."""
    youtube = get_authenticated_service()

    try:
        media = MediaFileUpload(thumbnail_path, mimetype="image/png")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
        print(f"  Thumbnail set for {video_id}")
        return True
    except Exception as e:
        print(f"  Warning: Thumbnail upload failed: {e}")
        print("  (Custom thumbnails require a verified account)")
        return False


def upload_with_thumbnail(
    video_path: str,
    thumbnail_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    category: str = "education",
    privacy: str = "public",
    is_short: bool = False,
    publish_at: str = None,
    synthetic_media: bool = False,
    language: str = None,
) -> str:
    """Upload a video and set its custom thumbnail.

    ``synthetic_media`` and ``language`` are forwarded to upload_video; see
    its docstring.
    """
    video_id = upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        category=category,
        privacy=privacy,
        is_short=is_short,
        publish_at=publish_at,
        synthetic_media=synthetic_media,
        language=language,
    )

    # Wait a moment for YouTube to process
    time.sleep(3)

    if thumbnail_path and Path(thumbnail_path).exists():
        set_thumbnail(video_id, thumbnail_path)

    return video_id


def upload_pipeline_output(result: dict, privacy: str = "public", publish_at: str = None) -> dict:
    """
    Upload all outputs from a pipeline run.
    Takes the result dict returned by pipeline.run_pipeline().
    """
    uploaded = {}

    # Upload long-form video
    if result.get("video_path") and Path(result["video_path"]).exists():
        print("\n[UPLOAD] Long-form video...")
        video_id = upload_with_thumbnail(
            video_path=result["video_path"],
            thumbnail_path=result.get("thumbnail_path", ""),
            title=result["title"],
            description=result.get("description", ""),
            tags=result.get("tags", []),
            privacy=privacy,
            publish_at=publish_at,
        )
        uploaded["video_id"] = video_id
        uploaded["video_url"] = f"https://youtube.com/watch?v={video_id}"

    return uploaded


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upload video to YouTube")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", nargs="+", default=[], help="Video tags")
    parser.add_argument("--thumbnail", help="Path to thumbnail image")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    parser.add_argument("--short", action="store_true", help="Mark as YouTube Short")
    parser.add_argument("--schedule", help="Schedule publish (ISO 8601: 2026-03-25T15:00:00Z)")

    args = parser.parse_args()

    if args.thumbnail:
        upload_with_thumbnail(
            video_path=args.video,
            thumbnail_path=args.thumbnail,
            title=args.title,
            description=args.description,
            tags=args.tags,
            privacy=args.privacy,
            is_short=args.short,
            publish_at=args.schedule,
        )
    else:
        upload_video(
            video_path=args.video,
            title=args.title,
            description=args.description,
            tags=args.tags,
            privacy=args.privacy,
            is_short=args.short,
            publish_at=args.schedule,
        )
