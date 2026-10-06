#!/bin/zsh
# Manual batch upload — produce N videos in one go (not the scheduled daemon).
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
[ -f "$REPO_DIR/.env" ] && { set -a; source "$REPO_DIR/.env"; set +a; }
PY="$REPO_DIR/.venv/bin/python"
"$PY" autopilot.py --videos 2 >> /tmp/youtube_upload.log 2>&1
