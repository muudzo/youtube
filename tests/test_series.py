"""Tests for the one-series-per-channel runner.

The series runner is what both daemons now publish through, so its contract is
the thing that keeps episodes numbered, in order, in their playlist, and never
double-counted. YouTube is replaced by an in-memory fake throughout.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EN_SERIES_FILE, NL_SERIES_FILE
from scripts import series as series_mod
from scripts.nl import safety
from scripts.render_lock import render_lock
from scripts.series import (
    MAX_ATTEMPTS,
    MAX_UPLOAD_ATTEMPTS,
    SERIES_RETRY_SLEEP_SECONDS,
    UPLOAD_RETRY_SLEEP_SECONDS,
    YOUTUBE_TITLE_LIMIT,
    Episode,
    SeriesConfigError,
    add_to_playlist,
    ensure_playlist,
    load_series,
    load_state,
    next_episode,
    produce_next_episode,
    record_failure,
    record_published,
    retry_delay_seconds,
    sync_playlist,
)

VALID = {
    "id": "vanished",
    "channel": "en",
    "language": "en",
    "playlist_title": "Vanished Without a Trace",
    "playlist_description": "Cases.",
    "title_format": "{title} | Vanished Ep. {n}",
    "labels": {
        "series_line": "Episode {n} of {series}",
        "full_series": "Full series",
        "previous": "Previous episode",
    },
    "episodes": ["Topic A", "Topic B", "Topic C"],
}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "series.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def series(tmp_path):
    return load_series(_write(tmp_path, VALID))


# ─── Fake YouTube client ─────────────────────────────────


class _Call:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class FakeYouTube:
    """Just enough of the Data API surface for playlists and playlistItems."""

    def __init__(self, existing_playlists=(), fail_item_insert=False, uploads=()):
        self.uploads = list(uploads)  # (title, video_id) newest first
        self.playlists_store = set(existing_playlists)
        self.items: list[tuple[str, str]] = []
        self.created: list[dict] = []
        self.fail_item_insert = fail_item_insert

    def playlists(self):
        fake = self

        class _Playlists:
            def list(self, part, id):
                return _Call(lambda: {"items": [{"id": id}] if id in fake.playlists_store else []})

            def insert(self, part, body):
                def run():
                    new_id = f"PL{len(fake.created) + 1}"
                    fake.created.append(body)
                    fake.playlists_store.add(new_id)
                    return {"id": new_id}
                return _Call(run)

        return _Playlists()

    def playlistItems(self):
        fake = self

        class _Items:
            def list(self, part, playlistId, maxResults):
                return _Call(lambda: {"items": [
                    {"snippet": {"title": t, "resourceId": {"videoId": v}}} for t, v in fake.uploads
                ]})

            def insert(self, part, body):
                def run():
                    if fake.fail_item_insert:
                        raise RuntimeError("playlistNotFound")
                    snippet = body["snippet"]
                    fake.items.append((snippet["playlistId"], snippet["resourceId"]["videoId"]))
                    return {"id": "item"}
                return _Call(run)

        return _Items()

    def channels(self):
        class _Channels:
            def list(self, part, mine):
                return _Call(lambda: {"items": [
                    {"contentDetails": {"relatedPlaylists": {"uploads": "UUmine"}}}]})

        return _Channels()


# ─── Loading ─────────────────────────────────────────────


def test_a_valid_series_file_loads(series):
    assert series.id == "vanished"
    assert series.channel == "en"
    assert series.episodes == ("Topic A", "Topic B", "Topic C")


@pytest.mark.parametrize("missing", ["id", "channel", "playlist_title", "title_format", "episodes"])
def test_a_series_file_missing_a_required_key_is_rejected(tmp_path, missing):
    data = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(SeriesConfigError):
        load_series(_write(tmp_path, data))


@pytest.mark.parametrize("bad", [
    {"episodes": []},
    {"episodes": ["Same", "same "]},
    {"channel": "fr"},
    {"title_format": "{title} without a number"},
    {"title_format": "Ep. {n} without a title"},
])
def test_invalid_series_definitions_are_rejected(tmp_path, bad):
    with pytest.raises(SeriesConfigError):
        load_series(_write(tmp_path, {**VALID, **bad}))


def test_a_series_line_with_an_unknown_placeholder_is_rejected_before_any_render(tmp_path):
    data = {**VALID, "labels": {**VALID["labels"], "series_line": "Episode {num} of {series}"}}
    with pytest.raises(SeriesConfigError):
        load_series(_write(tmp_path, data))


def test_a_title_format_that_leaves_no_room_for_the_title_is_rejected(tmp_path):
    with pytest.raises(SeriesConfigError):
        load_series(_write(tmp_path, {**VALID, "title_format": "{title}" + " x" * 40 + " {n}"}))


def test_both_shipped_series_load_and_target_their_own_channel():
    en = load_series(EN_SERIES_FILE)
    nl = load_series(NL_SERIES_FILE)
    assert (en.channel, nl.channel) == ("en", "nl")
    assert en.id != nl.id


def test_every_dutch_episode_passes_the_safety_gate():
    """An unsafe episode would burn its retries and leave a gap in the series."""
    nl = load_series(NL_SERIES_FILE)
    blocked = [t for t in nl.episodes if not safety.is_safe(t)]
    assert blocked == []


def test_a_missing_state_file_starts_an_empty_series(tmp_path):
    assert load_state(tmp_path / "nope.json") == {"playlist_id": None, "published": [], "failures": {}}


# ─── Picking the next episode ────────────────────────────


def test_the_first_episode_is_number_one_with_no_previous(series):
    ep = next_episode(series, load_state(Path("/nonexistent")))
    assert (ep.number, ep.topic, ep.previous_video_id) == (1, "Topic A", None)


def test_the_next_episode_links_back_to_the_previous_upload(series):
    state = record_published(load_state(Path("/x")), next_episode(series, load_state(Path("/x"))),
                             "vid1", in_playlist=True)
    ep = next_episode(series, {**state, "playlist_id": "PL1"})
    assert (ep.number, ep.topic, ep.previous_video_id, ep.playlist_id) == (2, "Topic B", "vid1", "PL1")


def test_an_episode_that_keeps_failing_is_skipped_without_leaving_a_number_gap(series):
    state = load_state(Path("/x"))
    for _ in range(MAX_ATTEMPTS):
        state = record_failure(state, "Topic A", "render crashed")

    ep = next_episode(series, state)

    # Numbering follows what viewers see on YouTube, not the file order.
    assert (ep.number, ep.topic) == (1, "Topic B")


def test_a_finished_series_has_no_next_episode(series):
    state = load_state(Path("/x"))
    for i, topic in enumerate(series.episodes):
        ep = Episode(series=series, number=i + 1, topic=topic)
        state = record_published(state, ep, f"vid{i}", in_playlist=True)
    assert next_episode(series, state) is None


def test_recording_does_not_mutate_the_previous_state(series):
    state = load_state(Path("/x"))
    ep = next_episode(series, state)
    record_published(state, ep, "vid1", in_playlist=True)
    record_failure(state, "Topic A", "x")
    assert state == {"playlist_id": None, "published": [], "failures": {}}


# ─── Titles and descriptions ─────────────────────────────


def test_a_short_title_gets_the_series_suffix(series):
    ep = Episode(series=series, number=3, topic="Topic C")
    assert ep.title("Amelia Earhart's Last Flight") == "Amelia Earhart's Last Flight | Vanished Ep. 3"


def test_a_long_title_is_trimmed_but_keeps_the_episode_number(series):
    ep = Episode(series=series, number=12, topic="Topic C")
    title = ep.title("A" * 140)
    assert len(title) <= YOUTUBE_TITLE_LIMIT
    assert title.endswith(" | Vanished Ep. 12")


def test_the_description_block_links_the_playlist_and_previous_episode(series):
    ep = Episode(series=series, number=2, topic="Topic B", playlist_id="PL9", previous_video_id="vid1")
    block = ep.description_block()
    assert "Episode 2 of Vanished Without a Trace" in block
    assert "https://www.youtube.com/playlist?list=PL9" in block
    assert "https://youtu.be/vid1" in block


def test_the_description_block_omits_links_it_does_not_have(series):
    block = Episode(series=series, number=1, topic="Topic A").description_block()
    assert "playlist?list=" not in block
    assert "youtu.be" not in block


# ─── Playlist sync ───────────────────────────────────────


def test_a_missing_playlist_is_created_public_with_the_series_title(series):
    yt = FakeYouTube()
    state = ensure_playlist(yt, series, load_state(Path("/x")))
    assert state["playlist_id"] == "PL1"
    assert yt.created[0]["snippet"]["title"] == "Vanished Without a Trace"
    assert yt.created[0]["status"]["privacyStatus"] == "public"


def test_an_existing_playlist_is_reused(series):
    yt = FakeYouTube(existing_playlists={"PLkeep"})
    state = ensure_playlist(yt, series, {**load_state(Path("/x")), "playlist_id": "PLkeep"})
    assert state["playlist_id"] == "PLkeep"
    assert yt.created == []


def test_a_playlist_deleted_on_youtube_is_recreated(series):
    yt = FakeYouTube()
    state = ensure_playlist(yt, series, {**load_state(Path("/x")), "playlist_id": "PLgone"})
    assert state["playlist_id"] == "PL1"


def test_a_failed_playlist_add_reports_false_instead_of_raising():
    assert add_to_playlist(FakeYouTube(fail_item_insert=True), "PL1", "vid1") is False


def test_sync_retries_episodes_that_never_made_it_into_the_playlist(series):
    state = load_state(Path("/x"))
    state = record_published(state, Episode(series=series, number=1, topic="Topic A"),
                             "vid1", in_playlist=False)
    yt = FakeYouTube()

    state = sync_playlist(yt, series, state)

    assert yt.items == [("PL1", "vid1")]
    assert state["published"][0]["in_playlist"] is True


# ─── The runner ──────────────────────────────────────────


@pytest.fixture
def runner(tmp_path, series, monkeypatch):
    """Isolate the runner from the real disk, lock file and YouTube."""
    monkeypatch.setattr(series_mod, "free_disk_gb", lambda path: 100.0)
    monkeypatch.setattr(series_mod, "RENDER_LOCK_FILE", tmp_path / ".render.lock")
    yt = FakeYouTube()
    return {"series": series, "state_path": tmp_path / "state.json", "yt": yt,
            "factory": lambda: yt}


def test_a_published_episode_is_branded_added_to_the_playlist_and_recorded(runner):
    seen: list[Episode] = []

    def produce(ep):
        seen.append(ep)
        return {"video_id": "vid1"}

    result = produce_next_episode(runner["series"], runner["state_path"], produce,
                                  runner["factory"], upload=True)

    assert result["video_id"] == "vid1"
    assert seen[0].playlist_id == "PL1"  # playlist exists before the upload links to it
    assert runner["yt"].items == [("PL1", "vid1")]
    state = load_state(runner["state_path"])
    assert state["published"][0] == {**state["published"][0], "number": 1, "topic": "Topic A",
                                     "video_id": "vid1", "in_playlist": True}


def test_a_crashing_render_is_recorded_as_a_failure_not_raised(runner):
    def produce(ep):
        raise RuntimeError("moviepy ran out of memory")

    result = produce_next_episode(runner["series"], runner["state_path"], produce,
                                  runner["factory"], upload=True)

    assert result["status"] == "failed"
    state = load_state(runner["state_path"])
    assert state["published"] == []
    assert state["failures"]["Topic A"]["count"] == 1


def test_a_run_that_uploaded_nothing_counts_as_a_failure(runner):
    produce_next_episode(runner["series"], runner["state_path"], lambda ep: {},
                         runner["factory"], upload=True)
    assert load_state(runner["state_path"])["failures"]["Topic A"]["count"] == 1


def test_a_render_only_run_records_nothing_and_never_touches_youtube(runner):
    def factory():
        raise AssertionError("render-only must not authenticate")

    produce_next_episode(runner["series"], runner["state_path"], lambda ep: {"video_path": "x"},
                         factory, upload=False)

    assert not runner["state_path"].exists()


def test_a_finished_series_returns_none_without_producing(runner):
    state = load_state(runner["state_path"])
    for i, topic in enumerate(runner["series"].episodes):
        state = record_published(state, Episode(series=runner["series"], number=i + 1, topic=topic),
                                 f"v{i}", in_playlist=True)
    series_mod.save_state(state, runner["state_path"])

    def produce(ep):
        raise AssertionError("nothing left to produce")

    assert produce_next_episode(runner["series"], runner["state_path"], produce,
                                runner["factory"], upload=True) is None


def test_low_disk_skips_the_render_without_burning_an_attempt(runner, monkeypatch):
    monkeypatch.setattr(series_mod, "free_disk_gb", lambda path: 0.5)

    def produce(ep):
        raise AssertionError("must not render on a full disk")

    result = produce_next_episode(runner["series"], runner["state_path"], produce,
                                  runner["factory"], upload=True)

    assert result["status"] == "skipped"
    assert load_state(runner["state_path"])["failures"] == {}


def test_a_second_publisher_of_the_same_series_is_turned_away(runner):
    """A manual --upload run next to the daemon must not publish the same episode."""
    def produce(ep):
        raise AssertionError("must not produce while the daemon holds the series")

    with render_lock(series_mod.series_lock_file(runner["state_path"])):
        result = produce_next_episode(runner["series"], runner["state_path"], produce,
                                      runner["factory"], upload=True)

    assert result["status"] == "skipped"


def test_an_upload_lost_to_a_crash_is_recovered_instead_of_republished(runner):
    """Killed after videos.insert but before the state save: find it, don't re-upload."""
    series_mod.save_state({**load_state(runner["state_path"]),
                           "in_flight": {"number": 1, "topic": "Topic A"}}, runner["state_path"])
    runner["yt"].uploads = [("Amelia Earhart's Last Flight | Vanished Ep. 1", "vidLost")]
    seen: list[Episode] = []

    def produce(ep):
        seen.append(ep)
        return {"video_id": "vid2"}

    produce_next_episode(runner["series"], runner["state_path"], produce,
                         runner["factory"], upload=True)

    assert [(e.number, e.topic, e.previous_video_id) for e in seen] == [(2, "Topic B", "vidLost")]
    state = load_state(runner["state_path"])
    assert [p["video_id"] for p in state["published"]] == ["vidLost", "vid2"]
    assert ("PL1", "vidLost") in runner["yt"].items
    assert "in_flight" not in state


