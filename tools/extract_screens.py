#!/usr/bin/env python3
"""Reconstruct every HK97 screen as a PNG (res/gfx/screens/).

Emulates the game's load primitives (see docs/mapping.md):
  decomp -> WRAM $7F:9000 buffer, DMA buffer->VRAM, fill VRAM,
  rectangle scripts (BG2 map $5800), text renderer (BG3 2bpp framebuffer
  at $6000, sequential map $7C00), layered palettes in the shadow.
Video: Mode 1. BG1 tiles $0000 map $5C00; BG2 tiles $2000 map $5800;
BG3 2bpp tiles $6000 map $7C00. Composition: BG3 (prio) > BG1 > BG2.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hk97 import bgr555_palette, decompress, load_rom, lorom, _Src

OUT = Path(__file__).resolve().parent.parent / "res" / "gfx" / "screens"

FONT_BASE = 0x838000   # text glyphs (linear across the banks)


class Screen:
    def __init__(self, rom: bytes):
        self.rom = rom
        self.vram = bytearray(0x10000)          # 64KB, byte-indexed
        self.buf = bytearray(0x8000)            # WRAM $7F:8000..FFFF
        self.cgram = bytearray(0x200)
        # boot: line 0 and OBJ palettes
        self.pal(0x84D4E7, 0x000)

    # ---- primitives ----
    def pal(self, src24: int, off: int) -> None:
        d = decompress(self.rom, src24)
        self.cgram[off:off + len(d)] = d

    def decomp(self, src24: int, buf_off: int = 0x1000) -> None:
        d = decompress(self.rom, src24)
        self.buf[buf_off:buf_off + len(d)] = d

    def dma(self, buf_off: int, vram_word: int, nbytes: int) -> None:
        self.vram[vram_word * 2:vram_word * 2 + nbytes] = \
            self.buf[buf_off:buf_off + nbytes]

    def fill(self, vram_word: int, nbytes: int, value: int = 0) -> None:
        for i in range(nbytes // 2):
            a = (vram_word + i) * 2
            self.vram[a] = value & 0xFF
            self.vram[a + 1] = value >> 8

    def wword(self, vram_word: int, value: int) -> None:
        self.vram[vram_word * 2] = value & 0xFF
        self.vram[vram_word * 2 + 1] = (value >> 8) & 0xFF

    def rword(self, vram_word: int) -> int:
        return self.vram[vram_word * 2] | (self.vram[vram_word * 2 + 1] << 8)

    def clear_b147(self) -> None:
        """$B147: sequential BG3 map (prio), BG1 map zeroed, fb cleared."""
        for i in range(0x400):
            self.wword(0x7C00 + i, 0x2000 + i)
        self.fill(0x5C00, 0x800)
        self.clear_fb()

    def clear_fb(self) -> None:          # $B1E1 (+$B1AC for the BG1 map)
        self.fill(0x5C00, 0x800)
        self.fill(0x6000, 0x3800)        # words $6000..$7C00 (BG3 fb)

    def clear_bg2_b2ba(self) -> None:    # $B2BA
        self.fill(0x2000, 0xC00 * 9 + 0x400)

    def rect(self, src24: int) -> None:
        """$B757: rectangles in the BG2 map ($5800)."""
        src = _Src(self.rom, src24)
        while True:
            col = src.word()
            if col == 0xFFFF:
                break
            row, w, h, base = (src.word(), src.word(), src.word(),
                               src.word())
            for r in range(h):
                off = (row + r) * 32 + col
                for c in range(w):
                    self.wword(0x5800 + off + c, off + c + base)

    # ---- text (BG3 framebuffer) ----
    def _fb_addr(self, x: int, y: int) -> int:        # $B8FA
        return 0x6000 + x * 8 + (y & 0xFF) * 0x100

    def _blit(self, file_off: int, fb: int, nwords: int,
              halves: int = 2) -> None:
        for half in range(halves):
            src = file_off + half * 0x100
            dst = fb + half * 0x100
            for i in range(nwords):
                self.wword(dst + i, self.rom[src + i * 2]
                           | (self.rom[src + i * 2 + 1] << 8))

    def text(self, src24: int, wide: bool = False) -> None:
        """$B87B (wide=False) or $B7B4 (wide=True): text pages."""
        src = _Src(self.rom, src24)
        font = lorom(FONT_BASE)
        while True:
            x = src.word()
            y = src.word()
            while True:
                c = src.word()
                if c == 0xFFFF:
                    break
                if wide:                 # $B81B: 8x8 glyph (1 half)
                    off = font + (c >> 4) * 0x100 + (c & 0xF) * 0x10
                    self._blit(off, self._fb_addr(x, y), 8, halves=1)
                    x += 1
                elif c < 0x10:           # $B915: 8x16 glyph
                    off = font + (c >> 4) * 0x100 + (c & 0xF) * 0x10
                    self._blit(off, self._fb_addr(x, y), 8)
                    x += 1
                else:
                    off = font + (c >> 3) * 0x200 + (c & 7) * 0x20
                    self._blit(off, self._fb_addr(x, y), 16)
                    x += 2
            nxt = src.word()
            if nxt == 0xFFFF:
                break
            src.addr -= 2       # give the word back (new x,y header)
            if src.addr < 0x8000:
                src.addr += 0x8000
                src.bank -= 1

    # ---- render ----
    def render(self, bg1=True, bg2=True, bg3=True):
        from PIL import Image
        pal = bgr555_palette(self.cgram)
        img = Image.new("RGB", (256, 224), pal[0])
        put = img.putpixel
        for ty in range(28):
            for tx in range(32):
                moff = ty * 32 + tx
                # BG2 (background): 4bpp tiles @ $2000
                if bg2:
                    self._draw4(put, tx, ty, self.rword(0x5800 + moff),
                                0x2000, pal)
                if bg1:
                    self._draw4(put, tx, ty, self.rword(0x5C00 + moff),
                                0x0000, pal)
                if bg3:
                    self._draw2(put, tx, ty, self.rword(0x7C00 + moff),
                                0x6000, pal)
        return img

    def _draw4(self, put, tx, ty, entry, base_word, pal) -> None:
        idx = entry & 0x3FF
        pl = (entry >> 10) & 7
        a = (base_word + idx * 16) * 2
        if a + 32 > len(self.vram):
            return
        for y in range(8):
            p0 = self.vram[a + y * 2]
            p1 = self.vram[a + y * 2 + 1]
            p2 = self.vram[a + 16 + y * 2]
            p3 = self.vram[a + 16 + y * 2 + 1]
            if not (p0 | p1 | p2 | p3):
                continue
            for x in range(8):
                b = 7 - x
                c = (((p0 >> b) & 1) | ((p1 >> b) & 1) << 1
                     | ((p2 >> b) & 1) << 2 | ((p3 >> b) & 1) << 3)
                if c:
                    put((tx * 8 + x, ty * 8 + y), pal[pl * 16 + c])

    def _draw2(self, put, tx, ty, entry, base_word, pal) -> None:
        idx = entry & 0x3FF
        pl = (entry >> 10) & 7
        a = (base_word + idx * 8) * 2
        for y in range(8):
            p0 = self.vram[a + y * 2]
            p1 = self.vram[a + y * 2 + 1]
            if not (p0 | p1):
                continue
            for x in range(8):
                b = 7 - x
                c = ((p0 >> b) & 1) | ((p1 >> b) & 1) << 1
                if c:
                    put((tx * 8 + x, ty * 8 + y), pal[pl * 4 + c])


# ---------------------------------------------------------------- catalog

STORY = {  # [page][language] -> (script, wide)
    1: [(0x808C1D, 0), (0x80909B, 0), (0x8098A7, 1)],
    2: [(0x808D7B, 0), (0x809135, 0), (0x809A6F, 1)],
    3: [(0x808BB9, 0), (0x809045, 0), (0x809805, 1)],
}
INTRO_TXT = {  # [page 2..5][language]
    2: [(0x808EBD, 0), (0x8091B3, 0), (0x809431, 1)],
    3: [(0x808F23, 0), (0x8091ED, 0), (0x8094F1, 1)],
    4: [(0x808F89, 0), (0x80924D, 0), (0x8095EB, 1)],
    5: [(0x808FE7, 0), (0x8092A7, 0), (0x8096CD, 1)],
}


def save(scr: Screen, name: str, **kw) -> None:
    scr.render(**kw).save(OUT / f"{name}.png")
    # separate layers for the Mega Drive: photo (BG1+BG2) and text (BG3).
    # text comes out with a magenta background = the rescomp transparent color.
    (OUT / "layers").mkdir(exist_ok=True)
    photo = scr.render(bg3=False)
    photo.save(OUT / "layers" / f"{name}_photo.png")
    txt = scr.render(bg1=False, bg2=False, bg3=True)
    px = txt.load()
    from PIL import Image
    mag = Image.new("RGB", txt.size, (255, 0, 255))
    mpx = mag.load()
    for y in range(txt.height):
        for x in range(txt.width):
            if px[x, y] != (0, 0, 0):
                mpx[x, y] = px[x, y]
    mag.save(OUT / "layers" / f"{name}_text.png")
    print(f"{name}.png")


def main() -> int:
    rom = load_rom()
    OUT.mkdir(parents=True, exist_ok=True)

    # language select (plain text; the cursor is a sprite, not rendered)
    s = Screen(rom)
    s.clear_b147()
    s.text(0x808B05)
    save(s, "langselect")

    # story: 3 pages x 3 languages
    for page, langs in STORY.items():
        for lang, (ptr, wide) in enumerate(langs):
            s = Screen(rom)
            s.clear_b147()
            s.text(ptr, wide)
            save(s, f"story{page}_l{lang}")

    # language-3 screens (hidden menu)
    for name, tiles, palp, rect in (
            ("lang3_1", 0x8882A0, 0x88827C, 0x80C6C6),
            ("lang3_2", 0x88DA71, 0x88DA4D, 0x80C6D2)):
        s = Screen(rom)
        s.clear_b147()
        s.decomp(tiles)
        s.dma(0x1000, 0x2000, 0x7000)
        s.pal(palp, 0x20)
        s.clear_fb()
        s.rect(rect)
        save(s, name)

    # intro pages 1..5 (2..5 have per-language text)
    intro = {
        1: (0x84A829, 0x84D483, 0x80C6DE, None),
        2: (0x84D516, 0x84D4F3, 0x80C6F4, INTRO_TXT[2]),
        3: (None,     0x8599ED, 0x80C700, INTRO_TXT[3]),
        4: (None,     0x85ECA9, 0x80C70C, INTRO_TXT[4]),
        5: (0x86CB82, 0x86CB5E, 0x80C718, INTRO_TXT[5]),
    }
    for page, (tiles, palp, rect, txts) in intro.items():
        for lang in (range(3) if txts else (0,)):
            s = Screen(rom)
            s.clear_b147()
            if page == 3:
                s.decomp(0x8684B5)
                s.decomp(0x85AD0D)
                s.dma(0x1000, 0x2000, 0x7000)
                s.decomp(0x859A51)
                s.dma(0x1000, 0x0000, 0x4000)
                s.decomp(0x85AA58)
                s.dma(0x1000, 0x5C00, 0x800)
            elif page == 4:
                s.decomp(0x8684B5)
                s.dma(0x1000, 0x2000, 0x7000)
                s.decomp(0x85ECED)
                s.dma(0x1000, 0x0000, 0x4000)
                s.decomp(0x868289)
                s.dma(0x1000, 0x5C00, 0x800)
            else:
                s.fill(0x0000, 0x4000)
                s.decomp(tiles)
                s.dma(0x1000, 0x2000, 0x7000)
            s.pal(palp, 0x20)
            if page in (3, 4):
                s.fill(0x6000, 0x3800)   # only the fb ($B1E1), keep the BG1 map
            else:
                s.clear_fb()
            if txts:
                ptr, wide = txts[lang]
                s.text(ptr, wide)
            s.rect(rect)
            suffix = f"_l{lang}" if txts else ""
            save(s, f"intro{page}{suffix}")

    # game over: photo + 2 text screens
    s = Screen(rom)
    s.clear_b147()
    s.fill(0x0000, 0x4000)
    s.decomp(0x87AD9A)
    s.dma(0x1000, 0x2000, 0x7000)
    s.pal(0x87AD76, 0x20)
    s.clear_fb()
    s.rect(0x80C8D7)
    save(s, "gameover1")
    s.clear_bg2_b2ba()
    s.clear_fb()
    s.text(0x8092EF)
    save(s, "gameover2")
    s.clear_fb()
    s.text(0x809399)
    save(s, "gameover3")

    # game screen: HUD ($BDE7) over a background, with the game palette
    s = Screen(rom)
    s.pal(0x84A725, 0x000)
    s.pal(0x84D4E7, 0x000)
    s.clear_b147()
    s.decomp(0x89D1A5)
    s.dma(0x1000, 0x2000, 0x7000)
    s.pal(0x89D181, 0x20)
    s.rect(0x80BDE7)
    save(s, "game_hud_bg0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
