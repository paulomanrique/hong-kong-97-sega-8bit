#!/usr/bin/env python3
"""Extract the HK97 graphics to PNG in res/gfx/ (reference + rescomp).

Each "screen" simulates what the game does: palettes decompressed into the
CGRAM shadow (layered, offset = line*32), tiles into VRAM, a sequential
map (32x28, linear photo) or a compressed map. See docs/mapping.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hk97 import (bgr555_palette, decompress, load_rom, render_map)

OUT = Path(__file__).resolve().parent.parent / "res" / "gfx"

# base palette loaded at boot (BG 0-7 and OBJ 8-15)
PAL_BASE = 0x84A725
PAL_LINE0 = 0x84D4E7

# full-screen photos: (name, tiles, 16-color palette, palette line in the map)
PHOTOS = [
    ("intro1",   0x84A829, 0x84D483, 1),
    ("intro2",   0x84D516, 0x84D4F3, 1),
    ("intro5",   0x86CB82, 0x86CB5E, 1),
    ("gameover", 0x87AD9A, 0x87AD76, 1),
    ("gamebg0",  0x89D1A5, 0x89D181, 1),
    ("gamebg1",  0x899BA1, 0x899B7D, 1),
    ("gamebg2",  0x8A8C6D, 0x8A8C49, 1),
    ("gamebg3",  0x8AED01, 0x8AECDD, 1),
    ("gamebg4",  0x8BBC7E, 0x8BBC5A, 1),
    ("gamebg5",  0x8BEB49, 0x8BEB25, 1),
]


def seq_map(count: int, base: int) -> list[int]:
    return [base + i for i in range(count)]


def make_shadow(rom: bytes, layers: list[tuple[int, int]]) -> bytes:
    """Apply palette streams (addr, offset_bytes) into the 0x200 shadow."""
    shadow = bytearray(0x200)
    for addr, off in layers:
        d = decompress(rom, addr)
        shadow[off:off + len(d)] = d
    return bytes(shadow)


def main() -> int:
    rom = load_rom()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- 256x224 photos (BG2: tiles from word $2000, sequential 32x28
    #     map with entry = 0x200+i and the palette on line 1)
    for name, tiles_a, pal_a, palline in PHOTOS:
        tiles = decompress(rom, tiles_a)
        shadow = make_shadow(rom, [(PAL_BASE, 0), (pal_a, palline * 0x20)])
        pal = bgr555_palette(shadow)
        # like the game (rect $B757): tile index = position (0..0x37F),
        # relative to the BG2 char base — indices fit in the 10 bits.
        tmap = seq_map(32 * 28, palline << 10)
        img = render_map(tiles, tmap, pal, 32, 28, tile_base_word=0)
        img.save(OUT / f"{name}.png")
        print(f"{name}.png  ({len(tiles):#x} bytes of tiles)")

    # --- sprite/title tileset ($84:8600 -> VRAM $0000, 16KB, 512 tiles)
    #     32x16-tile sheet with OBJ palette line 8 (= A725 line 0)
    tiles = decompress(rom, 0x848600)
    shadow = make_shadow(rom, [(PAL_LINE0, 0), (PAL_BASE, 0), (PAL_BASE, 0x100)])
    pal = bgr555_palette(shadow)
    n = len(tiles) // 32
    for pl in (8, 9, 10, 11):
        tmap = seq_map(n, 0x000 | (pl << 10))
        img = render_map(tiles, tmap, pal, 32, (n + 31) // 32,
                         tile_base_word=0)
        img.save(OUT / f"sprites_pal{pl}.png")
    print(f"sprites_pal8..11.png  ({n} tiles)")

    # --- reference palettes (text dump)
    with open(OUT / "palettes.txt", "w") as f:
        for name, _, pal_a, _ in PHOTOS:
            d = decompress(rom, pal_a)
            cols = bgr555_palette(d)
            f.write(f"{name}: " + " ".join(
                f"#{r:02x}{g:02x}{b:02x}" for r, g, b in cols) + "\n")
    print("palettes.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
