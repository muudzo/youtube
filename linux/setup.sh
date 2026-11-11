#!/usr/bin/env bash
# Run as the service user from a checkout in /srv or /opt (not /home).
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run as the intended non-root service user with sudo access.' >&2
    exit 1
fi
case "$REPO_DIR" in
    /home/*|/root/*) echo 'Install the runtime under /srv or /opt; systemd ProtectHome hides home directories.' >&2; exit 1 ;;
esac
sudo apt-get update -qq
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-venv ffmpeg fonts-dejavu-core fonts-liberation2
test -d .venv || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt -r requirements-dev.txt
mkdir -p output/logs output/videos output/audio output/subtitles output/thumbnails \
    assets/stock_footage assets/music assets/fonts
.venv/bin/python -m pip freeze > output/linux-requirements.lock
if [ ! -e .env ]; then
    install -m 600 linux/vm.env.example .env
fi
SERVICE_USER="$(id -un)" SERVICE_GROUP="$(id -gn)" REPO_DIR="$REPO_DIR" .venv/bin/python - <<'PY'
import os
from pathlib import Path
src = Path('linux/youtube-autopilot@.service').read_text()
for key, value in [('__USER__', os.environ['SERVICE_USER']), ('__GROUP__', os.environ['SERVICE_GROUP']), ('__REPO_DIR__', os.environ['REPO_DIR'])]:
    src = src.replace(key, value)
Path('output/youtube-autopilot@.service').write_text(src)
PY
sudo install -m 644 output/youtube-autopilot@.service /etc/systemd/system/youtube-autopilot@.service
sudo install -m 644 linux/youtube-pipeline.slice /etc/systemd/system/youtube-pipeline.slice
sudo systemctl daemon-reload
sudo systemctl enable youtube-autopilot@en.service
.venv/bin/python linux/preflight.py --render-only
echo 'Installed. English service enabled for boot; not started. Dutch remains opt-in.'
echo 'Add keys to .env, transfer channel progress, authenticate, then run: ./manage.sh start'
