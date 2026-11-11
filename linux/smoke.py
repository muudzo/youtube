"""Render synthetic test media with the real pipeline, without keys or uploads."""

import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=True)

from config import VIDEO_WIDTH, VIDEO_HEIGHT, SHORTS_WIDTH, SHORTS_HEIGHT, RENDER_THREADS, RENDER_LOCK_FILE
from scripts.render_lock import render_lock
from scripts.video_assembler import assemble_video
from scripts.shorts_generator import create_short
from scripts.thumbnail_generator import create_thumbnail
from scripts.nl.variation import THUMBNAIL_TREATMENTS
from PIL import Image


def main():
    out = ROOT / 'output' / 'linux-smoke'
    out.mkdir(parents=True, exist_ok=True)
    source = out / 'source.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=24',
                    '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-threads', str(RENDER_THREADS), str(source)], check=True)
    audio = out / 'tone.wav'
    with wave.open(str(audio), 'wb') as handle:
        handle.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b''.join(struct.pack('<h', int(3000 * math.sin(2 * math.pi * 440 * n / 24000))) for n in range(72000)))
    subtitles = [{'text': 'Ubuntu render test', 'start': 0, 'end': 1.5},
                 {'text': 'Nederland werkt ook', 'start': 1.5, 'end': 3}]
    with render_lock(RENDER_LOCK_FILE):
        assemble_video([source], audio, subtitles, out / 'landscape.mp4')
        create_short(audio, subtitles, [source], out / 'short.mp4', hook_text='VM TEST')
    background = out / 'background.png'
    Image.new('RGB', (1280, 720), (45, 80, 110)).save(background)
    for treatment in THUMBNAIL_TREATMENTS:
        create_thumbnail('Ubuntu klaar', background_image_path=background,
                         output_path=out / f'{treatment.name}.png', font_path=treatment.font)
    report = {}
    for name, expected in [('landscape.mp4', (VIDEO_WIDTH, VIDEO_HEIGHT)),
                           ('short.mp4', (SHORTS_WIDTH, SHORTS_HEIGHT))]:
        data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                         '-show_streams', '-show_format', '-of', 'json', str(out / name)]))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        audio_stream = next(s for s in data['streams'] if s['codec_type'] == 'audio')
        assert (video['width'], video['height']) == expected
        assert video['codec_name'] == 'h264' and audio_stream['codec_name'] == 'aac'
        assert float(data['format']['duration']) >= 2.9
        report[name] = {'size': list(expected), 'video': video['codec_name'],
                        'audio': audio_stream['codec_name'], 'seconds': data['format']['duration']}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('Synthetic smoke test passed. No API calls, authentication, or uploads performed.')


if __name__ == '__main__':
    main()
