"""
Video Assembler — stitches everything together into a final video.
Combines stock footage, narration audio, subtitles, and background music.
Compatible with MoviePy v2.
"""

import random
import sys
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    concatenate_audioclips,
    ColorClip,
    vfx,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    FPS,
    VIDEO_DIR,
    BG_MUSIC_VOLUME,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_FONT_COLOR,
    SUBTITLE_STROKE_COLOR,
    SUBTITLE_STROKE_WIDTH,
    SUBTITLE_POSITION,
)

# ─── Brightness settings ──────────────────────────────────
BRIGHTNESS_THRESHOLD = 60       # clips below this mean brightness are "dark"
BRIGHTNESS_SAMPLE_COUNT = 5     # number of frames to sample per clip
BRIGHTNESS_BOOST_FACTOR = 2.5   # multiplier applied to dark clips that we keep


def ken_burns_zoom(clip, zoom_start=1.0, zoom_end=1.15):
    """Apply subtle Ken Burns zoom effect — makes static footage feel alive."""
    w, h = clip.size

    def zoom_frame(get_frame, t):
        progress = t / max(clip.duration, 0.1)
        scale = zoom_start + (zoom_end - zoom_start) * progress
        frame = get_frame(t)
        # Scale up the frame
        new_w, new_h = int(w * scale), int(h * scale)
        from PIL import Image
        img = Image.fromarray(frame)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        # Center crop back to original size
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        img = img.crop((left, top, left + w, top + h))
        return np.array(img)

    return clip.transform(zoom_frame)


def apply_transition(clip, fade_duration=0.5):
    """Apply fade in/out transitions to a clip for smooth cuts."""
    if clip.duration <= fade_duration * 2:
        return clip
    clip = clip.with_effects([vfx.FadeIn(fade_duration), vfx.FadeOut(fade_duration)])
    return clip


def load_and_resize_clip(video_path: Path, target_duration: float) -> VideoFileClip:
    """Load a video clip, resize to target dimensions, and trim/loop to target duration."""
    clip = VideoFileClip(str(video_path))
    clip = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))

    if clip.duration > target_duration:
        max_start = clip.duration - target_duration
        start = random.uniform(0, max(0, max_start))
        clip = clip.subclipped(start, start + target_duration)
    elif clip.duration < target_duration:
        loops_needed = int(target_duration / clip.duration) + 1
        clip = concatenate_videoclips([clip] * loops_needed).subclipped(0, target_duration)

    # Apply Ken Burns zoom (subtle motion) + fade transitions
    clip = ken_burns_zoom(clip, zoom_start=1.0, zoom_end=random.uniform(1.08, 1.18))
    clip = apply_transition(clip, fade_duration=0.4)

    return clip


def measure_clip_brightness(video_path: Path) -> float:
    """Measure average brightness of a clip by sampling multiple frames.

    Returns the mean brightness across BRIGHTNESS_SAMPLE_COUNT evenly-spaced
    frames.  Returns 0.0 on error so the clip can still be considered.
    """
    try:
        clip = VideoFileClip(str(video_path))
        duration = clip.duration
        if duration <= 0:
            clip.close()
            return 0.0

        sample_times = [
            duration * (i + 1) / (BRIGHTNESS_SAMPLE_COUNT + 1)
            for i in range(BRIGHTNESS_SAMPLE_COUNT)
        ]

        brightness_values = []
        for t in sample_times:
            try:
                frame = clip.get_frame(min(t, duration - 0.05))
                brightness_values.append(float(frame.mean()))
            except Exception:
                pass

        clip.close()

        if not brightness_values:
            return 0.0
        return sum(brightness_values) / len(brightness_values)
    except Exception:
        return 0.0


def brighten_clip(clip):
    """Apply a brightness boost to a dark clip using a pixel multiplier."""

    def boost_image(frame):
        boosted = frame.astype(np.float32) * BRIGHTNESS_BOOST_FACTOR
        return np.clip(boosted, 0, 255).astype(np.uint8)

    return clip.image_transform(boost_image)


