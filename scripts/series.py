"""One series per channel: ordered episodes, branded titles, one playlist.

Each channel publishes a single named series defined in series/<channel>.json.
Both daemons go through produce_next_episode(), which:

  1. holds a per-series lock, so a manual run next to the daemon cannot
     publish the same episode twice,
  2. recovers an episode that reached YouTube just before a crash/kill (found
     by its numbered title) instead of uploading it again,
  3. makes sure the series playlist exists (re-adding any episode that
     uploaded but never made it into the playlist),
  4. renders + uploads the next episode under the shared render lock (the
     channel pipeline deletes local files after a confirmed upload),
  5. adds the upload to the playlist and records it.

Episode numbers follow what viewers see on YouTube (published order), so an
episode that keeps failing is skipped without leaving a gap in the numbering.
"""

import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MIN_FREE_DISK_GB, OUTPUT_DIR, RENDER_LOCK_FILE
from scripts.render_lock import RenderBusyError, render_lock

# An episode whose render fails this many times is skipped so one bad topic
# cannot wedge the whole series.
MAX_ATTEMPTS = 3
# Upload failures are counted separately and allowed more often: new channels
# hit YouTube's daily upload cap, which says nothing about the episode itself.
MAX_UPLOAD_ATTEMPTS = 6
YOUTUBE_TITLE_LIMIT = 100
# The series suffix must leave most of the 100 characters for the real title.
MAX_TITLE_FORMAT_OVERHEAD = 40
# How far back in the channel's uploads to look when recovering from a crash.
RECENT_UPLOADS_CHECKED = 25

# Daemon back-off per outcome (see retry_delay_seconds).
SERIES_DONE_SLEEP_SECONDS = 6 * 3600
SERIES_RETRY_SLEEP_SECONDS = 30 * 60
UPLOAD_RETRY_SLEEP_SECONDS = 3 * 3600
CHANNELS = ("en", "nl")
_REQUIRED_KEYS = ("id", "channel", "playlist_title", "title_format", "episodes")
_DEFAULT_LABELS = {
    "series_line": "Episode {n} of {series}",
    "full_series": "Full series",
    "previous": "Previous episode",
}

ProduceFn = Callable[["Episode"], dict]
YouTubeFactory = Callable[[], object]


class SeriesConfigError(ValueError):
    """A series file or series state file is missing, malformed or invalid."""


@dataclass(frozen=True)
class Series:
    id: str
    channel: str
    language: str
    playlist_title: str
    playlist_description: str
    title_format: str
    series_line: str
    full_series_label: str
    previous_label: str
    episodes: tuple[str, ...]

    @property
    def state_file(self) -> Path:
        return OUTPUT_DIR / f"series_{self.id}_state.json"


@dataclass(frozen=True)
class Episode:
    series: Series
    number: int
    topic: str
    playlist_id: str | None = None
    previous_video_id: str | None = None

    def title(self, base: str) -> str:
        """The script's title with the series suffix, kept within YouTube's limit."""
        fmt = self.series.title_format
        full = fmt.format(title=base, n=self.number)
        if len(full) <= YOUTUBE_TITLE_LIMIT:
            return full
        overflow = len(full) - YOUTUBE_TITLE_LIMIT
        trimmed = base[: max(0, len(base) - overflow - 1)].rstrip(" ,:;-|") + "…"
        return fmt.format(title=trimmed, n=self.number)

    def description_block(self) -> str:
        """Series footer appended to the long-form description."""
        s = self.series
        lines = ["──────────", s.series_line.format(n=self.number, series=s.playlist_title)]
        if self.playlist_id:
            lines.append(f"▶ {s.full_series_label}: {playlist_url(self.playlist_id)}")
        if self.previous_video_id:
            lines.append(f"◀ {s.previous_label}: https://youtu.be/{self.previous_video_id}")
        return "\n\n" + "\n".join(lines)


def title_pattern(series: Series, number: int) -> re.Pattern:
    """Regex matching any title this series gives episode ``number``."""
    escaped = re.escape(series.title_format)
    escaped = escaped.replace(re.escape("{title}"), ".+").replace(re.escape("{n}"), str(number))
    return re.compile(escaped, re.S)


def playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


# ─── Loading ─────────────────────────────────────────────


def _validate_title_format(fmt: str) -> None:
    if "{title}" not in fmt or "{n}" not in fmt:
        raise SeriesConfigError(f"title_format must contain {{title}} and {{n}}: {fmt!r}")
    try:
        fmt.format(title="x", n=1)
    except (KeyError, IndexError, ValueError) as e:
        raise SeriesConfigError(f"title_format has an unknown placeholder: {fmt!r} ({e})") from e
    overhead = len(fmt.format(title="", n=999))
    if overhead > MAX_TITLE_FORMAT_OVERHEAD:
        raise SeriesConfigError(
            f"title_format adds {overhead} characters; keep it under "
            f"{MAX_TITLE_FORMAT_OVERHEAD} so the real title fits in {YOUTUBE_TITLE_LIMIT}"
        )


