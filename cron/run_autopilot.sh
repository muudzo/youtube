#!/bin/zsh
# Entry point for the autopilot daemon (run by launchd).
# Portable: resolves the repo root from this script's own location, so it
# works regardless of username or where the repo is cloned.

set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# ffmpeg lives in Homebrew; keep a minimal, explicit PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Load secrets (GROQ_API_KEY, PEXELS_API_KEY, GEMINI_API_KEY, ...)
if [ -f "$REPO_DIR/.env" ]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
fi

PY="$REPO_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: venv python not found at $PY — run ./setup.sh first" >&2
  exit 1
fi

# Produce as many videos as the daily YouTube quota allows, deleting local
# files after each confirmed upload.
exec "$PY" autopilot.py --daemon
