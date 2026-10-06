"""Tests for delete-after-upload artifact cleanup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import STOCK_DIR
from scripts.cleanup import purge_artifacts


def test_purges_listed_files(tmp_path):
    # Arrange
    video = tmp_path / "render.mp4"
    audio = tmp_path / "narration.mp3"
    video.write_bytes(b"x" * 1024)
    audio.write_bytes(b"y" * 512)

    # Act
    freed = purge_artifacts([video, audio])

    # Assert
    assert not video.exists()
    assert not audio.exists()
    assert freed == 1024 + 512


def test_ignores_none_and_missing(tmp_path):
    missing = tmp_path / "nope.mp4"

    freed = purge_artifacts([None, missing, ""])

    assert freed == 0


def test_keeps_files_not_in_list(tmp_path):
    # The small script JSON must survive — caller never lists it.
    keep = tmp_path / "topic_script.json"
    keep.write_text("{}")
    doomed = tmp_path / "render.mp4"
    doomed.write_bytes(b"z" * 10)

    purge_artifacts([doomed])

    assert keep.exists()
    assert not doomed.exists()


def test_footage_guard_only_deletes_under_stock_dir(tmp_path):
    # A clip inside STOCK_DIR is deleted; one outside is left untouched.
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    inside = STOCK_DIR / "test_section_99_clip.mp4"
    inside.write_bytes(b"a" * 100)
    outside = tmp_path / "not_footage.mp4"
    outside.write_bytes(b"b" * 100)

    purge_artifacts([], footage_files=[inside, outside])

    assert not inside.exists(), "footage inside STOCK_DIR should be deleted"
    assert outside.exists(), "files outside STOCK_DIR must never be deleted"