def create_footage_sequence(footage_files: list, total_duration: float):
    """Create a sequence of stock footage clips that fills the total duration."""
    if not footage_files:
        return ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=(10, 10, 10),
            duration=total_duration,
        )

    # ── Measure brightness of all clips ──────────────────
    bright_clips = []
    dark_clips = []
    for f in footage_files:
        brightness = measure_clip_brightness(f)
        if brightness >= BRIGHTNESS_THRESHOLD:
            bright_clips.append(f)
            print(f"  OK  brightness={brightness:.0f}  {Path(f).name}")
        else:
            dark_clips.append((f, brightness))
            print(f"  DARK brightness={brightness:.0f}  {Path(f).name}")

    # If enough bright clips, use only those; otherwise boost dark ones too
    if len(bright_clips) >= 3:
        usable = bright_clips
        needs_boost = []
        print(f"  Using {len(usable)} bright clips, skipping {len(dark_clips)} dark clips")
    else:
        # Not enough bright clips — boost the dark ones instead of skipping
        usable = bright_clips
        needs_boost = [f for f, _ in dark_clips]
        usable += needs_boost
        print(f"  Only {len(bright_clips)} bright clips — will brightness-boost {len(needs_boost)} dark clips")

    needs_boost_set = set(str(p) for p in needs_boost)

    # Use 5-10 second clips for a natural feel
    target_clip_duration = 8.0
    num_clips_needed = max(1, int(total_duration / target_clip_duration))

    # Shuffle clips for visual variety (stolen from MoneyPrinterTurbo)
    # Instead of sequential order, randomize for more dynamic feel
    random.shuffle(usable)
    selected = []
    for i in range(num_clips_needed):
        selected.append(usable[i % len(usable)])

    clip_duration = total_duration / len(selected)
    print(f"  Using {len(selected)} clips at ~{clip_duration:.1f}s each")

    clips = []
    for footage_path in selected:
        try:
            clip = load_and_resize_clip(footage_path, clip_duration)
            # Apply brightness boost if this was a dark clip
            if str(footage_path) in needs_boost_set:
                clip = brighten_clip(clip)
            clips.append(clip)
        except Exception as e:
            print(f"  Warning: Failed to load {footage_path}: {e}")
            clips.append(
                ColorClip(
                    size=(VIDEO_WIDTH, VIDEO_HEIGHT),
                    color=(20, 20, 30),
                    duration=clip_duration,
                )
            )

    return concatenate_videoclips(clips)


def create_subtitle_clips(subtitles: list, video_size: tuple = None) -> list:
    """Create TextClip overlays for each subtitle.

    MoviePy v2 notes:
    - with_position(('center', 0.85), relative=True) is needed for fractional
      positioning; without relative=True the float is treated as pixel offset.
    - method='caption' wraps text within `size` width; 'label' does not wrap.
    - font='Arial' works on macOS (system font).
    """
    subtitle_clips = []
    w = video_size[0] if video_size else VIDEO_WIDTH
    h = video_size[1] if video_size else VIDEO_HEIGHT

    for sub in subtitles:
        duration = sub["end"] - sub["start"]
        if duration <= 0:
            continue

        try:
            # Determine position — always use relative=True for fractional coords
            if SUBTITLE_POSITION == "center":
                pos = ("center", "center")
                relative = False
            else:
                # bottom-ish placement
                pos = ("center", 0.82)
                relative = True

            txt_clip = (
                TextClip(
                    text=sub["text"],
                    font_size=SUBTITLE_FONT_SIZE,
                    color=SUBTITLE_FONT_COLOR,
                    bg_color=None,                   # transparent background
                    stroke_color=SUBTITLE_STROKE_COLOR,
                    stroke_width=SUBTITLE_STROKE_WIDTH,
                    font="Arial",
                    method="caption",
                    size=(w - 200, None),
                    text_align="center",
                    transparent=True,
                )
                .with_position(pos, relative=relative)
                .with_start(sub["start"])
                .with_duration(duration)
            )
            subtitle_clips.append(txt_clip)
        except Exception as e:
            print(f"  Warning: Failed to create subtitle clip: {e}")

    return subtitle_clips


def assemble_video(
    footage_files: list,
    audio_path: Path,
    subtitles: list,
    output_path: Path,
    bg_music_path: Path = None,
) -> Path:
    """Assemble the final video from all components."""
    print("Assembling video...")

    # Load narration audio
    narration = AudioFileClip(str(audio_path))
    total_duration = narration.duration
    print(f"  Video duration: {total_duration:.1f}s")

    # Create footage sequence
    print("  Building footage sequence...")
    video = create_footage_sequence(footage_files, total_duration)

    # Create subtitle overlays
    print("  Adding subtitles...")
    subtitle_clips = create_subtitle_clips(subtitles, video_size=(VIDEO_WIDTH, VIDEO_HEIGHT))

    # Composite video + subtitles — explicitly set size
    final_video = CompositeVideoClip(
        [video] + subtitle_clips,
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
    )

    # Build audio track
    audio_tracks = [narration]
    if bg_music_path and bg_music_path.exists():
        print("  Adding background music...")
        bg_music = AudioFileClip(str(bg_music_path))
        if bg_music.duration < total_duration:
            loops = int(total_duration / bg_music.duration) + 1
            bg_music = concatenate_audioclips([bg_music] * loops)
        bg_music = bg_music.subclipped(0, total_duration)
        # Volume scale + professional fade-out (3 seconds) so it doesn't cut abruptly
        from moviepy.audio.fx import AudioFadeOut
        bg_music = bg_music.with_volume_scaled(BG_MUSIC_VOLUME).with_effects([AudioFadeOut(3)])
        audio_tracks.append(bg_music)

    final_audio = CompositeAudioClip(audio_tracks)
    final_video = final_video.with_audio(final_audio)

    # Render
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  Rendering to {output_path.name}...")
    final_video.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        preset="medium",
        threads=4,
    )

    # Cleanup
    final_video.close()
    narration.close()

    print(f"  Done! Video saved: {output_path}")
    return output_path


if __name__ == "__main__":
    print("Video assembler ready. Use assemble_video() with your components.")
