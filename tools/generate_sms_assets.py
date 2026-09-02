#!/usr/bin/env python3
"""Build deterministic SMS/Game Gear Mode-4 assets from extracted HK97 data.

This is an offline converter.  It consumes PNG/WAV/JSON files produced by the
repository's extractors; it never reads, embeds, or executes the original ROM.

Background bundle layout (all integers little-endian)::

    0x00  char[4]  "S4BG"
    0x04  u8       version (1)
    0x05  u8       width in tiles (32)
    0x06  u8       height in tiles (28)
    0x07  u8       flags (bit 0 gameplay, bit 1 protected-tile conflict)
    0x08  u16      tile count
    0x0a  u16      palette byte count (16 SMS, 32 Game Gear)
    0x0c  u16      tile-data offset (32 SMS, 48 Game Gear)
    0x0e  u16      tilemap offset
    0x10  palette  SMS u8[16], or Game Gear little-endian u16[16]
          ...      32-byte Mode-4 patterns, then 32x28 little-endian entries

The even PCM sample is stored in the high nibble of each music byte.  Sprite
tile numbers are local to the VDP's sprite pattern half (register 6 selects it).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import wave
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from PIL import Image, ImageOps
except ImportError as exc:  # pragma: no cover - exercised by the CLI environment
    raise SystemExit("Pillow is required: python -m pip install Pillow") from exc

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 224
MAP_WIDTH = 32
MAP_HEIGHT = 28
GG_LCD_WIDTH = 160
GG_LCD_HEIGHT = 144
GG_VIEW_X = 48
GG_VIEW_Y = 24
GG_TEXT_COLUMNS = GG_LCD_WIDTH // 8
TEXT_TRANSPARENT = (255, 0, 255)
STATIC_TILE_BUDGET = 440
GAME_TILE_BUDGET = 256
DIGIT_TILE_RESERVE = 40
DIGIT_TILE_BASE = 216
DIGIT_COLOR_INDICES = (14, 15)
# In 224-line mode the name table occupies 0x3700..0x3dff, overlapping
# sprite patterns 440..495. With sprites in the second pattern half, only
# indices 256..439 are safe: 184 physical patterns. In native 8x16 mode each
# SAT entry consumes an aligned pair, so the cache holds 92 sprite units.
SPRITE_TILE_BUDGET = 92
GG_SPRITE_TILE_BUDGET = 96
GAMEPLAY_SUBTRACT = (24 * 8, 16 * 8, 8 * 8)
BANK_SIZE = 16 * 1024
BG_BUNDLE_HEADER = struct.Struct("<4sBBBBHHHH")
BG_BUNDLE_MAGIC = b"S4BG"
BG_BUNDLE_VERSION = 1

USED_ANIMS = (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08,
              0x09, 0x0A, 0x0C, 0x0D, 0x0E, 0x0F, 0x10)

HFLIP_BIT = 0x0200
VFLIP_BIT = 0x0400


def _component_bits(target: str) -> int:
    if target not in ("sms", "gg"):
        raise ValueError(f"unsupported target {target!r}")
    return 4 if target == "gg" else 2


def _hw_component(value: int, bits: int = 2) -> int:
    """Project an 8-bit component to a native 2-bit or 4-bit component."""
    levels = (1 << bits) - 1
    return (int(value) * levels + 127) // 255


def _hw_rgb(rgb: Sequence[int], bits: int = 2) -> tuple[int, int, int]:
    levels = (1 << bits) - 1
    return tuple((_hw_component(v, bits) * 255 + levels // 2) // levels
                 for v in rgb[:3])  # type: ignore[return-value]


def pack_cram_color(rgb: Sequence[int], target: str = "sms") -> int:
    """Pack RGB as SMS 00BBGGRR or Game Gear 0000BBBBGGGGRRRR."""
    bits = _component_bits(target)
    r, g, b = (_hw_component(v, bits) for v in rgb[:3])
    return r | (g << bits) | (b << (bits * 2))


def encode_cram_palette(palette: Sequence[Sequence[int]],
                        target: str = "sms") -> bytes:
    colors = [pack_cram_color(color, target) for color in palette]
    if target == "gg":
        return struct.pack(f"<{len(colors)}H", *colors)
    return bytes(colors)


def prepare_background_for_target(image: Image.Image,
                                  target: str = "sms") -> Image.Image:
    """Place a source-derived screen in the target's Mode-4 virtual surface."""
    if image.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        raise ValueError(
            f"background must be {SCREEN_WIDTH}x{SCREEN_HEIGHT}, got {image.size}"
        )
    image = image.convert("RGB")
    if target == "sms":
        return image
    _component_bits(target)
    lcd = image.resize((GG_LCD_WIDTH, GG_LCD_HEIGHT), Image.Resampling.NEAREST)
    surface = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
    surface.paste(lcd, (GG_VIEW_X, GG_VIEW_Y))
    return surface


def _text_pixel_visible(pixel: Sequence[int]) -> bool:
    return tuple(pixel[:3]) != TEXT_TRANSPARENT and (
        len(pixel) < 4 or int(pixel[3]) != 0
    )


def _text_mask_pixels(image: Image.Image) -> list[bool]:
    return [_text_pixel_visible(pixel)
            for pixel in image.convert("RGBA").getdata()]


