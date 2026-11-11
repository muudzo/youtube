"""A CPU-rendered, original paper-cut story. No image/video generation API.

Uses free Edge speech for narration; all artwork, motion and music are generated
locally. Does not upload. Run from the repo: .venv/bin/python scripts/illustrated_demo.py
"""

import asyncio
import json
import math
import random
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fonts import font_path
from scripts.render_lock import render_lock

W, H, FPS = 1280, 720, 24
OUT = ROOT / 'output' / 'illustrated_demo'
STORY = [
    'Every night, the keeper lit a lamp for ships that never came.',
    'Then, one evening, a tiny boat appeared beyond the rocks.',
    'Its only passenger was a child, holding a broken compass.',
    'The keeper turned the great light toward the silent sea.',
    'Far away, a second light answered. Then another. Then a hundred.',
    'The child smiled. The ships were not lost. They were waiting.',
]
LABELS = ['01 / THE WATCH', '02 / THE ARRIVAL', '03 / THE COMPASS',
          '04 / THE SIGNAL', '05 / THE ANSWER', '06 / THE WAITING LIGHT']
INK = (9, 22, 35)
GOLD = (244, 194, 112)
FONT = ImageFont.truetype(font_path(), 32)
SMALL = ImageFont.truetype(font_path(), 15)
TITLE = ImageFont.truetype(font_path('Verdana Bold.ttf'), 38)
RNG = random.Random(420)
STARS = [(RNG.randint(25, W - 25), RNG.randint(35, 330), RNG.uniform(.5, 1.8)) for _ in range(65)]
LIGHTS = [(RNG.uniform(180, 1190), RNG.uniform(390, 495), RNG.uniform(.1, .9)) for _ in range(100)]


def sky(scene):
    top = np.array((10, 23, 40) if scene < 5 else (23, 40, 57))
    bottom = np.array((49, 84, 96) if scene < 5 else (133, 116, 102))
    rows = np.linspace(0, 1, H)[:, None, None]
    array = np.broadcast_to(top[None, None, :] * (1 - rows) + bottom[None, None, :] * rows, (H, W, 3)).astype('uint8').copy()
    frame = Image.fromarray(array).convert('RGBA')
    draw = ImageDraw.Draw(frame)
    for x, y, r in STARS:
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(155, 183, 194, 160))
    draw.ellipse((1020, 77, 1097, 154), fill=(220, 228, 211))
    draw.ellipse((1007, 65, 1080, 138), fill=(15, 30, 46))
    draw.polygon([(0, 424), (110, 365), (210, 389), (320, 348), (465, 418),
                  (640, 379), (790, 410), (890, 370), (1050, 412), (1280, 350), (1280, 500), (0, 500)], fill=(31, 61, 76))
    draw.rectangle((0, 430, W, H), fill=(20, 49, 65))
    return frame


BACKGROUNDS = [sky(i) for i in range(6)]


def boat(draw, x, y, scale=1., light=False):
    def p(a, b):
        return x+a*scale, y+b*scale
    draw.polygon([p(-45, 0), p(40, 0), p(24, 18), p(-22, 18)], fill=INK)
    draw.line([p(0, 0), p(0, -62)], fill=(30, 32, 36), width=max(1, int(3*scale)))
    draw.polygon([p(-3, -59), p(-3, -5), p(-35, -5)], fill=(139, 153, 149))
    if light:
        draw.ellipse([p(18, -6), p(24, 0)], fill=GOLD)


def person(draw, x, y, scale=1., child=False):
    # A consistent silhouette used in the close-up and final wide shot.
    radius = 12*scale
    draw.ellipse((x-radius, y-78*scale, x+radius, y-54*scale), fill=INK)
    draw.polygon([(x-15*scale, y-53*scale), (x+14*scale, y-53*scale),
                  (x+23*scale, y-8*scale), (x-24*scale, y-8*scale)], fill=(25, 45, 56) if child else INK)
    draw.line([(x-8*scale, y-10*scale), (x-10*scale, y+12*scale)], fill=INK, width=max(2, int(9*scale)))
    draw.line([(x+9*scale, y-10*scale), (x+12*scale, y+12*scale)], fill=INK, width=max(2, int(9*scale)))


def lighthouse(draw, x, base, scale, t, glow):
    def box(a, b, c, d):
        return (x+a*scale, base+b*scale, x+c*scale, base+d*scale)
    draw.polygon([(x-42*scale, base), (x+43*scale, base),
                  (x+25*scale, base-240*scale), (x-25*scale, base-240*scale)], fill=(180, 182, 166))
    draw.polygon([(x+12*scale, base), (x+43*scale, base),
                  (x+25*scale, base-240*scale), (x+8*scale, base-240*scale)], fill=(106, 131, 133))
    draw.rectangle(box(-33, -259, 33, -235), fill=(211, 177, 115))
    draw.rectangle(box(-24, -254, 24, -239), fill=GOLD)
    draw.polygon([(x-45*scale, base-259*scale), (x, base-290*scale),
                  (x+45*scale, base-259*scale)], fill=INK)
    draw.rectangle(box(-40, -239, 40, -234), fill=INK)
    for a in (-23, 0, 23):
        draw.line([(x+a*scale, base-256*scale), (x+a*scale, base-237*scale)], fill=INK, width=3)
    for yy in (-180, -125, -65):
        draw.rounded_rectangle(box(-5, yy, 6, yy+17), radius=3, fill=INK)
    draw.rounded_rectangle(box(-12, -34, 12, 2), radius=7, fill=INK)
    ly = base - 247*scale
    sweep = 25*math.sin(t*.45)
    glow.polygon([(x+15*scale, ly), (1280, ly-42+sweep), (1280, ly+100+sweep)], fill=(246, 206, 129, 24))
    glow.ellipse((x-40*scale, ly-38*scale, x+40*scale, ly+38*scale), fill=(255, 205, 128, 72))


