"""The NL token must not control the English channel.

Channel isolation is the whole reason this surface exists: policy strikes land
on the channel, and the existing channel's audience is entirely 55+. That
isolation rests on one browser dialog during OAuth, where picking the wrong
account is silent and indistinguishable from picking the right one. This guard
is what makes the mistake loud instead.
"""

import json

import pytest

from scripts.nl import channel_guard
from scripts.nl.channel_guard import WrongChannelError


class _FakeChannels:
    def __init__(self, payload):
        self._payload = payload

    def list(self, **_kwargs):
        return self

    def execute(self):
        return self._payload


class _FakeService:
    def __init__(self, payload):
        self._payload = payload

    def channels(self):
        return _FakeChannels(self._payload)


def _payload(channel_id, title):
    return {"items": [{"id": channel_id, "snippet": {"title": title}}]}


def _token(tmp_path, name):
    path = tmp_path / name
    path.write_text(json.dumps({"token": "x", "refresh_token": "y"}))
    return path


def test_identity_returns_channel_id_and_title(tmp_path, monkeypatch):
    # Arrange
    token = _token(tmp_path, "token_nl.json")
    monkeypatch.setattr(
        channel_guard, "_service_for",
        lambda _p: _FakeService(_payload("UC_NL", "Nederlandse Uitleg")),
    )

    # Act
    identity = channel_guard.channel_identity(token)

    # Assert
    assert identity == {"id": "UC_NL", "title": "Nederlandse Uitleg"}


def test_identity_is_none_when_the_token_does_not_exist(tmp_path):
    # Arrange / Act
    identity = channel_guard.channel_identity(tmp_path / "absent.json")

    # Assert
    assert identity is None


def test_identity_is_none_when_the_account_has_no_channel(tmp_path, monkeypatch):
    # Arrange
    token = _token(tmp_path, "token_nl.json")
    monkeypatch.setattr(channel_guard, "_service_for", lambda _p: _FakeService({"items": []}))

    # Act
    identity = channel_guard.channel_identity(token)

    # Assert
    assert identity is None


def test_raises_when_both_tokens_resolve_to_the_same_channel(tmp_path, monkeypatch):
    # Arrange
    nl, en = _token(tmp_path, "token_nl.json"), _token(tmp_path, "token.json")
    monkeypatch.setattr(
        channel_guard, "_service_for",
        lambda _p: _FakeService(_payload("UC_SAME", "4kMUDZO")),
    )

    # Act / Assert
    with pytest.raises(WrongChannelError, match="4kMUDZO"):
        channel_guard.assert_distinct_channels(nl, en)


def test_passes_when_the_channels_differ(tmp_path, monkeypatch):
    # Arrange
    nl, en = _token(tmp_path, "token_nl.json"), _token(tmp_path, "token.json")
    ids = {nl.name: _payload("UC_NL", "NL"), en.name: _payload("UC_EN", "4kMUDZO")}
    monkeypatch.setattr(
        channel_guard, "_service_for", lambda p: _FakeService(ids[p.name])
    )

    # Act
    result = channel_guard.assert_distinct_channels(nl, en)

    # Assert
    assert result["id"] == "UC_NL"


def test_passes_when_there_is_no_english_token_to_compare_against(tmp_path, monkeypatch):
    # Arrange — a machine that only ever ran the Dutch channel
    nl = _token(tmp_path, "token_nl.json")
    monkeypatch.setattr(
        channel_guard, "_service_for", lambda _p: _FakeService(_payload("UC_NL", "NL"))
    )

    # Act
    result = channel_guard.assert_distinct_channels(nl, tmp_path / "absent.json")

    # Assert
    assert result["id"] == "UC_NL"


def test_unreadable_english_token_does_not_block_production(tmp_path, monkeypatch):
    # Arrange — a stale or revoked English token must not stop the NL channel
    nl, en = _token(tmp_path, "token_nl.json"), _token(tmp_path, "token.json")

    def flaky(path):
        if path.name == "token.json":
            raise OSError("revoked")
        return _FakeService(_payload("UC_NL", "NL"))

    monkeypatch.setattr(channel_guard, "_service_for", flaky)

    # Act
    result = channel_guard.assert_distinct_channels(nl, en)

    # Assert
    assert result["id"] == "UC_NL"