def _reflow_gg_text(text_overlay: Image.Image) -> Image.Image:
    """Reflow ROM-rendered 8x8 English glyph cells without scaling them."""
    if text_overlay.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        raise ValueError("text overlay must be 256x224")
    source = text_overlay.convert("RGB")
    blank = Image.new("RGB", (8, 8), TEXT_TRANSPARENT)
    source_lines: list[list[Image.Image]] = []
    for tile_y in range(MAP_HEIGHT):
        cells = [source.crop((tile_x * 8, tile_y * 8,
                              tile_x * 8 + 8, tile_y * 8 + 8))
                 for tile_x in range(MAP_WIDTH)]
        occupied = [any(_text_pixel_visible(pixel)
                        for pixel in cell.getdata())
                    for cell in cells]
        if not any(occupied):
            continue
        first = occupied.index(True)
        last = len(occupied) - list(reversed(occupied)).index(True)
        source_lines.append(cells[first:last])

    words: list[list[Image.Image]] = []
    for line in source_lines:
        word: list[Image.Image] = []
        for cell in line:
            if any(_text_pixel_visible(pixel) for pixel in cell.getdata()):
                word.append(cell)
            elif word:
                words.append(word)
                word = []
        if word:
            words.append(word)

    output_lines: list[list[Image.Image]] = []
    current: list[Image.Image] = []
    for word in words:
        while len(word) > GG_TEXT_COLUMNS:
            if current:
                output_lines.append(current)
                current = []
            output_lines.append(word[:GG_TEXT_COLUMNS])
            word = word[GG_TEXT_COLUMNS:]
        needed = len(word) + (1 if current else 0)
        if current and len(current) + needed > GG_TEXT_COLUMNS:
            output_lines.append(current)
            current = []
        if current:
            current.append(blank)
        current.extend(word)
    if current:
        output_lines.append(current)

    result = Image.new("RGB", (GG_LCD_WIDTH, len(output_lines) * 8),
                       TEXT_TRANSPARENT)
    for row, cells in enumerate(output_lines):
        for column, cell in enumerate(cells):
            result.paste(cell, (column * 8, row * 8))
    return result


def _paste_text_overlay(destination: Image.Image, overlay: Image.Image,
                        xy: tuple[int, int]) -> None:
    mask = Image.new("L", overlay.size)
    mask.putdata([255 if value else 0 for value in _text_mask_pixels(overlay)])
    destination.paste(overlay.convert("RGB"), xy, mask)


def _embed_gg_lcd(lcd: Image.Image) -> Image.Image:
    if lcd.size != (GG_LCD_WIDTH, GG_LCD_HEIGHT):
        raise ValueError("Game Gear LCD image must be 160x144")
    surface = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
    surface.paste(lcd, (GG_VIEW_X, GG_VIEW_Y))
    return surface


def _embed_gg_mask(lcd_mask: Image.Image) -> list[bool]:
    surface = Image.new("1", (SCREEN_WIDTH, SCREEN_HEIGHT))
    surface.paste(lcd_mask.convert("1"), (GG_VIEW_X, GG_VIEW_Y))
    return [bool(value) for value in surface.getdata()]


def prepare_static_screen_for_target(
    name: str,
    image: Image.Image,
    target: str = "sms",
    text_overlay: Image.Image | None = None,
    photo_layer: Image.Image | None = None,
) -> tuple[Image.Image, list[bool] | None]:
    """Adapt one extracted screen and keep active GG text pixel-native."""
    if image.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        raise ValueError("static screen must be 256x224")
    if target == "sms":
        mask = (_text_mask_pixels(text_overlay)
                if text_overlay is not None else None)
        return image.convert("RGB"), mask
    _component_bits(target)

    if name == "intro1":
        # The title lettering is baked into BG2 rather than the text layer.
        # Its complete 160-pixel source window fits the LCD at native size.
        source = image.convert("RGB")
        lcd = Image.new("RGB", (GG_LCD_WIDTH, GG_LCD_HEIGHT), (0, 0, 0))
        header = source.crop((GG_VIEW_X, 0,
                              GG_VIEW_X + GG_LCD_WIDTH, 72))
        portraits = ImageOps.fit(source.crop((0, 72, SCREEN_WIDTH,
                                              SCREEN_HEIGHT)),
                                 (GG_LCD_WIDTH, 72),
                                 method=Image.Resampling.NEAREST,
                                 centering=(0.5, 0.5))
        lcd.paste(header, (0, 0))
        lcd.paste(portraits, (0, 72))
        title_mask = Image.new("1", lcd.size)
        title_mask.putdata([
            y < 72 and lcd.getpixel((x, y)) != (0, 0, 0)
            for y in range(GG_LCD_HEIGHT) for x in range(GG_LCD_WIDTH)
        ])
        return _embed_gg_lcd(lcd), _embed_gg_mask(title_mask)

    if re.fullmatch(r"intro[2-5]_l2", name):
        if text_overlay is None or photo_layer is None:
            raise ValueError(f"{name} needs extracted photo and text layers")
        text = _reflow_gg_text(text_overlay)
        if text.height > GG_LCD_HEIGHT:
            raise ValueError(f"{name} text exceeds the Game Gear LCD")
        photo_height = GG_LCD_HEIGHT - text.height
        photo = ImageOps.fit(photo_layer.convert("RGB").crop(
            (0, 0, SCREEN_WIDTH, 168)),
            (GG_LCD_WIDTH, photo_height),
            method=Image.Resampling.NEAREST,
            centering=(0.5, 0.5))
        lcd = Image.new("RGB", (GG_LCD_WIDTH, GG_LCD_HEIGHT), (0, 0, 0))
        lcd.paste(photo, (0, 0))
        _paste_text_overlay(lcd, text, (0, photo_height))
        lcd_mask = Image.new("1", lcd.size)
        text_mask = Image.new("1", text.size)
        text_mask.putdata(_text_mask_pixels(text))
        lcd_mask.paste(text_mask, (0, photo_height))
        return _embed_gg_lcd(lcd), _embed_gg_mask(lcd_mask)

    surface = prepare_background_for_target(image, target)
    if text_overlay is None:
        return surface, None
    visible = Image.new("1", text_overlay.size)
    visible.putdata(_text_mask_pixels(text_overlay))
    lcd_mask = visible.resize((GG_LCD_WIDTH, GG_LCD_HEIGHT),
                              Image.Resampling.NEAREST)
    return surface, _embed_gg_mask(lcd_mask)


def encode_mode4_tile(pixels: Sequence[int]) -> bytes:
    """Encode 64 row-major palette indices as one 32-byte Mode-4 pattern."""
    if len(pixels) != 64:
        raise ValueError(f"a Mode-4 tile needs 64 pixels, got {len(pixels)}")
    out = bytearray()
    for y in range(8):
        row = pixels[y * 8:(y + 1) * 8]
        if any(not 0 <= int(p) <= 15 for p in row):
            raise ValueError("Mode-4 palette indices must be in 0..15")
        for plane in range(4):
            value = 0
            for x, pixel in enumerate(row):
                value |= ((int(pixel) >> plane) & 1) << (7 - x)
            out.append(value)
    return bytes(out)


