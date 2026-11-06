"""Cross-process render lock.

The English and Dutch daemons run as separate launchd jobs on one 8 GB Mac.
A single moviepy render of a 10-minute 1080p video already uses most of that
RAM, so two at once swap hard or get killed mid-write — which leaves a corrupt
mp4 and wastes the whole production. This lock makes the second daemon wait.

Uses flock(), which the kernel releases automatically if the holder dies, so a
crashed render can never leave the lock stuck.
"""

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class RenderBusyError(RuntimeError):
    """Raised by a non-blocking acquire when another render holds the lock."""


@contextmanager
def render_lock(path: Path, blocking: bool = True) -> Iterator[None]:
    """Hold an exclusive render lock for the duration of the block."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if not blocking:
                raise RenderBusyError(f"another render holds {path}") from None
            print("  Another channel is rendering; waiting for it to finish...")
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
