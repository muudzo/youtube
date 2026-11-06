"""The render lock keeps two channels from rendering at once on an 8 GB Mac.

flock() locks belong to an open file description, so a second open() of the
same path conflicts even inside one process — which lets this be tested
without spawning a second daemon.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.render_lock import RenderBusyError, render_lock


def test_a_second_render_cannot_start_while_one_holds_the_lock(tmp_path):
    lock = tmp_path / ".render.lock"
    with render_lock(lock):
        with pytest.raises(RenderBusyError):
            with render_lock(lock, blocking=False):
                pass


def test_the_lock_is_released_when_the_render_finishes(tmp_path):
    lock = tmp_path / ".render.lock"
    with render_lock(lock):
        pass
    with render_lock(lock, blocking=False):
        pass


def test_the_lock_is_released_when_the_render_crashes(tmp_path):
    lock = tmp_path / ".render.lock"
    with pytest.raises(RuntimeError):
        with render_lock(lock):
            raise RuntimeError("render died")
    with render_lock(lock, blocking=False):
        pass
