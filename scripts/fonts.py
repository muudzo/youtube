"""Resolve real typefaces on macOS and Ubuntu without proprietary font copies."""

import os
from pathlib import Path


MAC_FONTS = Path('/System/Library/Fonts/Supplemental')
LINUX_FONTS = Path('/usr/share/fonts/truetype')
LINUX_FACES = {
    'Impact.ttf': 'dejavu/DejaVuSans-Bold.ttf',
    'Arial Black.ttf': 'liberation/LiberationSans-Bold.ttf',
    'Verdana Bold.ttf': 'dejavu/DejaVuSerif-Bold.ttf',
    'Trebuchet MS Bold.ttf': 'liberation/LiberationSerif-Bold.ttf',
    'Arial Bold.ttf': 'dejavu/DejaVuSans-Bold.ttf',
}


def font_path(face: str = 'Arial Bold.ttf') -> str:
    """Prefer the native Mac face; otherwise use its installed open font."""
    override = os.getenv('YOUTUBE_CAPTION_FONT') if face == 'Arial Bold.ttf' else None
    candidates = [Path(override)] if override else []
    linux_face = LINUX_FACES.get(face, LINUX_FACES['Arial Bold.ttf'])
    candidates += [MAC_FONTS / face, LINUX_FONTS / linux_face,
                   LINUX_FONTS / linux_face.replace('liberation/', 'liberation2/')]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('No usable font installed. On Ubuntu run ./setup.sh (fonts-dejavu-core and fonts-liberation2).')
