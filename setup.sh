#!/bin/zsh
# One-time setup for the YouTube autopilot on this machine.
# Idempotent — safe to re-run. Installs ffmpeg, a Python venv with deps,
# required directories, and the launchd agents (not started — see manage.sh).

set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "==> [1/5] ffmpeg"
if command -v ffmpeg >/dev/null 2>&1 || [ -x /opt/homebrew/bin/ffmpeg ]; then
    echo "    ffmpeg already installed"
elif command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
else
    echo "    ERROR: Homebrew not found. Install from https://brew.sh then re-run." >&2
    exit 1
fi

echo "==> [2/5] Python venv + dependencies"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "    deps installed into .venv"

echo "==> [3/5] Output directories"
mkdir -p output/logs output/videos output/audio output/subtitles \
         output/thumbnails assets/stock_footage assets/music assets/fonts

echo "==> [4/5] launchd agents"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA"
for name in autopilot brainrot cleanup; do
    plist="com.youtube.$name.plist"
    sed "s|__REPO_DIR__|$REPO_DIR|g" "launchd/$plist" > "$LA/$plist"
    echo "    installed $LA/$plist"
done

echo "==> [5/5] Pre-flight check"
[ -f .env ] || echo "    WARNING: no .env — run: cp .env.example .env  then add your keys"
[ -f client_secret.json ] || echo "    WARNING: no client_secret.json — see DEPLOY.md (needed for upload)"

cat <<EOF

Setup complete. Remaining manual steps (see DEPLOY.md):
  1. cp .env.example .env   and fill GROQ_API_KEY + PEXELS_API_KEY
  2. Add client_secret.json (Google OAuth desktop credentials)
  3. One-time Google login (opens a browser). Use the per-channel command --
     the bare uploader call writes token.json and would clobber the English
     channel's token:
       .venv/bin/python brainrot.py auth      # Dutch channel  -> token_nl.json
       .venv/bin/python autopilot.py --auth   # English channel -> token.json
  4. Start the autopilot:
       ./manage.sh start
EOF
