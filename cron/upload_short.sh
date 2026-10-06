#!/bin/zsh
# Manual: re-upload the most recent Short that's still on disk.
# Useful when a daemon run rendered a Short but its upload failed (the Short
# mp4 is kept on disk in that case).
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
[ -f "$REPO_DIR/.env" ] && { set -a; source "$REPO_DIR/.env"; set +a; }
PY="$REPO_DIR/.venv/bin/python"
"$PY" -c "
from dotenv import load_dotenv
load_dotenv(override=True)
from pathlib import Path
from scripts.youtube_uploader import upload_video
import glob, json

shorts = sorted(glob.glob('output/videos/*_short.mp4'), key=lambda f: Path(f).stat().st_mtime, reverse=True)
if shorts:
    short = shorts[0]
    slug = Path(short).stem.replace('_short','')
    script_file = f'output/{slug}_script.json'
    title = Path(short).stem.replace('_', ' ').title()
    if Path(script_file).exists():
        s = json.load(open(script_file))
        title = s.get('title', title)
    upload_video(short, title=title, is_short=True, privacy='public')
    print(f'Uploaded Short: {title}')
else:
    print('No Shorts to upload')
"
