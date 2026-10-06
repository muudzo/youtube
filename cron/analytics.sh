#!/bin/zsh
# Channel analytics snapshot.
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
[ -f "$REPO_DIR/.env" ] && { set -a; source "$REPO_DIR/.env"; set +a; }
PY="$REPO_DIR/.venv/bin/python"
"$PY" scripts/engagement_booster.py analytics
