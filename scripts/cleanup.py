"""
Local artifact cleanup — delete heavy files after a confirmed upload.

The autopilot is "upload then forget": once a video is safely on YouTube we
have no reason to keep the multi-hundred-MB render, its audio, subtitles,
thumbnails, or the downloaded stock footage on disk. This module deletes
those best-effort and reports how much space was freed.

Safety rules:
- Only ever called after a CONFIRMED upload (caller passes the upload result).
- Failed uploads keep their files so the next run can retry.
- The small script JSON and logs are never touched.
- Deletion never raises — a cleanup failure must not fail the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import STOCK_DIR


def _human(num_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _delete(path) -> int:
    """Delete a single file if it exists. Returns bytes freed (0 on miss/error)."""
    if not path:
        return 0
    p = Path(path)
    try:
        if p.is_file():
            freed = p.stat().st_size
            p.unlink()
            return freed
    except OSError as e:
        print(f"  Cleanup warning: could not delete {p.name}: {e}")
    return 0


def purge_artifacts(paths, footage_files=None) -> int:
    """
    Delete the listed artifact files plus any downloaded stock footage.

    Args:
        paths: iterable of file paths (str or Path) to delete. None entries
               and missing files are ignored.
        footage_files: iterable of stock-footage paths used by this render.
                       Passed explicitly so we only delete clips we actually
                       downloaded, never the whole STOCK_DIR blindly.

    Returns:
        Total bytes freed.
    """
    freed = 0
    deleted = 0

    for path in paths or []:
        b = _delete(path)
        if b:
            freed += b
            deleted += 1

    for clip in footage_files or []:
        # Defensive: only delete things that live under the stock-footage dir.
        try:
            clip_path = Path(clip).resolve()
            if STOCK_DIR.resolve() in clip_path.parents:
                b = _delete(clip_path)
                if b:
                    freed += b
                    deleted += 1
        except OSError:
            continue

    if deleted:
        print(f"  Cleanup: removed {deleted} local file(s), freed {_human(freed)}")
    return freed
