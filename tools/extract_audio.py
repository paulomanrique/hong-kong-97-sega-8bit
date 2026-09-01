#!/usr/bin/env python3
"""Extract and decode the HK97 music BRR sample -> WAV.

The game has a single sample (the music's infinite loop), no SFX.
IPL upload: driver at APU $0800, DIR at $3C00 (start=loop=$3C10),
BRR data at $3C10 (0x60AE bytes). Rate: 8000 Hz — measured by
autocorrelation of the SNES audio dumped in BizHawk (5.61s loop,
44000 samples => 7846 Hz ~ nominal 8000).

Usage: python tools/extract_audio.py [--rate 8000]
"""
import argparse
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hk97 import load_rom

BRR_FILE_OFF = 0x78C9E          # IPL block data (4-byte header before it)
BRR_LEN = 0x60AE
OUT_DIR = Path(__file__).resolve().parent.parent / "res" / "music"


def decode_brr(data: bytes) -> list[int]:
    """Decode 9-byte BRR blocks (filters 0-3) into 16-bit PCM."""
    out: list[int] = []
    p1 = p2 = 0
    for boff in range(0, len(data) - 8, 9):
        hdr = data[boff]
        shift = hdr >> 4
        filt = (hdr >> 2) & 3
        for i in range(8):
            byte = data[boff + 1 + i]
            for nib in (byte >> 4, byte & 0xF):
                s = nib - 16 if nib >= 8 else nib
                if shift <= 12:
                    v = (s << shift) >> 1
                else:
                    v = (-2048 if s < 0 else 0)  # invalid shift
                if filt == 1:
                    v += p1 + (-p1 >> 4)
                elif filt == 2:
                    v += (p1 << 1) + ((-((p1 << 1) + p1)) >> 5) \
                        - p2 + (p2 >> 4)
                elif filt == 3:
                    v += (p1 << 1) + ((-(p1 + (p1 << 2) + (p1 << 3))) >> 6) \
                        - p2 + (((p2 << 1) + p2) >> 4)
                v = max(-32768, min(32767, v))
                # hardware 15-bit wrap (clamp already covers the audible range)
                p2, p1 = p1, v
                out.append(v)
        if hdr & 1:                      # END flag
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=8000)
    args = ap.parse_args()

    rom = load_rom()
    pcm = decode_brr(rom[BRR_FILE_OFF:BRR_FILE_OFF + BRR_LEN])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    wav_path = OUT_DIR / "music.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(args.rate)
        w.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))
    dur = len(pcm) / args.rate
    print(f"{wav_path}  ({len(pcm)} samples @ {args.rate} Hz = {dur:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