def wrap(draw, text, font, width):
    lines, current = [], ''
    for word in text.split():
        candidate = (current+' '+word).strip()
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def frame_at(t):
    scene = min(5, int(t//5))
    u = (t % 5)/5
    image = BACKGROUNDS[scene].copy()
    draw = ImageDraw.Draw(image)
    # The sea moves independently from the sky and cliff layers.
    for row in range(18):
        y = 442+row*13
        amp = 1.5+row*.12
        points = [(x, y+amp*math.sin(x*.023+t*.8+row)) for x in range(-20, W+21, 20)]
        draw.line(points, fill=(50+row, 88+row, 101+row, 255), width=1 if row < 8 else 2)
    lights = Image.new('RGBA', (W, H))
    glow = ImageDraw.Draw(lights)
    if scene in (0, 1, 3):
        scale = 1.15 if scene == 3 else 1
        base = 570 if scene != 3 else 585
        x = 295 if scene != 3 else 440
        lighthouse(draw, x, base, scale, t, glow)
        draw.polygon([(0, 539), (122, 518), (220, 531), (315, 520), (404, 564),
                      (480, 609), (517, 720), (0, 720)], fill=(12, 30, 39))
        draw.line([(0, 539), (122, 518), (220, 531), (315, 520), (404, 564)], fill=(76, 109, 109), width=5)
        if scene == 1:
            boat(draw, 1030-u*220, 492+2*math.sin(t*1.8), 1.15, True)
            draw.polygon([(1040, 592), (1090, 544), (1120, 583), (1170, 564), (1240, 620)], fill=(12, 31, 42))
        if scene == 3:
            person(draw, 443, 300, .35)
    elif scene == 2:
        lighthouse(draw, 1050, 488, .53, t, glow)
        draw.polygon([(0, 580), (320, 550), (560, 575), (850, 720), (0, 720)], fill=INK)
        person(draw, 475+2*math.sin(t), 570, 2.6, child=True)
        draw.line([(438, 455), (490, 469), (536, 450)], fill=(28, 50, 60), width=17)
        cx, cy = 515, 449
        draw.ellipse((cx-29, cy-29, cx+29, cy+29), fill=(198, 153, 81), outline=GOLD, width=3)
        draw.ellipse((cx-23, cy-23, cx+23, cy+23), fill=(28, 49, 58))
        angle = -.4+u*.5
        draw.line([(cx, cy), (cx+16*math.sin(angle), cy-16*math.cos(angle))], fill=GOLD, width=3)
        glow.ellipse((cx-45, cy-45, cx+45, cy+45), fill=(246, 194, 111, 24))
    else:
        # Lights arrive in staggered groups, instead of appearing at once.
        reveal = (u if scene == 4 else 1.)
        for i, (x, y, jitter) in enumerate(LIGHTS):
            if scene == 4 and i/len(LIGHTS) > reveal:
                continue
            radius = 1.5+1.2*math.sin(t+jitter*5)**2
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=GOLD)
            draw.line([(x, y+7), (x+2, y+14+jitter*12)], fill=(142, 131, 103), width=2)
            glow.ellipse((x-10, y-10, x+10, y+10), fill=(244, 191, 97, 45))
        for i in range(5):
            boat(draw, 270+i*190, 475+8*math.sin(i), .35, True)
        if scene == 5:
            draw.polygon([(0, 605), (150, 566), (340, 580), (600, 720), (0, 720)], fill=INK)
            person(draw, 220, 570, 1.5)
            person(draw, 281, 581, 1., child=True)
    image = Image.alpha_composite(image, lights.filter(ImageFilter.GaussianBlur(10)))
    # A restrained camera push; actual object/water/light motion remains separate.
    zoom = 1 + .022*u
    zw, zh = int(W*zoom), int(H*zoom)
    image = image.resize((zw, zh), Image.Resampling.BILINEAR)
    left, top = int((zw-W)*(.35+.2*u)), int((zh-H)*.35)
    image = image.crop((left, top, left+W, top+H))
    # Letterbox, title, and captions are drawn after camera movement.
    overlay = Image.new('RGBA', (W, H))
    d = ImageDraw.Draw(overlay)
    d.rectangle((0, 0, W, 35), fill=(4, 12, 19, 255))
    d.rectangle((0, 620, W, H), fill=(4, 12, 19, 242))
    d.line((54, 66, 92, 66), fill=GOLD, width=2)
    d.text((106, 56), LABELS[scene], font=SMALL, fill=GOLD)
    if scene == 0:
        d.text((650, 246), 'THE WAITING', font=TITLE, fill=(237, 231, 211))
        d.text((650, 292), 'LIGHT', font=TITLE, fill=GOLD)
        d.text((653, 348), 'AN ORIGINAL ILLUSTRATED SHORT', font=SMALL, fill=(167, 190, 193))
    lines = wrap(d, STORY[scene], FONT, W-180)
    for n, line in enumerate(lines):
        width = d.textlength(line, font=FONT)
        d.text(((W-width)/2, 635+n*38), line, font=FONT, fill=(240, 235, 221))
    d.text((55, 10), '4kMUDZO  /  STORY LAB', font=SMALL, fill=(154, 175, 181))
    d.text((1070, 10), 'FICTION  /  00:30', font=SMALL, fill=(154, 175, 181))
    image = Image.alpha_composite(image, overlay).convert('RGB')
    # Brief dip-to-black between scenes; opening/ending fade in/out.
    gain = min(1., t/.6, (30-t)/.7)
    local = t % 5
    if scene > 0 and local < .18:
        gain *= .55 + .45*local/.18
    if gain < 1:
        image = Image.blend(Image.new('RGB', (W, H)), image, max(0, gain))
    return image


async def narrate():
    import edge_tts
    for i, text in enumerate(STORY):
        path = OUT / f'voice-{i}.mp3'
        if path.exists() and path.stat().st_size > 1000:
            continue
        print(f'Narrating scene {i+1}/6', flush=True)
        await asyncio.wait_for(edge_tts.Communicate(text, 'en-US-GuyNeural', rate='+5%').save(str(path)), timeout=40)


def music():
    sr = 24000
    t = np.arange(sr*30)/sr
    audio = np.zeros_like(t)
    # Original quiet ambient bed, no sampled or licensed music.
    for i, hz in enumerate((146.832, 220., 293.665, 349.228)):
        audio += .018*np.sin(2*np.pi*hz*t)*(.65+.35*np.sin(t*.23+i))
    audio *= np.minimum(1, t/2)*np.minimum(1, (30-t)/2)
    with wave.open(str(OUT/'ambient.wav'), 'wb') as f:
        f.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
        f.writeframes((audio*32767).astype('<i2').tobytes())


def audio_track():
    from pydub import AudioSegment
    combined = AudioSegment.silent(duration=30000, frame_rate=24000)
    for i in range(6):
        source = OUT/f'voice-{i}.mp3'
        clip = AudioSegment.from_file(source)
        # Fit long lines without cutting off words; preserve pitch with atempo.
        if len(clip) > 4700:
            sped = OUT/f'voice-{i}-fit.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-af',
                            f'atempo={len(clip)/4650:.5f}', str(sped)], check=True)
            clip = AudioSegment.from_wav(sped)
        combined = combined.overlay(clip, position=i*5000+100)
    music()
    combined = combined.overlay(AudioSegment.from_wav(OUT/'ambient.wav'))
    combined.export(OUT/'soundtrack.wav', format='wav')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'story.json').write_text(json.dumps({'title': 'The Waiting Light', 'fiction': True, 'scenes': STORY}, indent=2)+'\n')
    asyncio.run(narrate())
    audio_track()
    with render_lock(ROOT/'output'/'.render.lock'):
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
               '-i', str(OUT/'soundtrack.wav'), '-map', '0:v', '-map', '1:a',
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-threads', '2',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-t', '30',
               '-movflags', '+faststart', str(OUT/'the-waiting-light.mp4')]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for n in range(FPS*30):
                proc.stdin.write(frame_at(n/FPS).tobytes())
                if n % (FPS*5) == 0:
                    print(f'Rendering scene {n//(FPS*5)+1}/6', flush=True)
            proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError('FFmpeg encoding failed')
        except BaseException:
            proc.kill()
            proc.wait()
            raise
    for i in range(6):
        frame_at(i*5+2).save(OUT/f'scene-{i+1}.jpg', quality=90)
    # A contact sheet makes visual review quick.
    sheet = Image.new('RGB', (1280, 1080))
    for i in range(6):
        sheet.paste(frame_at(i*5+2).resize((640, 360)), ((i%2)*640, (i//2)*360))
    sheet.save(OUT/'storyboard.jpg', quality=93)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                       '-show_format', '-of', 'json', str(OUT/'the-waiting-light.mp4')]))
    assert abs(float(probe['format']['duration'])-30) < .15
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    assert (video['width'], video['height']) == (W, H)
    assert any(s['codec_type'] == 'audio' for s in probe['streams'])
    (OUT/'probe.json').write_text(json.dumps(probe, indent=2)+'\n')
    print(f'Finished: {OUT / "the-waiting-light.mp4"}', flush=True)


if __name__ == '__main__':
    main()