def _validate_series_line(line: str) -> None:
    try:
        line.format(n=1, series="x")
    except (KeyError, IndexError, ValueError) as e:
        raise SeriesConfigError(
            f"labels.series_line may only use {{n}} and {{series}}: {line!r} ({e})"
        ) from e


def _validate_episodes(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise SeriesConfigError("episodes must be a non-empty list of topics")
    episodes = tuple(str(t).strip() for t in raw)
    if any(not t for t in episodes):
        raise SeriesConfigError("episodes must not contain blank topics")
    keys = [_key(t) for t in episodes]
    duplicates = sorted({t for t, k in zip(episodes, keys) if keys.count(k) > 1})
    if duplicates:
        raise SeriesConfigError(f"duplicate episodes: {duplicates}")
    return episodes


def load_series(path: Path) -> Series:
    """Read and validate a series definition file."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SeriesConfigError(f"cannot read series file {path}: {e}") from e
    if not isinstance(data, dict):
        raise SeriesConfigError(f"{path} must contain a JSON object")

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise SeriesConfigError(f"{path.name} is missing {missing}")
    if data["channel"] not in CHANNELS:
        raise SeriesConfigError(f"channel must be one of {CHANNELS}, got {data['channel']!r}")
    _validate_title_format(data["title_format"])
    labels = {**_DEFAULT_LABELS, **data.get("labels", {})}
    _validate_series_line(labels["series_line"])

    return Series(
        id=str(data["id"]),
        channel=data["channel"],
        language=data.get("language", data["channel"]),
        playlist_title=str(data["playlist_title"]),
        playlist_description=str(data.get("playlist_description", "")),
        title_format=data["title_format"],
        series_line=labels["series_line"],
        full_series_label=labels["full_series"],
        previous_label=labels["previous"],
        episodes=_validate_episodes(data["episodes"]),
    )


# ─── State ───────────────────────────────────────────────


def _empty_state() -> dict:
    return {"playlist_id": None, "published": [], "failures": {}}


def load_state(path: Path) -> dict:
    """Read series progress. A corrupt file raises instead of resetting.

    Silently resetting would restart the series at episode 1 and re-upload
    everything already published, so this fails loudly instead.
    """
    path = Path(path)
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SeriesConfigError(
            f"series state {path} is unreadable ({e}). Restore it; deleting it "
            f"restarts the series at episode 1 and re-uploads published episodes."
        ) from e
    return {**_empty_state(), **data}


def save_state(state: dict, path: Path) -> None:
    """Persist series progress atomically so a crash cannot corrupt it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(path)


def _key(topic: str) -> str:
    return topic.strip().casefold()


def next_episode(series: Series, state: dict) -> Episode | None:
    """The first episode not yet published and not given up on, or None."""
    published = state["published"]
    done = {_key(p["topic"]) for p in published}
    for topic in series.episodes:
        if _key(topic) in done:
            continue
        if _given_up(state["failures"].get(topic, {})):
            continue
        return Episode(
            series=series,
            number=len(published) + 1,
            topic=topic,
            playlist_id=state.get("playlist_id"),
            previous_video_id=published[-1]["video_id"] if published else None,
        )
    return None


def record_published(state: dict, episode: Episode, video_id: str,
                     in_playlist: bool, now: datetime | None = None) -> dict:
    """Return a new state with the episode marked as published."""
    now = now or datetime.now(timezone.utc)
    entry = {
        "number": episode.number,
        "topic": episode.topic,
        "video_id": video_id,
        "in_playlist": in_playlist,
        "published_at": now.isoformat(),
    }
    failures = {k: v for k, v in state["failures"].items() if k != episode.topic}
    return {**state, "published": [*state["published"], entry], "failures": failures}


def _given_up(failure: dict) -> bool:
    return (failure.get("count", 0) >= MAX_ATTEMPTS
            or failure.get("upload_count", 0) >= MAX_UPLOAD_ATTEMPTS)


def record_failure(state: dict, topic: str, error: object, kind: str = "render") -> dict:
    """Return a new state with one more failed attempt for this topic.

    ``kind="upload"`` means the video rendered but never reached YouTube; it
    is counted separately so upload caps don't skip good episodes.
    """
    previous = state["failures"].get(topic, {})
    entry = {
        "count": previous.get("count", 0) + (kind == "render"),
        "upload_count": previous.get("upload_count", 0) + (kind == "upload"),
        "last_error": str(error)[:300],
    }
    return {**state, "failures": {**state["failures"], topic: entry}}


def describe(series: Series, state: dict) -> str:
    """Human-readable progress for status commands and logs."""
    published = state["published"]
    upcoming = next_episode(series, state)
    lines = [f"{series.playlist_title} [{series.channel}]: "
             f"{len(published)}/{len(series.episodes)} episodes published"]
    if state.get("playlist_id"):
        lines.append(f"  Playlist: {playlist_url(state['playlist_id'])}")
    for p in published[-3:]:
        lines.append(f"  Ep. {p['number']}: {p['topic']} -> https://youtu.be/{p['video_id']}")
    for topic, failure in state["failures"].items():
        if _given_up(failure):
            lines.append(f"  Skipped after repeated failures: {topic} "
                         f"({failure.get('last_error', '')})")
    if upcoming:
        lines.append(f"  Next: Ep. {upcoming.number}: {upcoming.topic}")
    else:
        lines.append("  Series complete. Add episodes to the series file to continue.")
    return "\n".join(lines)


# ─── YouTube playlist ────────────────────────────────────


def _playlist_exists(youtube, playlist_id: str) -> bool:
    response = youtube.playlists().list(part="id", id=playlist_id).execute()
    return bool(response.get("items"))


def ensure_playlist(youtube, series: Series, state: dict) -> dict:
    """Return a state whose playlist_id exists on YouTube, creating it if needed."""
    old_id = state.get("playlist_id")
    if old_id and _playlist_exists(youtube, old_id):
        return state

    body = {
        "snippet": {
            "title": series.playlist_title,
            "description": series.playlist_description,
            "defaultLanguage": series.language,
        },
        "status": {"privacyStatus": "public"},
    }
    created = youtube.playlists().insert(part="snippet,status", body=body).execute()
    print(f"  Created series playlist: {playlist_url(created['id'])}")

    published = state["published"]
    if old_id:
        # The old playlist is gone (deleted on YouTube), so every published
        # episode needs adding to the new one.
        print(f"  Previous playlist {old_id} no longer exists; re-adding episodes.")
        published = [{**p, "in_playlist": False} for p in published]
    return {**state, "playlist_id": created["id"], "published": published}


def add_to_playlist(youtube, playlist_id: str, video_id: str) -> bool:
    """Append a video to the playlist. Returns False instead of raising.

    A failure here must not undo a successful upload; the episode is recorded
    with in_playlist=False and sync_playlist() retries it on the next run.
    """
    body = {"snippet": {"playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    try:
        youtube.playlistItems().insert(part="snippet", body=body).execute()
        return True
    except Exception as e:  # HttpError, transport errors: all retried later
        print(f"  Warning: could not add {video_id} to playlist {playlist_id}: {e}")
        return False


def sync_playlist(youtube, series: Series, state: dict) -> dict:
    """Ensure the playlist exists and retry any episode missing from it."""
    state = ensure_playlist(youtube, series, state)
    playlist_id = state["playlist_id"]
    published = [
        p if p.get("in_playlist") else
        {**p, "in_playlist": add_to_playlist(youtube, playlist_id, p["video_id"])}
        for p in state["published"]
    ]
    return {**state, "published": published}


# ─── Crash recovery ──────────────────────────────────────


def find_uploaded_episode(youtube, series: Series, number: int) -> str | None:
    """Video id of episode ``number`` among the channel's recent uploads."""
    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = channels.get("items", [])
    if not items:
        return None
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    recent = youtube.playlistItems().list(
        part="snippet", playlistId=uploads, maxResults=RECENT_UPLOADS_CHECKED
    ).execute().get("items", [])
    pattern = title_pattern(series, number)
    for item in recent:
        snippet = item["snippet"]
        if pattern.fullmatch(snippet.get("title", "")):
            return snippet["resourceId"]["videoId"]
    return None


def recover_in_flight(youtube, series: Series, state: dict) -> dict:
    """Resolve an attempt that was interrupted (crash, kill, reboot).

    If the episode reached YouTube it is recorded (the playlist add is left to
    sync_playlist); otherwise the marker is dropped and the episode retried.
    """
    in_flight = state.get("in_flight")
    cleared = {k: v for k, v in state.items() if k != "in_flight"}
    if not in_flight:
        return cleared
    number = int(in_flight["number"])
    if number != len(cleared["published"]) + 1:
        return cleared  # stale marker from an older state
    video_id = find_uploaded_episode(youtube, series, number)
    if not video_id:
        print(f"  Interrupted attempt at episode {number} never reached YouTube; retrying.")
        return cleared
    print(f"  Recovered episode {number}, uploaded before an interruption: "
          f"https://youtu.be/{video_id}")
    episode = Episode(series=series, number=number, topic=in_flight["topic"])
    return record_published(cleared, episode, video_id, in_playlist=False)


# ─── Runner ──────────────────────────────────────────────


def free_disk_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1024 ** 3


def series_lock_file(state_path: Path) -> Path:
    return Path(state_path).with_name(Path(state_path).name + ".lock")


def retry_delay_seconds(result: dict | None) -> int:
    """How long a daemon should wait after this outcome before the next try."""
    if result is None:
        return SERIES_DONE_SLEEP_SECONDS
    return {
        "skipped": SERIES_RETRY_SLEEP_SECONDS,
        "failed": SERIES_RETRY_SLEEP_SECONDS,
        "upload_failed": UPLOAD_RETRY_SLEEP_SECONDS,
    }.get(result.get("status"), 0)


def _disk_too_full(episode: Episode) -> dict | None:
    free = free_disk_gb(OUTPUT_DIR)
    if free >= MIN_FREE_DISK_GB:
        return None
    return {"status": "skipped", "topic": episode.topic,
            "reason": f"only {free:.1f} GB free on disk, need {MIN_FREE_DISK_GB:.0f} GB"}


def _render(episode: Episode, produce_fn: ProduceFn) -> dict:
    """Run the channel pipeline under the cross-channel render lock."""
    print(f"\n  {episode.series.playlist_title}: episode {episode.number}: {episode.topic}")
    with render_lock(RENDER_LOCK_FILE):
        return produce_fn(episode)


def _rendered(result: dict) -> bool:
    path = result.get("video_path")
    return bool(path) and Path(path).exists()


def _attempt(state: dict, episode: Episode, produce_fn: ProduceFn, youtube) -> tuple[dict, dict]:
    """Render + upload one episode. Returns (new state, result)."""
    meta = {"topic": episode.topic, "episode": episode.number}
    try:
        result = _render(episode, produce_fn)
    except Exception as e:  # any render/upload crash counts as one attempt
        print(f"  Episode failed: {e}")
        return record_failure(state, episode.topic, e), {**meta, "status": "failed", "error": str(e)}

    base = {**result, **meta}
    video_id = result.get("video_id")
    if video_id:
        in_playlist = add_to_playlist(youtube, state["playlist_id"], video_id)
        new_state = record_published(state, episode, video_id, in_playlist)
        return new_state, {**base, "status": "success", "in_playlist": in_playlist}
    if _rendered(result):
        error = "rendered, but the upload failed"
        return (record_failure(state, episode.topic, error, kind="upload"),
                {**base, "status": "upload_failed", "error": error})
    error = "no video was produced"
    return record_failure(state, episode.topic, error), {**base, "status": "failed", "error": error}


def _publish_next(series: Series, state_path: Path, produce_fn: ProduceFn,
                  youtube_factory: YouTubeFactory) -> dict | None:
    state = load_state(state_path)
    try:
        youtube = youtube_factory()
        state = sync_playlist(youtube, series, recover_in_flight(youtube, series, state))
    except Exception as e:  # missing token, wrong channel, network: retry later
        return {"status": "skipped", "reason": f"YouTube unavailable: {e}"}
    save_state(state, state_path)

    episode = next_episode(series, state)
    if episode is None:
        return None
    too_full = _disk_too_full(episode)
    if too_full:
        return too_full

    # Marker so an interruption after the upload is recovered, not re-uploaded.
    marker = {"number": episode.number, "topic": episode.topic,
              "started_at": datetime.now(timezone.utc).isoformat()}
    save_state({**state, "in_flight": marker}, state_path)
    new_state, result = _attempt(state, episode, produce_fn, youtube)
    save_state(new_state, state_path)
    return result


def _render_only(series: Series, state_path: Path, produce_fn: ProduceFn) -> dict | None:
    episode = next_episode(series, load_state(state_path))
    if episode is None:
        return None
    too_full = _disk_too_full(episode)
    if too_full:
        return too_full
    try:
        result = _render(episode, produce_fn)
    except Exception as e:  # render-only: report, record nothing
        print(f"  Episode failed: {e}")
        return {"status": "failed", "topic": episode.topic, "error": str(e)}
    return {**result, "topic": episode.topic, "episode": episode.number, "status": "rendered"}


def produce_next_episode(series: Series, state_path: Path, produce_fn: ProduceFn,
                         youtube_factory: YouTubeFactory, upload: bool = True) -> dict | None:
    """Produce the next episode. Returns None once the series is complete.

    Statuses: "success" (uploaded and recorded), "failed" (render attempt
    counted), "upload_failed" (rendered, upload attempt counted), "skipped"
    (nothing attempted: low disk, YouTube unavailable, or another process is
    already publishing this series), "rendered" (render-only run). A
    render-only run (upload=False) records nothing and never authenticates.
    """
    if not upload:
        return _render_only(series, state_path, produce_fn)
    try:
        with render_lock(series_lock_file(state_path), blocking=False):
            return _publish_next(series, state_path, produce_fn, youtube_factory)
    except RenderBusyError:
        return {"status": "skipped", "reason": "another process is already publishing this series"}
