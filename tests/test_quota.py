"""Tests for the autopilot daily upload-quota guard."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import autopilot
from config import DAILY_UPLOAD_UNIT_BUDGET


def test_fresh_state_has_full_budget():
    state = {}
    remaining = autopilot.quota_remaining(state)
    assert remaining == DAILY_UPLOAD_UNIT_BUDGET
    assert state["quota_units_used"] == 0
    assert state["quota_window"] == autopilot._quota_window()


def test_charge_quota_counts_video_and_short():
    state = {}
    spent = autopilot.charge_quota(state, {"video_id": "a", "short_id": "b"})
    assert spent == autopilot.COST_PER_UPLOAD * 2
    assert autopilot.quota_remaining(state) == DAILY_UPLOAD_UNIT_BUDGET - spent


def test_charge_quota_only_counts_successful_uploads():
    state = {}
    # Short failed (no short_id) → only the long-form is charged.
    spent = autopilot.charge_quota(state, {"video_id": "a"})
    assert spent == autopilot.COST_PER_UPLOAD


def test_window_rollover_resets_counter():
    state = {"quota_window": "1999-01-01", "quota_units_used": 9999}
    remaining = autopilot.quota_remaining(state)
    assert remaining == DAILY_UPLOAD_UNIT_BUDGET
    assert state["quota_units_used"] == 0


def test_seconds_until_reset_is_within_a_day():
    secs = autopilot._seconds_until_quota_reset()
    assert 0 < secs <= 86400
