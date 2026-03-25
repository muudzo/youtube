#!/bin/zsh
cd /Users/tatendanyemudzo/youtube
export PATH="/usr/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
/usr/bin/python3 -c "
from dotenv import load_dotenv
load_dotenv()
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