def test_an_in_flight_episode_that_never_reached_youtube_is_retried(runner):
    series_mod.save_state({**load_state(runner["state_path"]),
                           "in_flight": {"number": 1, "topic": "Topic A"}}, runner["state_path"])
    runner["yt"].uploads = [("Something else | Vanished Ep. 12", "other")]
    seen: list[Episode] = []

    produce_next_episode(runner["series"], runner["state_path"],
                         lambda ep: seen.append(ep) or {"video_id": "vid1"},
                         runner["factory"], upload=True)

    assert [(e.number, e.topic) for e in seen] == [(1, "Topic A")]


def test_the_in_flight_marker_is_cleared_after_a_failure(runner):
    def produce(ep):
        raise RuntimeError("boom")

    produce_next_episode(runner["series"], runner["state_path"], produce,
                         runner["factory"], upload=True)
    assert "in_flight" not in load_state(runner["state_path"])


def test_a_render_that_failed_to_upload_does_not_burn_a_render_attempt(runner, tmp_path):
    """New channels hit YouTube's daily upload cap; that must not skip good episodes."""
    video = tmp_path / "ep.mp4"
    video.write_bytes(b"video")

    result = produce_next_episode(runner["series"], runner["state_path"],
                                  lambda ep: {"video_path": str(video)},
                                  runner["factory"], upload=True)

    assert result["status"] == "upload_failed"
    failure = load_state(runner["state_path"])["failures"]["Topic A"]
    assert (failure["count"], failure["upload_count"]) == (0, 1)


def test_an_episode_that_never_uploads_is_eventually_skipped(series):
    state = load_state(Path("/x"))
    for _ in range(MAX_UPLOAD_ATTEMPTS):
        state = record_failure(state, "Topic A", "uploadLimitExceeded", kind="upload")
    assert next_episode(series, state).topic == "Topic B"


def test_the_result_reports_whether_the_video_reached_the_playlist(runner):
    runner["yt"].fail_item_insert = True
    result = produce_next_episode(runner["series"], runner["state_path"],
                                  lambda ep: {"video_id": "vid1"}, runner["factory"], upload=True)
    assert result["in_playlist"] is False


@pytest.mark.parametrize("status, delay", [
    ("success", 0),
    ("rendered", 0),
    ("skipped", SERIES_RETRY_SLEEP_SECONDS),
    ("failed", SERIES_RETRY_SLEEP_SECONDS),
    ("upload_failed", UPLOAD_RETRY_SLEEP_SECONDS),
])
def test_daemons_back_off_by_outcome(status, delay):
    assert retry_delay_seconds({"status": status}) == delay