def _flip_tile(tile: bytes, hflip: bool, vflip: bool) -> bytes:
    rows = [tile[y * 8:(y + 1) * 8] for y in range(8)]
    if vflip:
        rows.reverse()
    if hflip:
        rows = [row[::-1] for row in rows]
    return b"".join(rows)


def canonicalize_tile(tile: bytes) -> tuple[bytes, int]:
    """Return the lexicographically canonical H/V orientation and map flags."""
    if len(tile) != 64:
        raise ValueError("tile must contain 64 indexed pixels")
    candidates = (
        (tile, 0),
        (_flip_tile(tile, True, False), HFLIP_BIT),
        (_flip_tile(tile, False, True), VFLIP_BIT),
        (_flip_tile(tile, True, True), HFLIP_BIT | VFLIP_BIT),
    )
    return min(candidates, key=lambda item: (item[0], item[1]))


def _nearest_palette_index(rgb: tuple[int, int, int],
                           palette: Sequence[tuple[int, int, int]]) -> int:
    return min(range(len(palette)), key=lambda i: (
        (rgb[0] - palette[i][0]) ** 2
        + (rgb[1] - palette[i][1]) ** 2
        + (rgb[2] - palette[i][2]) ** 2,
        i,
    ))


def _median_cut_colors(pixels: list[tuple[int, int, int]], count: int,
                       component_bits: int = 2) -> list[tuple[int, int, int]]:
    if count <= 0 or not pixels:
        return []
    unique = sorted(set(pixels))
    if len(unique) <= count:
        return unique
    width = min(2048, len(pixels))
    height = (len(pixels) + width - 1) // width
    padded = pixels + [pixels[-1]] * (width * height - len(pixels))
    sample = Image.new("RGB", (width, height))
    sample.putdata(padded)
    quantized = sample.quantize(
        colors=count,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    raw = quantized.getpalette() or []
    used = sorted(set(quantized.getdata()))
    colors = [tuple(raw[i * 3:i * 3 + 3]) for i in used]
    # Re-project after median-cut averaging so every emitted color is native.
    return list(dict.fromkeys(_hw_rgb(c, component_bits)
                              for c in colors))[:count]


def make_sms_palette(
    image: Image.Image,
    color_count: int,
    protected_mask: Sequence[bool] | None = None,
    fixed_tail: Sequence[tuple[int, int, int]] = (),
    target: str = "sms",
) -> tuple[list[tuple[int, int, int]], bytes, dict[str, object]]:
    """Quantize to native SMS/GG colors, retaining protected colors first."""
    bits = _component_bits(target)
    rgb_pixels = [_hw_rgb(p, bits) for p in image.convert("RGB").getdata()]
    if protected_mask is not None and len(protected_mask) != len(rgb_pixels):
        raise ValueError("protected mask dimensions do not match the image")
    fixed = [_hw_rgb(color, bits) for color in fixed_tail]
    if len(fixed) > color_count:
        raise ValueError("fixed palette colors exceed palette capacity")
    free_count = color_count - len(fixed)
    protected_counts = Counter(
        pixel for pixel, protected in zip(rgb_pixels, protected_mask or [])
        if protected and pixel not in fixed
    )
    ordered_protected = sorted(protected_counts,
                               key=lambda c: (-protected_counts[c], c))
    conflict = len(ordered_protected) > free_count
    palette = ordered_protected[:free_count]
    remaining = free_count - len(palette)
    if remaining:
        candidates = _median_cut_colors(rgb_pixels, remaining, bits)
        palette.extend(c for c in candidates if c not in palette)
    # Median-cut may deduplicate after hardware projection. Fill from exact
    # native colors by frequency before padding the fixed-size CRAM block.
    all_counts = Counter(rgb_pixels)
    for color in sorted(all_counts, key=lambda c: (-all_counts[c], c)):
        if len(palette) >= free_count:
            break
        if color not in palette:
            palette.append(color)
    while len(palette) < free_count:
        palette.append((0, 0, 0))
    palette.extend(fixed)
    indexed = bytes(_nearest_palette_index(p, palette) for p in rgb_pixels)
    return palette, indexed, {
        "protected_color_count": len(ordered_protected),
        "protected_palette_conflict": conflict,
    }


def _tile_distance(tile: bytes, representative: bytes,
                   palette: Sequence[tuple[int, int, int]]) -> int:
    return sum(
        (palette[a][0] - palette[b][0]) ** 2
        + (palette[a][1] - palette[b][1]) ** 2
        + (palette[a][2] - palette[b][2]) ** 2
        for a, b in zip(tile, representative)
    )


@dataclass
class BackgroundResult:
    palette: list[tuple[int, int, int]]
    tiles: list[bytes]
    tilemap: list[int]
    report: dict[str, object]
    flash_palette: list[tuple[int, int, int]] | None = None
    target: str = "sms"

    @property
    def cram(self) -> bytes:
        return encode_cram_palette(self.palette, self.target)

    @property
    def tile_bytes(self) -> bytes:
        return b"".join(encode_mode4_tile(tile) for tile in self.tiles)

    @property
    def tilemap_bytes(self) -> bytes:
        return struct.pack(f"<{len(self.tilemap)}H", *self.tilemap)


def build_background(
    image: Image.Image,
    budget: int,
    protected_mask: Sequence[bool] | None = None,
    fixed_palette_tail: Sequence[tuple[int, int, int]] = (),
    palette_subtract: tuple[int, int, int] | None = None,
    target: str = "sms",
) -> BackgroundResult:
    """Convert one 256x224 image, clustering patterns when over budget."""
    if image.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        raise ValueError(
            f"background must be {SCREEN_WIDTH}x{SCREEN_HEIGHT}, got {image.size}"
        )
    if not 1 <= budget <= 512:
        raise ValueError("background tile budget must be in 1..512")
    bits = _component_bits(target)
    raw_palette, indexed, palette_report = make_sms_palette(
        image, 16, protected_mask, fixed_palette_tail, target
    )
    flash_palette = None
    if palette_subtract is None:
        palette = raw_palette
    else:
        flash_palette = raw_palette
        fixed_start = 16 - len(fixed_palette_tail)
        palette = [
            color if index >= fixed_start else _hw_rgb(tuple(
                max(0, color[channel] - palette_subtract[channel])
                for channel in range(3)
            ), bits)
            for index, color in enumerate(raw_palette)
        ]
    records: list[tuple[bytes, int, bool]] = []
    stats: dict[bytes, list[int | bool]] = {}
    for ty in range(MAP_HEIGHT):
        for tx in range(MAP_WIDTH):
            raw = b"".join(
                indexed[(ty * 8 + y) * SCREEN_WIDTH + tx * 8:
                        (ty * 8 + y) * SCREEN_WIDTH + tx * 8 + 8]
                for y in range(8)
            )
            canonical, flags = canonicalize_tile(raw)
            protected = False
            if protected_mask is not None:
                protected = any(
                    protected_mask[(ty * 8 + y) * SCREEN_WIDTH + tx * 8 + x]
                    for y in range(8) for x in range(8)
                )
            records.append((canonical, flags, protected))
            entry = stats.setdefault(canonical, [0, False])
            entry[0] = int(entry[0]) + 1
            entry[1] = bool(entry[1]) or protected

    unique = sorted(stats)
    protected_unique = [tile for tile in unique if bool(stats[tile][1])]
    conflict = len(protected_unique) > budget
    if len(unique) <= budget:
        representatives = unique
    else:
        key = lambda tile: (-int(stats[tile][0]), tile)
        representatives = sorted(protected_unique, key=key)[:budget]
        if not conflict:
            remaining = sorted((t for t in unique if t not in set(representatives)),
                               key=key)
            representatives.extend(remaining[:budget - len(representatives)])
        # Tile zero is useful for clearing and deterministic at slot zero when
        # it survived selection. Other representatives retain selection order.
    blank = bytes(64)
    if blank in representatives:
        representatives.remove(blank)
        representatives.insert(0, blank)

    rep_index = {tile: i for i, tile in enumerate(representatives)}
    mappings: dict[bytes, tuple[int, int, int]] = {}
    for tile in unique:
        if tile in rep_index:
            mappings[tile] = (rep_index[tile], 0, 0)
            continue
        best: tuple[int, int, int] | None = None
        for index, representative in enumerate(representatives):
            for extra_flags, h, v in ((0, False, False),
                                      (HFLIP_BIT, True, False),
                                      (VFLIP_BIT, False, True),
                                      (HFLIP_BIT | VFLIP_BIT, True, True)):
                candidate = _flip_tile(representative, h, v)
                trial = (_tile_distance(tile, candidate, palette), index,
                         extra_flags)
                if best is None or trial < best:
                    best = trial
        assert best is not None
        mappings[tile] = (best[1], best[2], best[0])

    tilemap: list[int] = []
    squared_error = 0
    approximated = 0
    protected_approximated = 0
    for tile, source_flags, protected in records:
        index, extra_flags, error = mappings[tile]
        tilemap.append(index | (source_flags ^ extra_flags))
        squared_error += error
        if error:
            approximated += 1
            if protected:
                protected_approximated += 1

    report: dict[str, object] = {
        **palette_report,
        "budget": budget,
        "source_unique_patterns": len(unique),
        "emitted_patterns": len(representatives),
        "protected_unique_patterns": len(protected_unique),
        "protected_tile_budget_conflict": conflict,
        "protected_approximated_cells": protected_approximated,
        "approximated_cells": approximated,
        "palette_distance_squared": squared_error,
    }
    return BackgroundResult(palette, representatives, tilemap, report,
                            flash_palette, target)


def _sanitize(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return value or "UNNAMED"


def _write_background(output: Path, name: str, result: BackgroundResult,
                      gameplay: bool) -> dict[str, object]:
    bg_dir = output / "bg"
    bg_dir.mkdir(parents=True, exist_ok=True)
    stem = bg_dir / name
    cram = result.cram
    tiles = result.tile_bytes
    tilemap = result.tilemap_bytes
    flags = (1 if gameplay else 0) | (
        2 if result.report["protected_tile_budget_conflict"] else 0
    )
    tiles_offset = BG_BUNDLE_HEADER.size + len(cram)
    tilemap_offset = tiles_offset + len(tiles)
    header = BG_BUNDLE_HEADER.pack(
        BG_BUNDLE_MAGIC, BG_BUNDLE_VERSION, MAP_WIDTH, MAP_HEIGHT, flags,
        len(result.tiles), len(cram), tiles_offset, tilemap_offset,
    )
    bundle = header + cram + tiles + tilemap
    if len(bundle) >= BANK_SIZE:
        raise ValueError(f"{name} bundle is {len(bundle)} bytes (must be <16 KiB)")
    (stem.with_suffix(".cram")).write_bytes(cram)
    (stem.with_suffix(".tiles")).write_bytes(tiles)
    (stem.with_suffix(".tilemap")).write_bytes(tilemap)
    (stem.with_suffix(".bin")).write_bytes(bundle)
    entry: dict[str, object] = {
        "name": name,
        "kind": "gameplay" if gameplay else "static",
        "bundle": f"bg/{name}.bin",
        "bundle_size": len(bundle),
        "bundle_header_size": BG_BUNDLE_HEADER.size,
        "cram": f"bg/{name}.cram",
        "tiles": f"bg/{name}.tiles",
        "tilemap": f"bg/{name}.tilemap",
        "tile_count": len(result.tiles),
        "report": result.report,
    }
    if result.flash_palette is not None:
        flash = encode_cram_palette(result.flash_palette, result.target)
        flash_path = bg_dir / f"{name}_flash.cram"
        flash_path.write_bytes(flash)
        entry["flash_cram"] = f"bg/{name}_flash.cram"
        entry["flash_cram_size"] = len(flash)
        entry["flash_index_correspondence"] = "1:1 with normal CRAM"
    return entry


def _metadata_origin(frame_meta: dict[str, object] | None,
                     width: int, height: int) -> tuple[int, int]:
    if frame_meta:
        sprites = frame_meta.get("sprites")
        if isinstance(sprites, list) and sprites:
            xs: list[int] = []
            ys: list[int] = []
            for sprite in sprites:
                if isinstance(sprite, list) and len(sprite) >= 4:
                    xs.append(int(sprite[0]))
                    ys.append(int(sprite[1]))
            if xs and ys:
                return min(xs), min(ys)
    return -(width // 2), -(height // 2)


@dataclass
class DigitBuild:
    tiles: list[bytes]
    colors: list[tuple[int, int, int]]
    source_pattern_indices: list[list[int]]
    source_color_map: dict[int, int]


def build_digit_tiles(
    source_tiles: Sequence[bytes],
    source_palette: Sequence[tuple[int, int, int]],
) -> DigitBuild:
    """Remap 10x4 exact source patterns to BG index 0 plus indices 14/15.

    SNES palette index zero is the score-cell background.  The three opaque
    source colors are reduced, palette-aware, to the two colors reserved in
    every gameplay CRAM palette.  No source pattern is inferred or redrawn.
    """
    if len(source_tiles) != DIGIT_TILE_RESERVE:
        raise ValueError(f"digits require exactly {DIGIT_TILE_RESERVE} tiles")
    if any(len(tile) != 64 for tile in source_tiles):
        raise ValueError("each source digit tile must contain 64 indices")
    used = Counter(pixel for tile in source_tiles for pixel in tile if pixel)
    if not used:
        raise ValueError("source digits contain no visible pixels")
    if max(used) >= len(source_palette):
        raise ValueError("source digit palette index is out of range")
    weighted = [_hw_rgb(source_palette[index])
                for index, count in sorted(used.items()) for _ in range(count)]
    colors = _median_cut_colors(weighted, 2)
    for color in sorted(set(weighted)):
        if len(colors) >= 2:
            break
        if color not in colors:
            colors.append(color)
    while len(colors) < 2:
        colors.append(colors[0])
    color_map = {
        source_index: DIGIT_COLOR_INDICES[
            _nearest_palette_index(_hw_rgb(source_palette[source_index]), colors)
        ]
        for source_index in used
    }
    remapped = [bytes(0 if pixel == 0 else color_map[pixel] for pixel in tile)
                for tile in source_tiles]
    return DigitBuild(remapped, colors, [], color_map)


def extract_source_digits(root: Path) -> DigitBuild:
    """Read the measured $80:B601 table and its exact source patterns.

    The ROM is an offline, user-supplied conversion input.  Only the selected
    40 remapped patterns are emitted; no ROM bytes or executable program are
    copied into the target artifact.
    """
    tools_dir = root / "tools"
    sys.path.insert(0, str(tools_dir))
    try:
        from hk97 import (bgr555_palette, decompress, load_rom, lorom,
                          snes_tile_4bpp)
    finally:
        if sys.path and sys.path[0] == str(tools_dir):
            sys.path.pop(0)
    rom = load_rom()
    source_pattern_data = decompress(rom, 0x848600)
    source_palette = bgr555_palette(decompress(rom, 0x84A725))[5 * 16:6 * 16]
    patterns: list[bytes] = []
    pattern_indices: list[list[int]] = []
    table = lorom(0x80B601)
    for digit in range(10):
        indices = []
        for position in range(4):  # measured order: TL, TR, BL, BR
            offset = table + digit * 8 + position * 2
            entry = rom[offset] | (rom[offset + 1] << 8)
            index = entry & 0x03FF
            indices.append(index)
            pixels = snes_tile_4bpp(source_pattern_data, index * 32)
            patterns.append(bytes(pixel for row in pixels for pixel in row))
        pattern_indices.append(indices)
    build = build_digit_tiles(patterns, source_palette)
    build.source_pattern_indices = pattern_indices
    return build


def _write_digits(output: Path, build: DigitBuild) -> dict[str, object]:
    data = b"".join(encode_mode4_tile(tile) for tile in build.tiles)
    (output / "digits.tiles").write_bytes(data)
    return {
        "tiles": "digits.tiles",
        "tile_count": len(build.tiles),
        "byte_count": len(data),
        "vram_base": DIGIT_TILE_BASE,
        "vram_last": DIGIT_TILE_BASE + len(build.tiles) - 1,
        "reserved_palette_indices": list(DIGIT_COLOR_INDICES),
        "reserved_cram": [pack_cram_color(color) for color in build.colors],
        "reserved_rgb": [list(color) for color in build.colors],
        "source_table": "$80:B601",
        "source_order": "digit 0..9, TL,TR,BL,BR",
        "source_pattern_indices": build.source_pattern_indices,
        "source_color_map": {str(k): v for k, v in build.source_color_map.items()},
    }


def _sprite_palette(images: Iterable[Image.Image],
                    target: str = "sms") -> list[tuple[int, int, int]]:
    bits = _component_bits(target)
    pixels: list[tuple[int, int, int]] = []
    for image in images:
        pixels.extend(_hw_rgb((r, g, b), bits) for r, g, b, a
                      in image.convert("RGBA").getdata() if a)
    opaque = _median_cut_colors(pixels, 15, bits)
    counts = Counter(pixels)
    for color in sorted(counts, key=lambda c: (-counts[c], c)):
        if len(opaque) >= 15:
            break
        if color not in opaque:
            opaque.append(color)
    while len(opaque) < 15:
        opaque.append((0, 0, 0))
    return [(0, 0, 0)] + opaque[:15]


@dataclass
class SpriteBuild:
    palette: list[tuple[int, int, int]]
    tiles: list[bytes]
    parts: list[tuple[int, int, int]]
    frames: list[dict[str, int]]
    anim_first: list[int]
    anim_count: list[int]
    cache_seed: list[int]
    report: dict[str, int]


def _sprite_tile_distance(tile: bytes, representative: bytes,
                          palette: Sequence[tuple[int, int, int]]) -> int:
    distance = 0
    for a, b in zip(tile, representative):
        if (a == 0) != (b == 0):
            distance += 1_000_000  # transparency is more important than hue
        elif a:
            distance += ((palette[a][0] - palette[b][0]) ** 2
                         + (palette[a][1] - palette[b][1]) ** 2
                         + (palette[a][2] - palette[b][2]) ** 2)
    return distance


def build_sprite_assets(
    frames_by_anim: dict[int, list[tuple[Image.Image, int,
                                         dict[str, object] | None]]],
    target: str = "sms",
) -> SpriteBuild:
    """Convert animation images to one palette/tile set and metasprites."""
    prepared: dict[int, list[tuple[Image.Image, int,
                                  dict[str, object] | None, float, float]]] = {}
    for anim in sorted(frames_by_anim):
        prepared[anim] = []
        for image, duration, meta in frames_by_anim[anim]:
            rgba = image.convert("RGBA")
            scale_x = scale_y = 1.0
            if target == "gg":
                scale_x = GG_LCD_WIDTH / SCREEN_WIDTH
                scale_y = GG_LCD_HEIGHT / SCREEN_HEIGHT
                width = max(1, round(rgba.width * scale_x))
                height = max(1, round(rgba.height * scale_y))
                rgba = rgba.resize((width, height), Image.Resampling.NEAREST)
            elif target == "sms" and anim == 0x01 and rgba.width > 64:
                scale_x = scale_y = 64 / rgba.width
                height = max(1, round(rgba.height * scale_y))
                rgba = rgba.resize((64, height), Image.Resampling.NEAREST)
            else:
                _component_bits(target)
            prepared[anim].append((rgba, max(1, min(255, int(duration))),
                                   meta, scale_x, scale_y))
    palette = _sprite_palette(
        (frame[0] for frames in prepared.values() for frame in frames), target
    )
    tiles: list[bytes] = []
    tile_index: dict[bytes, int] = {}
    parts: list[tuple[int, int, int]] = []
    frame_out: list[dict[str, int]] = []
    max_anim = max([0x10, *prepared.keys()])
    anim_first = [0] * (max_anim + 1)
    anim_count = [0] * (max_anim + 1)

    for anim in sorted(prepared):
        anim_first[anim] = len(frame_out)
        anim_count[anim] = len(prepared[anim])
        for frame_index, (image, duration, meta, scale_x,
                          scale_y) in enumerate(prepared[anim]):
            rgba = list(image.getdata())
            indexed = bytearray()
            for r, g, b, a in rgba:
                indexed.append(0 if a == 0 else _nearest_palette_index(
                    _hw_rgb((r, g, b), _component_bits(target)), palette[1:]) + 1)
            source_width = max(1, round(image.width / scale_x))
            source_height = max(1, round(image.height / scale_y))
            origin_x, origin_y = _metadata_origin(meta, source_width,
                                                  source_height)
            origin_x = round(origin_x * scale_x)
            origin_y = round(origin_y * scale_y)
            first_part = len(parts)
            for ty in range((image.height + 15) // 16):
                for tx in range((image.width + 7) // 8):
                    tile = bytearray(128)
                    opaque = False
                    for y in range(16):
                        py = ty * 16 + y
                        if py >= image.height:
                            continue
                        for x in range(8):
                            px = tx * 8 + x
                            if px >= image.width:
                                continue
                            value = indexed[py * image.width + px]
                            tile[y * 8 + x] = value
                            opaque |= value != 0
                    if not opaque:
                        continue
                    raw = bytes(tile)
                    if raw not in tile_index:
                        tile_index[raw] = len(tiles)
                        tiles.append(raw)
                    dx = origin_x + tx * 8
                    dy = origin_y + ty * 16
                    if not -128 <= dx <= 127 or not -128 <= dy <= 127:
                        raise ValueError(f"animation {anim:02X} frame {frame_index} "
                                         "has an offset outside int8")
                    parts.append((dx, dy, tile_index[raw]))

            frame_parts = parts[first_part:]
            scanlines: Counter[int] = Counter()
            for _, dy, _ in frame_parts:
                for y in range(dy, dy + 16):
                    scanlines[y] += 1
            max_scanline = max(scanlines.values(), default=0)
            if max_scanline > 8:
                raise ValueError(
                    f"animation {anim:02X} frame {frame_index} uses "
                    f"{max_scanline} sprites on one scanline (SMS limit 8)"
                )
            if len(frame_parts) > 64:
                raise ValueError(
                    f"animation {anim:02X} frame {frame_index} uses "
                    f"{len(frame_parts)} sprites (SMS limit 64)"
                )
            frame_out.append({
                "anim_id": anim,
                "frame_index": frame_index,
                "duration": duration,
                "part_count": len(frame_parts),
                "first_part": first_part,
                "origin_x": origin_x,
                "origin_y": origin_y,
                "width": image.width,
                "height": image.height,
                "max_scanline": max_scanline,
            })
    source_tile_count = len(tiles)
    counts = Counter(tile for _dx, _dy, tile in parts)
    sprite_tile_budget = (GG_SPRITE_TILE_BUDGET if target == "gg"
                          else SPRITE_TILE_BUDGET)
    cache_seed = sorted(
        range(source_tile_count),
        key=lambda index: (-counts[index], tiles[index]),
    )[:sprite_tile_budget]
    report = {
        "budget": sprite_tile_budget,
        "source_unique_patterns": source_tile_count,
        "rom_patterns": len(tiles),
        "cache_seed_patterns": len(cache_seed),
        "approximated_parts": 0,
    }
    return SpriteBuild(palette, tiles, parts, frame_out, anim_first, anim_count,
                       cache_seed, report)


def _load_animation_frames(gfx: Path, metadata_path: Path) -> dict[
        int, list[tuple[Image.Image, int, dict[str, object] | None]]]:
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    meta_anims = data.get("shared", {}).get("anims", {})
    result: dict[int, list[tuple[Image.Image, int, dict[str, object] | None]]] = {}
    anim_dir = gfx / "anim"
    for anim in USED_ANIMS:
        frames_meta = meta_anims.get(str(anim), [])
        paths = sorted(anim_dir.glob(f"a{anim:02X}_f*.png"), key=lambda p: int(
            re.search(r"_f(\d+)$", p.stem).group(1)  # type: ignore[union-attr]
        ))
        if not paths:
            raise FileNotFoundError(f"missing used animation {anim:02X} in {anim_dir}")
        entries = []
        for index, path in enumerate(paths):
            meta = frames_meta[index] if index < len(frames_meta) else None
            duration = int(meta.get("dur", 1)) if isinstance(meta, dict) else 1
            entries.append((Image.open(path).convert("RGBA"), duration, meta))
        result[anim] = entries
    return result


def _write_sprite_assets(output: Path, build: SpriteBuild,
                         target: str = "sms") -> dict[str, object]:
    cram = encode_cram_palette(build.palette, target)
    def encode_pair(pair: bytes) -> bytes:
        return encode_mode4_tile(pair[:64]) + encode_mode4_tile(pair[64:])

    tile_bytes = b"".join(encode_pair(tile) for tile in build.tiles)
    seed_bytes = b"".join(encode_pair(build.tiles[index])
                          for index in build.cache_seed)
    (output / "sprites.cram").write_bytes(cram)
    split = 128 * 64
    (output / "sprites0.tiles").write_bytes(tile_bytes[:split])
    (output / "sprites1.tiles").write_bytes(tile_bytes[split:])
    (output / "sprites_seed.tiles").write_bytes(seed_bytes)
    return {
        "cram": "sprites.cram",
        "tiles": ["sprites0.tiles", "sprites1.tiles"],
        "tile_bank_split": 128,
        "seed_tiles": "sprites_seed.tiles",
        "tile_count": len(build.tiles),
        "cache_seed_count": len(build.cache_seed),
        "palette_colors": len(build.palette),
        "sprite_height": 16,
        "frames": build.frames,
        "parts": [dict(dx=dx, dy=dy, tile=tile) for dx, dy, tile in build.parts],
        "anim_first_frame": build.anim_first,
        "anim_frame_count": build.anim_count,
        "report": build.report,
        "max_sprites_per_scanline": max(
            (frame["max_scanline"] for frame in build.frames), default=0
        ),
    }


def _read_wav_mono(path: Path) -> tuple[list[int], int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.getnframes()
        compression = wav.getcomptype()
        raw = wav.readframes(frames)
    if compression != "NONE" or width not in (1, 2, 3, 4):
        raise ValueError("music WAV must be uncompressed 8/16/24/32-bit PCM")
    samples: list[int] = []
    offset = 0
    for _ in range(frames):
        channel_values = []
        for _channel in range(channels):
            chunk = raw[offset:offset + width]
            offset += width
            if width == 1:
                value = (chunk[0] - 128) << 8
            else:
                value = int.from_bytes(chunk, "little", signed=True)
                value >>= (width * 8 - 16)
            channel_values.append(value)
        samples.append(sum(channel_values) // channels)
    return samples, rate


def resample_pcm(samples: Sequence[int], source_rate: int,
                 target_rate: int) -> list[int]:
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample rates must be positive")
    if not samples:
        return []
    count = max(1, (len(samples) * target_rate + source_rate // 2) // source_rate)
    result: list[int] = []
    for out_index in range(count):
        numerator = out_index * source_rate
        left = numerator // target_rate
        fraction = numerator % target_rate
        if left >= len(samples) - 1:
            result.append(int(samples[-1]))
        else:
            a, b = int(samples[left]), int(samples[left + 1])
            result.append((a * (target_rate - fraction) + b * fraction
                           + target_rate // 2) // target_rate)
    return result


def pack_pcm4(samples: Sequence[int]) -> bytes:
    nibbles = [max(0, min(15, ((int(sample) + 32768) * 15 + 32767) // 65535))
               for sample in samples]
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        high = nibbles[i]
        low = nibbles[i + 1] if i + 1 < len(nibbles) else 8
        out.append((high << 4) | low)
    return bytes(out)


def convert_music(path: Path, output: Path, target_rate: int,
                  filename: str = "music.pcm4") -> dict[str, object]:
    samples, source_rate = _read_wav_mono(path)
    resampled = resample_pcm(samples, source_rate, target_rate)
    packed = pack_pcm4(resampled)
    (output / filename).write_bytes(packed)
    return {
        "file": filename,
        "encoding": "unsigned-pcm4",
        "nibble_order": "even-high-odd-low",
        "sample_rate": target_rate,
        "sample_count": len(resampled),
        "byte_count": len(packed),
        "source_rate": source_rate,
        "source_sample_count": len(samples),
        "duration_seconds": len(resampled) / target_rate,
    }


def _write_header(output: Path, backgrounds: list[dict[str, object]],
                  sprites: SpriteBuild, target: str = "sms") -> None:
    sprite_tile_budget = (GG_SPRITE_TILE_BUDGET if target == "gg"
                          else SPRITE_TILE_BUDGET)
    lines = [
        "/* Generated by tools/generate_sms_assets.py. Do not edit. */",
        "#ifndef HK97_SMS_ASSETS_H",
        "#define HK97_SMS_ASSETS_H",
        "#include <stdint.h>",
        "",
        "#define SMS_BG_BUNDLE_MAGIC 0x47423453UL /* S4BG little-endian */",
        "#define SMS_BG_BUNDLE_VERSION 1",
        "#define SMS_BG_BUNDLE_HEADER_SIZE 16",
        "#define SMS_BG_CRAM_OFFSET 16",
        "#define SMS_BG_WIDTH_TILES 32",
        "#define SMS_BG_HEIGHT_TILES 28",
        f"#define SMS_BG_PALETTE_BYTES {32 if target == 'gg' else 16}",
        f"#define SMS_GAME_BG_TILE_BUDGET {GAME_TILE_BUDGET}",
        f"#define SMS_SPRITE_CACHE_SIZE {sprite_tile_budget}",
        "",
        "typedef struct {",
        "    uint8_t magic[4], version, width_tiles, height_tiles, flags;",
        "    uint16_t tile_count, palette_bytes, tiles_offset, tilemap_offset;",
        "} SmsBgBundleHeader; /* 16 bytes with the SMS Z80 ABI */",
        "",
        "typedef struct {",
        "    int8_t dx, dy;",
        "    uint16_t tile; /* source-pattern index in sprites.tiles */",
        "} SmsSpritePart;",
        "",
        "typedef struct {",
        "    uint8_t anim_id, frame_index, duration, part_count;",
        "    uint16_t first_part;",
        "    int8_t origin_x, origin_y;",
        "    uint8_t width, height, max_scanline;",
        "} SmsSpriteFrame;",
        "",
    ]
    for bg in backgrounds:
        macro = _sanitize(str(bg["name"]))
        lines.extend([
            f"#define SMS_BG_{macro}_TILE_COUNT {bg['tile_count']}",
            f"#define SMS_BG_{macro}_BUNDLE_SIZE {bg['bundle_size']}",
        ])
    lines.extend(["", "static const SmsSpritePart sms_sprite_parts[] = {"])
    lines.extend(f"    {{ {dx}, {dy}, {tile} }},"
                 for dx, dy, tile in sprites.parts)
    lines.append("};")
    lines.extend(["", "static const SmsSpriteFrame sms_sprite_frames[] = {"])
    for frame in sprites.frames:
        lines.append(
            "    { %(anim_id)d, %(frame_index)d, %(duration)d, %(part_count)d, "
            "%(first_part)d, %(origin_x)d, %(origin_y)d, %(width)d, %(height)d, "
            "%(max_scanline)d }," % frame
        )
    lines.extend([
        "};", "",
        f"static const uint16_t sms_sprite_cache_seed[{len(sprites.cache_seed)}] = {{",
        "    " + ", ".join(str(v) for v in sprites.cache_seed),
        "};", "",
        "static const uint8_t sms_anim_first_frame[17] = {",
        "    " + ", ".join(str(v) for v in sprites.anim_first[:17]),
        "};",
        "static const uint8_t sms_anim_frame_count[17] = {",
        "    " + ", ".join(str(v) for v in sprites.anim_count[:17]),
        "};", "", "#endif", "",
    ])
    (output / "sms_assets.h").write_text("\n".join(lines), encoding="utf-8")
def _gameplay_backgrounds(gfx: Path) -> dict[int, Image.Image]:
    backgrounds: dict[int, Image.Image] = {}
    for index in range(6):
        path = gfx / f"gamebg{index}.png"
        if not path.exists():
            raise FileNotFoundError(f"missing gameplay background {path}")
        backgrounds[index] = Image.open(path).convert("RGB")
    return backgrounds


def generate(root: Path, output: Path, target: str = "sms") -> dict[str, object]:
    _component_bits(target)
    gfx = root / "res" / "gfx"
    screens = gfx / "screens"
    anim_meta = root / "docs" / "anims.json"
    if output.exists() and not output.is_dir():
        raise ValueError(f"output exists and is not a directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    background_entries: list[dict[str, object]] = []
    removed_screens = {"game_hud_bg0", "gameover2", "gameover3"}
    static_paths = sorted(p for p in screens.glob("*.png")
                          if p.stem not in removed_screens)
    if not static_paths:
        raise FileNotFoundError(f"no composite screens found in {screens}")
    for path in static_paths:
        layer_dir = screens / "layers"
        text_path = layer_dir / f"{path.stem}_text.png"
        photo_path = layer_dir / f"{path.stem}_photo.png"
        text = Image.open(text_path) if text_path.exists() else None
        photo = Image.open(photo_path) if photo_path.exists() else None
        source, mask = prepare_static_screen_for_target(
            path.stem, Image.open(path), target, text, photo
        )
        result = build_background(source, STATIC_TILE_BUDGET, mask,
                                  target=target)
        background_entries.append(_write_background(
            output, path.stem, result, gameplay=False
        ))

    gameplay_images = _gameplay_backgrounds(gfx)
    for index in range(6):
        source = prepare_background_for_target(gameplay_images[index], target)
        result = build_background(source, GAME_TILE_BUDGET,
                                  palette_subtract=GAMEPLAY_SUBTRACT,
                                  target=target)
        background_entries.append(_write_background(
            output, f"gamebg{index}", result, gameplay=True
        ))

    animation_frames = _load_animation_frames(gfx, anim_meta)
    sprite_build = build_sprite_assets(animation_frames, target)
    sprite_manifest = _write_sprite_assets(output, sprite_build, target)
    cheat_audio = convert_music(root / "res" / "music" / "cheat.wav",
                                output, 5753, "cheat.pcm4")
    _write_header(output, background_entries, sprite_build, target)

    manifest: dict[str, object] = {
        "format_version": 1,
        "native_port": True,
        "source_rom_embedded": False,
        "target": target,
        "screen": {"surface_width": SCREEN_WIDTH,
                   "surface_height": SCREEN_HEIGHT,
                   "map_width": MAP_WIDTH, "map_height": MAP_HEIGHT,
                   "lcd_width": GG_LCD_WIDTH if target == "gg" else SCREEN_WIDTH,
                   "lcd_height": GG_LCD_HEIGHT if target == "gg" else SCREEN_HEIGHT,
                   "lcd_x": GG_VIEW_X if target == "gg" else 0,
                   "lcd_y": GG_VIEW_Y if target == "gg" else 0},
        "bundle": {"magic": "S4BG", "header_size": BG_BUNDLE_HEADER.size,
                   "byte_order": "little", "bank_size_limit": BANK_SIZE},
        "palette_component_bits": _component_bits(target),
        "background_palette_count": 1,
        "sprite_palette_count": 1,
        "backgrounds": background_entries,
        "sprites": sprite_manifest,
        "cheat_audio": cheat_audio,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert extracted Hong Kong 97 graphics to SMS/GG Mode 4"
    )
    parser.add_argument("--target", choices=("sms", "gg"), default="sms")
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parent.parent,
                        help="project root (default: parent of tools/)")
    parser.add_argument("--output", type=Path,
                        help="output directory (default: ROOT/generated)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = (args.output or (root / "generated")).resolve()
    try:
        manifest = generate(root, output, args.target)
    except (FileNotFoundError, ValueError, json.JSONDecodeError,
            wave.Error) as exc:
        parser.exit(1, f"error: {exc}\n")
    conflicts = [bg["name"] for bg in manifest["backgrounds"]
                 if bg["report"]["protected_tile_budget_conflict"]]
    print(f"generated {len(manifest['backgrounds'])} backgrounds, "
          f"{manifest['sprites']['tile_count']} sprite patterns in {output}")
    if conflicts:
        print("protected-tile budget conflicts: " + ", ".join(conflicts),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
