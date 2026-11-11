#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
export PATH="/usr/local/bin:/usr/bin:/bin"
case "${1:-en}" in
    en) exec "$REPO_DIR/.venv/bin/python" autopilot.py --daemon --series ;;
    nl) export YOUTUBE_TOKEN_FILE=token_nl.json
        exec "$REPO_DIR/.venv/bin/python" brainrot.py daemon --series ;;
    *) echo 'usage: linux/run.sh {en|nl}' >&2; exit 2 ;;
esac
