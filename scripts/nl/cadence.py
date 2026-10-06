"""
Upload cadence governor.

The English autopilot produces until the YouTube API quota is exhausted —
roughly three video+Short pairs a day, back to back, at whatever hour the
daemon happens to be running. That is the single most visible signal in
YouTube's inauthentic-content fingerprint: an upload pace and regularity no
human editorial process produces.

This governor caps the Dutch channel to a human rate and, just as importantly,
makes the spacing irregular. A machine uploading every 5.00 hours is as
obvious as one uploading twelve times a day.

State is persisted so the cap survives restarts — without that, launchd
bouncing the daemon would reset the day's count and defeat the whole thing.
"""

import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import (
    NL_MAX_UPLOADS_PER_DAY,
    NL_MIN_HOURS_BETWEEN_UPLOADS,
    NL_STATE_FILE,
    NL_UPLOAD_JITTER_MINUTES,
)

# Dutch viewing peaks: late afternoon through mid-evening, local time.
# Uploading at 04:00 CET reaches nobody and looks automated.
_PREFERRED_HOURS_CET = (16, 17, 18, 19, 20, 21)
_CET_OFFSET_HOURS = 1  # CET; an hour's drift under DST is immaterial here


@dataclass(frozen=True)
class Decision:
    """Whether to produce now, and why not if not."""

    allowed: bool
    reason: str
    wait_seconds: int = 0


def load_state(path: Path = None) -> dict:
    """Read cadence state, tolerating a missing or corrupt file."""
    path = Path(path or NL_STATE_FILE)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # A corrupt state file must not wedge the channel permanently; the
        # worst case of resetting is one extra upload in a day.
        print("  Waarschuwing: cadence-state onleesbaar, opnieuw beginnen.")
        return {}


def save_state(state: dict, path: Path = None) -> None:
    """Persist cadence state."""
    path = Path(path or NL_STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _today(now: datetime) -> str:
    return now.astimezone(timezone.utc).date().isoformat()


def _uploads_today(state: dict, now: datetime) -> int:
    """Count of uploads in the current UTC day, resetting on rollover."""
    if state.get("day") != _today(now):
        return 0
    return int(state.get("uploads", 0))


def check(state: dict, now: datetime = None) -> Decision:
    """Decide whether an upload is allowed right now."""
    now = now or datetime.now(timezone.utc)
    done = _uploads_today(state, now)

    if done >= NL_MAX_UPLOADS_PER_DAY:
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return Decision(
            False,
            f"dagelijkse limiet bereikt ({done}/{NL_MAX_UPLOADS_PER_DAY})",
            int((midnight - now).total_seconds()),
        )

    last = state.get("last_upload_utc")
    if last:
        try:
            previous = datetime.fromisoformat(last)
        except ValueError:
            previous = None
        if previous:
            elapsed = (now - previous).total_seconds()
            required = NL_MIN_HOURS_BETWEEN_UPLOADS * 3600
            if elapsed < required:
                return Decision(
                    False,
                    f"te kort na vorige upload ({elapsed / 3600:.1f}u van "
                    f"{NL_MIN_HOURS_BETWEEN_UPLOADS}u)",
                    int(required - elapsed),
                )

    return Decision(True, f"toegestaan ({done}/{NL_MAX_UPLOADS_PER_DAY} vandaag)")


def record_upload(state: dict, now: datetime = None) -> dict:
    """Return a new state reflecting one completed upload.

    Does not mutate the input — the caller decides when to persist.
    """
    now = now or datetime.now(timezone.utc)
    return {
        **state,
        "day": _today(now),
        "uploads": _uploads_today(state, now) + 1,
        "last_upload_utc": now.isoformat(),
    }


def jitter_seconds(rng: random.Random = None) -> int:
    """Random delay so spacing between uploads is never mechanical."""
    rng = rng or random.Random()
    return rng.randint(0, max(0, NL_UPLOAD_JITTER_MINUTES) * 60)


def seconds_until_good_hour(now: datetime = None,
                            rng: random.Random = None) -> int:
    """Seconds to wait for the next Dutch viewing peak.

    Returns 0 when already inside the window, so a run mid-peak proceeds
    immediately instead of waiting for the next day.
    """
    now = now or datetime.now(timezone.utc)
    rng = rng or random.Random()
    local_hour = (now.hour + _CET_OFFSET_HOURS) % 24

    if local_hour in _PREFERRED_HOURS_CET:
        return 0

    ahead = [(h - local_hour) % 24 for h in _PREFERRED_HOURS_CET]
    hours_away = min(a for a in ahead if a > 0)
    # Land somewhere inside the hour rather than exactly on it.
    return hours_away * 3600 + rng.randint(0, 3599)


def describe(state: dict, now: datetime = None) -> str:
    """One-line cadence status for logs."""
    now = now or datetime.now(timezone.utc)
    decision = check(state, now)
    done = _uploads_today(state, now)
    suffix = "" if decision.allowed else f" — wacht {decision.wait_seconds / 3600:.1f}u"
    return (f"Cadans: {done}/{NL_MAX_UPLOADS_PER_DAY} vandaag, "
            f"{decision.reason}{suffix}")
