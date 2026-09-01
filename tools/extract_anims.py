#!/usr/bin/env python3
"""Extract HK97 animations/sprites: PNG frames + JSON metadata.

Formats (see docs/mapping.md and $8087BA/$80863E/$8086D0 in the disasm):
- per type (0-14): $8A15=bank, $8A24/$8A33=ptr -> 12-byte header:
    +0 anim table (words, [i]=start of the frame list, [i+1]=end)
    +2 per-frame OAM table (words)
    +4 hitbox size (2 bytes/frame: nibbles w1,h1 / w2,h2)
    +6 hitbox offset (2 bytes/frame: nibbles)
    +8 draw box (4 bytes/frame: xofs, yofs, w, h)
- anim entry: 4 bytes (frame+1, duration, ?, ?)
- frame OAM: count, then 4 bytes/sprite: xofs, yofs (signed),
  tile, attr (raw bit4 = 16x16; &0xCF|0x20 + page $8AAB[type]*2)
Tiles: sheet from $84:8600 (512 4bpp tiles), OBJ palette = $84:A725.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hk97 import bgr555_palette, decompress, load_rom, lorom, snes_tile_4bpp

OUT = Path(__file__).resolve().parent.parent / "res" / "gfx" / "anim"
DOCS = Path(__file__).resolve().parent.parent / "docs"

TAB_BANK, TAB_LO, TAB_HI, TAB_PAGE = 0x8A15, 0x8A24, 0x8A33, 0x8AAB
NTYPES = 15

# anims referenced by the code, per type (to bound the scan)
MAX_ANIM = 0x14


def rd_w(rom: bytes, addr24: int) -> int:
    o = lorom(addr24)
    return rom[o] | (rom[o + 1] << 8)


def rd_b(rom: bytes, addr24: int) -> int:
    return rom[lorom(addr24)]


def main() -> int:
    rom = load_rom()
    OUT.mkdir(parents=True, exist_ok=True)

    tiles = decompress(rom, 0x848600)
    palraw = decompress(rom, 0x84A725)
    pal = bgr555_palette(palraw)          # OBJ lines 0-7 = same colors

    from PIL import Image

    def draw_sprite(img, ox, oy, tile, attr, big, page):
        tile_idx = (tile | ((attr + page * 2) & 1) << 8)
        palline = (attr >> 1) & 7
        hflip = bool(attr & 0x40)
        vflip = bool(attr & 0x80)
        size = 16 if big else 8
        for sy in range(0, size, 8):
            for sx in range(0, size, 8):
                # OBJ 16x16: tiles t, t+1, t+16, t+17 (see $8086D0)
                t = tile_idx + (sx // 8) + (sy // 8) * 16
                off = (t & 0x1FF) * 32
                if off + 32 > len(tiles):
                    continue
                px = snes_tile_4bpp(tiles, off)
                for y in range(8):
                    for x in range(8):
                        c = px[y][x]
                        if not c:
                            continue
                        dx = sx + x if not hflip else size - 1 - (sx + x)
                        dy = sy + y if not vflip else size - 1 - (sy + y)
                        tx, ty = ox + dx, oy + dy
                        if 0 <= tx < img.width and 0 <= ty < img.height:
                            img.putpixel((tx, ty),
                                         (*pal[palline * 16 + c], 255))

    # all 15 types point to the SAME header at $82:8000 (page 0);
    # the handlers only choose the anim id — extract once.
    meta: dict = {}
    if True:
        t, bank, page = 0, 0x82, 0
        base = 0x828000
        hdr = [rd_w(rom, base + i) for i in range(0, 12, 2)]
        anim_tab, oam_tab, hb_size, hb_off, drawbox, _ = hdr
        tmeta = {"page": page, "anims": {}}
        for a in range(MAX_ANIM):
            try:
                start = rd_w(rom, (bank << 16) | (anim_tab + a * 2))
                end = rd_w(rom, (bank << 16) | (anim_tab + a * 2 + 2))
            except AssertionError:
                break
            n = (end - start) // 4
            if not (0 < n <= 32 and 0x8000 <= start <= end <= 0xFFFF):
                continue
            frames = []
            for f in range(n):
                e = (bank << 16) | (start + f * 4)
                fid = rd_b(rom, e) - 1
                dur = rd_b(rom, e + 1)
                if fid < 0 or fid > 0x60:
                    frames = []
                    break
                # frame OAM
                optr = rd_w(rom, (bank << 16) | (oam_tab + fid * 2))
                cnt = rd_b(rom, (bank << 16) | optr)
                if not (0 < cnt <= 64):
                    frames = []
                    break
                sprites = []
                for s in range(cnt):
                    so = (bank << 16) | (optr + 1 + s * 4)
                    sx = rd_b(rom, so)
                    sy = rd_b(rom, so + 1)
                    tile = rd_b(rom, so + 2)
                    attr = rd_b(rom, so + 3)
                    sprites.append((sx - 256 if sx >= 128 else sx,
                                    sy - 256 if sy >= 128 else sy,
                                    tile, attr))
                hs = rd_w(rom, (bank << 16) | (hb_size + fid * 2))
                ho = rd_w(rom, (bank << 16) | (hb_off + fid * 2))
                db = [rd_b(rom, (bank << 16) | (drawbox + fid * 4 + i))
                      for i in range(4)]
                frames.append(dict(frame=fid, dur=dur, sprites=sprites,
                                   hb_size=hs, hb_off=ho, drawbox=db))
            if not frames:
                continue
            tmeta["anims"][a] = frames
            # render each frame
            for fi, fr in enumerate(frames):
                xs = [s[0] for s in fr["sprites"]]
                ys = [s[1] for s in fr["sprites"]]
                big = [16 if s[3] & 0x10 else 8 for s in fr["sprites"]]
                x0 = min(xs)
                y0 = min(ys)
                w = max(x + b for x, b in zip(xs, big)) - x0
                h = max(y + b for y, b in zip(ys, big)) - y0
                img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
                for sx, sy, tile, attr in fr["sprites"]:
                    draw_sprite(img, sx - x0, sy - y0, tile,
                                attr, attr & 0x10, page)
                img.save(OUT / f"a{a:02X}_f{fi}.png")
        meta["shared"] = tmeta
        print(f"anims extracted: {sorted(tmeta['anims'])}")

    with open(DOCS / "anims.json", "w") as f:
        json.dump(meta, f, indent=1)
    print("docs/anims.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
