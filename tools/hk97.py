#!/usr/bin/env python3
"""Shared module: LoROM mapping, the HK97 LZSS decompressor, SNES tile
decoding and screen rendering.

Formats deduced from disasm/hk97_trace.asm (see docs/mapping.md).
"""
from pathlib import Path

ROM_PATH = Path(__file__).resolve().parent.parent / "work" / "hk97.sfc"


def load_rom() -> bytes:
    return ROM_PATH.read_bytes()


def lorom(addr24: int) -> int:
    """SNES address ($BB:AAAA) -> file offset."""
    bank = (addr24 >> 16) & 0x7F
    addr = addr24 & 0xFFFF
    assert addr >= 0x8000, hex(addr24)
    return bank * 0x8000 + (addr - 0x8000)


class _Src:
    """Read cursor that replicates the game's pointer advance
    (LoROM: past $FFFF it wraps to $8000 of the next bank)."""

    def __init__(self, rom: bytes, addr24: int):
        self.rom = rom
        self.bank = (addr24 >> 16) & 0xFF
        self.addr = addr24 & 0xFFFF

    def byte(self) -> int:
        v = self.rom[lorom((self.bank << 16) | self.addr)]
        self.addr += 1
        if self.addr == 0x10000:
            self.addr = 0x8000
            self.bank += 1
        return v

    def word(self) -> int:
        lo = self.byte()
        return lo | (self.byte() << 8)


def decompress(rom: bytes, addr24: int) -> bytes:
    """HK97 custom LZSS ($9DCE). First word = output size."""
    src = _Src(rom, addr24)
    total = src.word()
    out = bytearray()

    def copy_match(dist: int, length: int) -> None:
        pos = len(out) - dist
        assert pos >= 0, f"match before the start (dist={dist})"
        for _ in range(length):
            out.append(out[pos])
            pos += 1

    while len(out) < total:
        b = src.byte()
        mode = b >> 6
        if mode == 0:
            copy_match((b >> 2) + 1, (b & 3) + 3)
        elif mode == 1:
            lo = src.byte()
            copy_match((((b >> 2) & 0xF) << 8 | lo) + 1, (b & 3) + 3)
        elif mode == 2:
            lo = src.byte()
            copy_match(((b & 3) << 8 | lo) + 1, ((b >> 2) & 0xF) + 7)
        else:
            # mode 3: sub-mode = number of 1 bits after the '11' bits (b5..b3)
            if b & 0x20 == 0:            # 110L NNNN
                b2 = src.byte()
                b3 = src.byte()
                length = ((b2 & 0xF0) | (b & 0x0F)) + 7 + (((b >> 4) & 1) << 8)
                copy_match(((b2 & 0x0F) << 8 | b3) + 1, length)
            elif b & 0x10 == 0:          # 1110 NNNN: short literals
                for _ in range((b & 0x0F) + 1):
                    out.append(src.byte())
            elif b & 0x08 == 0:          # 11110LLL: very long match
                # the ROR chain at $9F16 is equivalent to:
                #   len_hi = (b&7)<<4 | b3>>4;  dist = (b3&0xF)<<8 | b4
                len_lo = src.byte()
                b3 = src.byte()
                dist_lo = src.byte()
                length = ((((b & 7) << 4) | (b3 >> 4)) << 8 | len_lo) + 0x207
                copy_match(((b3 & 0x0F) << 8 | dist_lo) + 1, length)
            else:                        # 11111 0LL: long literals
                lo = src.byte()
                for _ in range(((b & 3) << 8 | lo) + 0x11):
                    out.append(src.byte())
    assert len(out) == total, f"overshoot: {len(out)} != {total}"
    return bytes(out)


def snes_tile_4bpp(data: bytes, off: int) -> list[list[int]]:
    """Decode one 8x8 4bpp planar SNES tile -> index matrix."""
    px = [[0] * 8 for _ in range(8)]
    for y in range(8):
        p0 = data[off + y * 2]
        p1 = data[off + y * 2 + 1]
        p2 = data[off + 16 + y * 2]
        p3 = data[off + 16 + y * 2 + 1]
        for x in range(8):
            bit = 7 - x
            px[y][x] = (((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                        | (((p2 >> bit) & 1) << 2) | (((p3 >> bit) & 1) << 3))
    return px


def bgr555_palette(data: bytes) -> list[tuple[int, int, int]]:
    """CGRAM (BGR555 words) -> RGB888 list (x8 expansion with replication)."""
    pal = []
    for i in range(0, len(data), 2):
        v = data[i] | (data[i + 1] << 8)
        r = (v & 0x1F) << 3
        g = ((v >> 5) & 0x1F) << 3
        b = ((v >> 10) & 0x1F) << 3
        pal.append((r | r >> 5, g | g >> 5, b | b >> 5))
    return pal


def render_map(tiles: bytes, tilemap: list[int], pal256, width: int,
               height: int, tile_base_word: int = 0):
    """Render a SNES tilemap (vPhcccccccccc entries) into an RGB image.

    tiles: 4bpp data whose VRAM word 0 is tile_base_word.
    tilemap: width*height entries.
    """
    from PIL import Image
    img = Image.new("RGB", (width * 8, height * 8))
    put = img.putpixel
    cache: dict[int, list[list[int]]] = {}
    for ty in range(height):
        for tx in range(width):
            e = tilemap[ty * width + tx]
            idx = e & 0x3FF
            palline = (e >> 10) & 7
            hflip = bool(e & 0x4000)
            vflip = bool(e & 0x8000)
            off = idx * 32 - tile_base_word * 2
            if off < 0 or off + 32 > len(tiles):
                continue
            if off not in cache:
                cache[off] = snes_tile_4bpp(tiles, off)
            px = cache[off]
            for y in range(8):
                for x in range(8):
                    c = px[y if not vflip else 7 - y][
                        x if not hflip else 7 - x]
                    rgb = pal256[palline * 16 + c] if c else pal256[0]
                    put((tx * 8 + x, ty * 8 + y), rgb)
    return img


def parse_rect_script(rom: bytes, addr24: int) -> list[dict]:
    """Interpret a $B757/$B734 script: list of rectangles in the BG2 map.

    Format (words): col, row, width, height, base; terminated by FFFF.
    entry(map) = (row*32+col) + base  (incrementing per cell).
    """
    src = _Src(rom, addr24)
    rects = []
    while True:
        col = src.word()
        if col == 0xFFFF:
            break
        row = src.word()
        w = src.word()
        h = src.word()
        base = src.word()
        rects.append(dict(col=col, row=row, w=w, h=h, base=base))
    return rects
