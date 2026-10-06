"""Tests for the upload cadence governor.

The cap only means anything if it survives a restart and a day rollover —
launchd bouncing the daemon must not reset the day's count.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NL_MAX_UPLOADS_PER_DAY, NL_MIN_HOURS_BETWEEN_UPLOADS
from scripts.nl import cadence

NOON = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_fresh_state_allows_production():
    assert cadence.check({}, NOON).allowed


def test_blocks_a_second_upload_inside_the_minimum_gap():
    state = cadence.record_upload({}, NOON)

    decision = cadence.check(state, NOON + timedelta(hours=1))

    assert not decision.allowed
    assert decision.wait_seconds > 0


def test_allows_again_once_the_gap_has_passed():
    state = cadence.record_upload({}, NOON)
    later = NOON + timedelta(hours=NL_MIN_HOURS_BETWEEN_UPLOADS + 0.1)

    assert cadence.check(state, later).allowed


def test_enforces_the_daily_cap():
    state = {}
    now = NOON
    for _ in range(NL_MAX_UPLOADS_PER_DAY):
        state = cadence.record_upload(state, now)
        now += timedelta(hours=NL_MIN_HOURS_BETWEEN_UPLOADS + 0.1)

    decision = cadence.check(state, now)

    assert not decision.allowed
    assert "limiet" in decision.reason


def test_cap_resets_on_the_next_day():
    state = {}
    now = NOON
    for _ in range(NL_MAX_UPLOADS_PER_DAY):
        state = cadence.record_upload(state, now)
        now += timedelta(hours=NL_MIN_HOURS_BETWEEN_UPLOADS + 0.1)

    assert cadence.check(state, NOON + timedelta(days=1)).allowed


def test_record_upload_does_not_mutate_the_input():
    original = {"uploads": 1, "day": "2026-09-14"}
    snapshot = dict(original)

    cadence.record_upload(original, NOON)

    assert original == snapshot


def test_cap_survives_a_restart_via_persisted_state(tmp_path):
    """A daemon restart must not hand the channel a fresh daily budget."""
    path = tmp_path / "state.json"
    state = {}
    now = NOON
    for _ in range(NL_MAX_UPLOADS_PER_DAY):
        state = cadence.record_upload(state, now)
        now += timedelta(hours=NL_MIN_HOURS_BETWEEN_UPLOADS + 0.1)
    cadence.save_state(state, path)

    reloaded = cadence.load_state(path)

    assert not cadence.check(reloaded, now).allowed


def test_corrupt_state_file_does_not_wedge_the_channel(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{ this is not json")

    state = cadence.load_state(path)

    assert state == {}
    assert cadence.check(state, NOON).allowed


def test_unparsable_timestamp_is_ignored_rather_than_crashing():
    state = {"day": NOON.date().isoformat(), "uploads": 1,
             "last_upload_utc": "gisteren"}

    assert cadence.check(state, NOON).allowed


def test_good_hour_is_zero_during_the_dutch_evening_peak():
    """18:00 UTC is 19:00 CET — inside the window, so no wait."""
    evening = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)

    assert cadence.seconds_until_good_hour(evening) == 0


def test_good_hour_waits_when_outside_the_peak():
    dead_of_night = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)

    assert cadence.seconds_until_good_hour(dead_of_night) > 0
