#!/bin/zsh
# Safety-net cleanup. The pipeline already deletes artifacts after each
# successful upload, so anything left here is leftover from a failed/crashed
# run. Sweep files older than 12h (well past any in-progress render) to stop
# disk creep. Script JSON + logs live in output/ root and are never touched.
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

for dir in \
  "$REPO_DIR/output/videos" \
  "$REPO_DIR/output/audio" \
  "$REPO_DIR/output/subtitles" \
  "$REPO_DIR/output/thumbnails" \
  "$REPO_DIR/assets/stock_footage"; do
  [ -d "$dir" ] && find "$dir" -type f ! -name ".gitkeep" -mmin +720 -delete 2>/dev/null
done
