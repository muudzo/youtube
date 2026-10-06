#!/bin/zsh
# Entry point for the Dutch channel daemon (run by launchd).
# Portable: resolves the repo root from this script's own location.

set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# ffmpeg lives in Homebrew; keep a minimal, explicit PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Load secrets (GROQ_API_KEY, PEXELS_API_KEY, ...)
if [ -f "$REPO_DIR/.env" ]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
fi

# The Dutch channel has its own OAuth token; without this the daemon would
# upload onto the English channel. brainrot.py also defaults it, but setting it
# here means a stray manual invocation of this script cannot get it wrong.
export YOUTUBE_TOKEN_FILE="token_nl.json"

PY="$REPO_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: venv python not found at $PY — run ./setup.sh first" >&2
  exit 1
fi

# Unlike autopilot.py, this does NOT run until the API quota is exhausted.
# scripts/nl/cadence.py caps it to NL_MAX_UPLOADS_PER_DAY with jitter.
exec "$PY" brainrot.py daemon
