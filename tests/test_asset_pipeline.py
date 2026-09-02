#!/usr/bin/env python3
"""Synthetic-only verification for the SMS/Game Gear asset pipeline."""

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_sms_assets", ROOT / "tools" / "generate_sms_assets.py"
)
assert SPEC and SPEC.loader
sms = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sms
SPEC.loader.exec_module(sms)


class Mode4Tests(unittest.TestCase):
    def test_mode4_planar_byte_layout(self) -> None:
        # First row: pixels 1,2,4,8,15,0,0,0. Leftmost is bit 7.
        pixels = [1, 2, 4, 8, 15, 0, 0, 0] + [0] * 56
        encoded = sms.encode_mode4_tile(pixels)
        self.assertEqual(encoded[:4], bytes((0x88, 0x48, 0x28, 0x18)))
        self.assertEqual(encoded[4:], bytes(28))

    def test_cram_bit_packing(self) -> None:
        self.assertEqual(sms.pack_cram_color((255, 0, 0)), 0x03)
        self.assertEqual(sms.pack_cram_color((0, 255, 0)), 0x0C)
        self.assertEqual(sms.pack_cram_color((0, 0, 255)), 0x30)
        self.assertEqual(sms.pack_cram_color((255, 255, 255)), 0x3F)

    def test_game_gear_cram_bit_packing(self) -> None:
        self.assertEqual(sms.pack_cram_color((255, 0, 0), "gg"), 0x00F)
        self.assertEqual(sms.pack_cram_color((0, 255, 0), "gg"), 0x0F0)
        self.assertEqual(sms.pack_cram_color((0, 0, 255), "gg"), 0xF00)
        self.assertEqual(
            sms.encode_cram_palette([(255, 0, 0), (0, 0, 255)], "gg"),
            bytes((0x0F, 0x00, 0x00, 0x0F)),
        )

    def test_game_gear_viewport_is_centered_in_virtual_surface(self) -> None:
        source = Image.new("RGB", (256, 224), (255, 0, 0))
        surface = sms.prepare_background_for_target(source, "gg")
        self.assertEqual(surface.size, (256, 224))
        self.assertEqual(surface.getpixel((47, 24)), (0, 0, 0))
        self.assertEqual(surface.getpixel((48, 24)), (255, 0, 0))
        self.assertEqual(surface.getpixel((207, 167)), (255, 0, 0))
        self.assertEqual(surface.getpixel((208, 167)), (0, 0, 0))

    def test_horizontal_and_vertical_flip_bits(self) -> None:
        image = Image.new("RGB", (256, 224), (0, 0, 0))
        px = image.load()
        tile = [[(255, 0, 0) if x <= y else (0, 255, 0)
                 for x in range(8)] for y in range(8)]
        for y in range(8):
            for x in range(8):
                px[x, y] = tile[y][x]
                px[8 + x, y] = tile[y][7 - x]
                px[x, 8 + y] = tile[7 - y][x]
        result = sms.build_background(image, 32)
        first = result.tilemap[0]
        h = result.tilemap[1]
        v = result.tilemap[32]
        self.assertEqual(first & 0x1FF, h & 0x1FF)
        self.assertEqual(first & 0x1FF, v & 0x1FF)
        self.assertEqual((first ^ h) & sms.HFLIP_BIT, sms.HFLIP_BIT)
        self.assertEqual((first ^ v) & sms.VFLIP_BIT, sms.VFLIP_BIT)


