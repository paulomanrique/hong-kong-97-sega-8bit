#!/usr/bin/env python3
"""Build the Mega Drive port's author-owned cheat screen and voice clip.

Inputs are copied privately to work/egg from the existing Mega Drive port.
Generated PNG/WAV files remain ignored alongside the ROM-derived assets.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SCREEN = ROOT / "res" / "gfx" / "screens" / "cheat.png"
WAV = ROOT / "res" / "music" / "cheat.wav"
CATCHPHRASE = "Eu sou cheteiro!!!"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT.parent / "hong-kong-97-genesis" / "res" / "egg",
        help="directory containing avatar.jpg, logo.png, and sound.mp3",
    )
    args = parser.parse_args()
    avatar_path = args.source / "avatar.jpg"
    logo_path = args.source / "logo.png"
    sound_path = args.source / "sound.mp3"
    for path in (avatar_path, logo_path, sound_path):
        if not path.is_file():
            raise SystemExit(f"missing Mega Drive cheat asset: {path}")

    screen = Image.new("RGBA", (256, 224), (0, 0, 0, 255))
    avatar = Image.open(avatar_path).convert("RGBA").resize(
        (128, 128), Image.Resampling.LANCZOS
    )
    screen.alpha_composite(avatar, (64, 48))

    logo = Image.open(logo_path).convert("RGBA")
    pixels = logo.load()
    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, _ = pixels[x, y]
            if min(r, g, b) > 150 and max(r, g, b) - min(r, g, b) < 40:
                pixels[x, y] = (0, 0, 0, 0)
    logo_width = 200
    logo_height = round(logo.height * logo_width / logo.width)
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    screen.alpha_composite(logo, ((256 - logo_width) // 2, 10))

    draw = ImageDraw.Draw(screen)
    font = ImageFont.load_default(size=22)
    box = draw.textbbox((0, 0), CATCHPHRASE, font=font)
    draw.text(((256 - (box[2] - box[0])) // 2, 192), CATCHPHRASE,
              fill=(255, 222, 0, 255), font=font)
    SCREEN.parent.mkdir(parents=True, exist_ok=True)
    screen.convert("RGB").save(SCREEN)

    WAV.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(sound_path),
        "-af", "loudnorm=I=-12:TP=-1:LRA=7",
        "-ar", "8000", "-ac", "1", "-c:a", "pcm_s16le", str(WAV),
    ], check=True)
    print(f"{SCREEN}\n{WAV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
