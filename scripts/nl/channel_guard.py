"""Verify which YouTube channel a token actually controls.

Channel isolation is the premise of this whole surface: policy strikes land on
the channel, and the existing channel's audience is entirely 55+. That
isolation rests on a single browser dialog during OAuth — and picking the wrong
account there is silent, indistinguishable from picking the right one, and only
discoverable after a Dutch video appears on the wrong channel.

So the token is asked what it controls, rather than assumed.
"""

import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.youtube_uploader import SCOPES


class WrongChannelError(RuntimeError):
    """Raised when the Dutch token controls the English channel."""


def _service_for(token_path: Path):
    """Build a YouTube client from one token file. Seam for tests."""
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def channel_identity(token_path: Path) -> dict | None:
    """Return ``{"id", "title"}`` for the channel this token controls.

    None when the token is absent or the account has no channel. Costs 1 quota
    unit.
    """
    token_path = Path(token_path)
    if not token_path.exists():
        return None

    items = _service_for(token_path).channels().list(
        part="snippet", mine=True
    ).execute().get("items", [])
    if not items:
        return None

    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def assert_distinct_channels(nl_token: Path, en_token: Path) -> dict | None:
    """Confirm the Dutch token is not pointed at the English channel.

    A missing or unreadable English token is not a failure — plenty of machines
    only ever run one channel, and a revoked English token must not be able to
    block Dutch production. Only a confirmed collision raises.
    """
    nl = channel_identity(nl_token)
    if nl is None:
        return None

    try:
        en = channel_identity(Path(en_token))
    except (OSError, ValueError, KeyError):
        return nl

    if en and en["id"] == nl["id"]:
        raise WrongChannelError(
            f"token_nl.json bestuurt hetzelfde kanaal als token.json: "
            f"{en['title']} ({en['id']}). De Nederlandse video's zouden op het "
            f"bestaande kanaal landen. Verwijder token_nl.json en log opnieuw "
            f"in met het NIEUWE kanaal."
        )
    return nl
