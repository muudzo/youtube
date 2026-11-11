"""Local readiness checks. Never prints credentials or calls external APIs."""

import argparse
import importlib.util
import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def credential_problems(root: Path, channel: str, env) -> list[str]:
    problems = []
    for name in ('GROQ_API_KEY', 'PEXELS_API_KEY'):
        value = env.get(name, '').strip()
        if not value or value.lower().startswith(('your-', 'replace', 'changeme')):
            problems.append(f'{name} is missing or a placeholder')
    token = root / ('token_nl.json' if channel == 'nl' else 'token.json')
    if not token.is_file():
        problems.append(f'{token.name} is missing; authenticate this channel first')
    else:
        try:
            data = json.loads(token.read_text())
            if not all(data.get(k) for k in ('refresh_token', 'client_id', 'client_secret')):
                problems.append(f'{token.name} lacks refreshable OAuth credentials')
        except (OSError, ValueError):
            problems.append(f'{token.name} is unreadable or invalid JSON')
    for name in ('.env', 'token.json', 'token_nl.json', 'client_secret.json'):
        path = root / name
        if path.exists() and stat.S_IMODE(path.stat().st_mode) & 0o077:
            problems.append(f'{name} must be owner-only (chmod 600)')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', choices=('en', 'nl'), default='en')
    parser.add_argument('--render-only', action='store_true', help='Check local rendering without API keys or OAuth')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=True)
    problems = []
    for command in ('ffmpeg', 'ffprobe'):
        if not shutil.which(command):
            problems.append(f'{command} is missing')
    for module in ('moviepy', 'PIL', 'edge_tts', 'pydub', 'googleapiclient'):
        if importlib.util.find_spec(module) is None:
            problems.append(f'Python dependency {module} is missing')
    from scripts.fonts import font_path
    try:
        font_path()
    except FileNotFoundError as exc:
        problems.append(str(exc))
    from config import MIN_FREE_DISK_GB
    if shutil.disk_usage(ROOT).free / 1024**3 < MIN_FREE_DISK_GB:
        problems.append(f'Less than {MIN_FREE_DISK_GB:g} GiB disk space available')
    if not args.render_only:
        problems.extend(credential_problems(ROOT, args.channel, os.environ))
    for problem in problems:
        print(f'WAITING: {problem}')
    if problems:
        return 1
    print('Local renderer ready' if args.render_only else f'{args.channel} deployment ready; API access and channel identity still require live verification')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