class BackgroundBudgetTests(unittest.TestCase):
    @staticmethod
    def noisy_screen() -> Image.Image:
        image = Image.new("RGB", (256, 224))
        pixels = []
        for y in range(224):
            for x in range(256):
                value = (x * 37 + y * 73 + (x // 8) * (y // 8) * 11) & 63
                pixels.append(((value & 3) * 85,
                               ((value >> 2) & 3) * 85,
                               ((value >> 4) & 3) * 85))
        image.putdata(pixels)
        return image

    def test_clustering_obeys_budget_and_is_deterministic(self) -> None:
        image = self.noisy_screen()
        first = sms.build_background(image, 23)
        second = sms.build_background(image, 23)
        self.assertLessEqual(len(first.tiles), 23)
        self.assertEqual(first.tile_bytes, second.tile_bytes)
        self.assertEqual(first.tilemap_bytes, second.tilemap_bytes)
        self.assertEqual(first.cram, second.cram)
        self.assertGreater(first.report["approximated_cells"], 0)

    def test_protected_budget_conflict_is_reported(self) -> None:
        image = self.noisy_screen()
        mask = [False] * (256 * 224)
        # Protect four deliberately different tile cells but allow one pattern.
        for ty, tx in ((0, 0), (0, 1), (1, 0), (1, 1)):
            for y in range(8):
                for x in range(8):
                    mask[(ty * 8 + y) * 256 + tx * 8 + x] = True
        result = sms.build_background(image, 1, mask)
        self.assertTrue(result.report["protected_tile_budget_conflict"])
        self.assertEqual(len(result.tiles), 1)

    def test_bundle_is_below_one_bank(self) -> None:
        image = self.noisy_screen()
        result = sms.build_background(image, sms.STATIC_TILE_BUDGET)
        with tempfile.TemporaryDirectory() as tmp:
            entry = sms._write_background(Path(tmp), "synthetic", result, False)
            bundle = (Path(tmp) / entry["bundle"]).read_bytes()
            self.assertLess(len(bundle), 16 * 1024)
            values = sms.BG_BUNDLE_HEADER.unpack_from(bundle)
            self.assertEqual(values[0], b"S4BG")
            self.assertEqual(values[2:4], (32, 28))
            self.assertEqual(values[5], len(result.tiles))
            self.assertEqual(values[7], 32)
            self.assertEqual(values[8], 32 + len(result.tiles) * 32)

    def test_game_gear_bundle_uses_32_byte_palette(self) -> None:
        image = sms.prepare_background_for_target(self.noisy_screen(), "gg")
        result = sms.build_background(image, sms.STATIC_TILE_BUDGET,
                                      target="gg")
        with tempfile.TemporaryDirectory() as tmp:
            entry = sms._write_background(Path(tmp), "synthetic", result, False)
            bundle = (Path(tmp) / entry["bundle"]).read_bytes()
            values = sms.BG_BUNDLE_HEADER.unpack_from(bundle)
            self.assertEqual(values[6], 32)
            self.assertEqual(values[7], 48)
            self.assertEqual(len(result.cram), 32)

    def test_gameplay_normal_and_index_matched_flash_palettes_differ(self) -> None:
        image = Image.new("RGB", (256, 224))
        image.putdata([((x % 4) * 85, (y % 4) * 85,
                        ((x // 4 + y // 4) % 4) * 85)
                       for y in range(224) for x in range(256)])
        digits = [(170, 0, 0), (0, 170, 85)]
        result = sms.build_background(
            image, 216, fixed_palette_tail=digits,
            palette_subtract=sms.GAMEPLAY_SUBTRACT,
        )
        self.assertIsNotNone(result.flash_palette)
        self.assertNotEqual(result.cram,
                            bytes(sms.pack_cram_color(c)
                                  for c in result.flash_palette))
        # Reserved digit slots keep the same indices/colors across the blink.
        self.assertEqual(result.palette[14:16], digits)
        self.assertEqual(result.flash_palette[14:16], digits)


class SpriteTests(unittest.TestCase):
    @staticmethod
    def opaque(width: int, height: int) -> Image.Image:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        px = image.load()
        for y in range(height):
            for x in range(width):
                px[x, y] = ((x * 85) & 255, (y * 85) & 255, 170, 255)
        return image

    def test_boss_is_scaled_to_64px_and_scanline_limit(self) -> None:
        build = sms.build_sprite_assets({
            0x01: [(self.opaque(96, 16), 7, None)],
        })
        frame = build.frames[0]
        self.assertEqual(frame["width"], 64)
        self.assertLessEqual(frame["max_scanline"], 8)

    def test_game_gear_sprite_uses_lcd_scale(self) -> None:
        build = sms.build_sprite_assets({
            0x02: [(self.opaque(32, 28), 7, None)],
        }, "gg")
        frame = build.frames[0]
        self.assertEqual((frame["width"], frame["height"]), (20, 18))
        self.assertEqual((frame["origin_x"], frame["origin_y"]), (-10, -9))
        self.assertLessEqual(frame["max_scanline"], 8)
        self.assertEqual(build.report["budget"], sms.GG_SPRITE_TILE_BUDGET)

    def test_non_boss_over_scanline_limit_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "scanline"):
            sms.build_sprite_assets({
                0x02: [(self.opaque(72, 8), 1, None)],
            })

    def test_transparent_tiles_are_trimmed(self) -> None:
        image = Image.new("RGBA", (24, 8), (0, 0, 0, 0))
        for y in range(8):
            for x in range(8, 16):
                image.putpixel((x, y), (255, 255, 255, 255))
        build = sms.build_sprite_assets({0x00: [(image, 2, None)]})
        self.assertEqual(len(build.parts), 1)
        self.assertEqual(len(build.tiles), 1)

    def test_sprite_cache_seed_is_deterministic_and_preserves_source(self) -> None:
        frames = []
        for frame_index in range(40):
            image = Image.new("RGBA", (64, 8), (0, 0, 0, 0))
            for tile_index in range(8):
                code = frame_index * 8 + tile_index
                # Unique opaque patterns; retain one pixel on every tile.
                image.putpixel((tile_index * 8, 0), (255, 255, 255, 255))
                for bit in range(9):
                    if code & (1 << bit):
                        x = tile_index * 8 + 1 + bit % 7
                        y = 1 + bit // 7
                        image.putpixel((x, y), (255, 255, 255, 255))
            frames.append((image, 1, None))
        first = sms.build_sprite_assets({0x02: frames})
        second = sms.build_sprite_assets({0x02: frames})
        self.assertGreater(len(first.tiles), sms.SPRITE_TILE_BUDGET)
        self.assertEqual(len(first.cache_seed), sms.SPRITE_TILE_BUDGET)
        self.assertEqual(first.tiles, second.tiles)
        self.assertEqual(first.parts, second.parts)
        self.assertEqual(first.cache_seed, second.cache_seed)
        self.assertGreater(first.report["source_unique_patterns"],
                           sms.SPRITE_TILE_BUDGET)
        self.assertEqual(first.report["approximated_parts"], 0)


class DigitTests(unittest.TestCase):
    def test_exact_40_patterns_use_reserved_gameplay_colors(self) -> None:
        # Four source indices: 0 cell background and three visible colors.
        source = []
        for tile_number in range(40):
            source.append(bytes(
                0 if (x + y + tile_number) % 5 == 0
                else 1 + ((x * 3 + y + tile_number) % 3)
                for y in range(8) for x in range(8)
            ))
        source_palette = [(0, 0, 0), (255, 0, 0),
                          (0, 170, 85), (0, 255, 85)]
        digits = sms.build_digit_tiles(source, source_palette)
        self.assertEqual(len(digits.tiles), 40)
        self.assertTrue(set().union(*map(set, digits.tiles)) <= {0, 14, 15})

        gameplay = Image.new("RGB", (256, 224), (85, 85, 85))
        bg0 = sms.build_background(gameplay, 216,
                                   fixed_palette_tail=digits.colors)
        bg1 = sms.build_background(Image.new("RGB", (256, 224), (0, 0, 255)),
                                   216, fixed_palette_tail=digits.colors)
        self.assertEqual(bg0.palette[14:16], digits.colors)
        self.assertEqual(bg1.palette[14:16], digits.colors)
        self.assertEqual(sms.DIGIT_TILE_BASE, 216)
        self.assertEqual(sms.DIGIT_TILE_BASE + len(digits.tiles) - 1, 255)


class AudioTests(unittest.TestCase):
    def test_pcm4_resampling_preserves_declared_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "tone.wav"
            values = [int(24000 * math) for math in (-1, -0.5, 0, 0.5, 1)] * 200
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(10000)
                wav.writeframes(struct.pack(f"<{len(values)}h", *values))
            info = sms.convert_music(path, root, 8000)
            self.assertEqual(info["sample_count"], 800)
            self.assertEqual(info["byte_count"], 400)
            self.assertAlmostEqual(info["duration_seconds"], 0.1)
            self.assertEqual((root / "music.pcm4").stat().st_size, 400)


if __name__ == "__main__":
    unittest.main()
