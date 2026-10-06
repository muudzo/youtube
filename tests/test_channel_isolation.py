"""Tests that the Dutch channel cannot publish onto the English channel.

One OAuth token authorises exactly one YouTube channel. The repo originally
hardcoded a single token.json, so a second channel's daemon would have uploaded
onto the first channel — silently, and irreversibly from the viewer's side.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NL_TOKEN_FILE

REPO = Path(__file__).parent.parent


def _token_file_with_env(value: str | None) -> str:
    """Import the uploader in a clean process and report its TOKEN_FILE."""
    env = dict(os.environ)
    env.pop("YOUTUBE_TOKEN_FILE", None)
    if value is not None:
        env["YOUTUBE_TOKEN_FILE"] = value

    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.');"
         "from scripts.youtube_uploader import TOKEN_FILE; print(TOKEN_FILE.name)"],
        capture_output=True, text=True, env=env, cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_default_token_is_the_english_channel():
    """Existing behaviour must be unchanged when the variable is unset."""
    assert _token_file_with_env(None) == "token.json"


def test_environment_variable_selects_a_different_channel_token():
    assert _token_file_with_env("token_nl.json") == "token_nl.json"


def test_brainrot_entrypoint_targets_the_dutch_token():
    """brainrot.py must set the variable before the uploader is ever imported."""
    env = dict(os.environ)
    env.pop("YOUTUBE_TOKEN_FILE", None)

    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.');"
         "import brainrot;"
         "from scripts.youtube_uploader import TOKEN_FILE; print(TOKEN_FILE.name)"],
        capture_output=True, text=True, env=env, cwd=REPO,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == NL_TOKEN_FILE


def test_both_channel_tokens_are_gitignored():
    """A committed OAuth token is a credential leak."""
    ignored = (REPO / ".gitignore").read_text().split()

    assert "token.json" in ignored
    assert NL_TOKEN_FILE in ignored


def test_dutch_token_is_actually_ignored_by_git():
    """Assert against git itself, not just the file's text."""
    result = subprocess.run(
        ["git", "check-ignore", NL_TOKEN_FILE],
        capture_output=True, text=True, cwd=REPO,
    )

    assert result.returncode == 0, f"{NL_TOKEN_FILE} is NOT gitignored"


def test_dutch_daemon_script_exports_the_dutch_token():
    script = (REPO / "cron" / "run_brainrot.sh").read_text()

    assert f'YOUTUBE_TOKEN_FILE="{NL_TOKEN_FILE}"' in script


def test_english_autopilot_was_not_repointed():
    """The English daemon must keep using the English channel."""
    script = (REPO / "cron" / "run_autopilot.sh").read_text()

    assert "YOUTUBE_TOKEN_FILE" not in script
