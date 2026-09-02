#!/usr/bin/env python3
"""Synthetic checks for final SEGA header sizing and checksum."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "finalize_rom", ROOT / "tools" / "finalize_rom.py"
)
assert SPEC and SPEC.loader
finalize_rom = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = finalize_rom
SPEC.loader.exec_module(finalize_rom)


class FinalizeRomTests(unittest.TestCase):
    def make_rom(self) -> bytearray:
        rom = bytearray(finalize_rom.ROM_SIZE)
        rom[0x7FF0:0x7FF8] = b"TMR SEGA"
        rom[0x100] = 1
        rom[0x10000] = 2
        rom[0x40000] = 4  # outside the size-code-0 checksum span
        return rom

    def test_checksum_uses_256k_span_and_excludes_header(self) -> None:
        rom = self.make_rom()
        self.assertEqual(finalize_rom.calculate_checksum(rom), 3)
        rom[0x7FF8] = 0xFF
        self.assertEqual(finalize_rom.calculate_checksum(rom), 3)

    def test_finalize_sets_target_header_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.gg"
            path.write_bytes(self.make_rom())
            checksum = finalize_rom.finalize(path, "gg")
            rom = path.read_bytes()
            self.assertEqual(checksum, 3)
            self.assertEqual(rom[0x7FFF], 0x70)
            self.assertEqual(rom[0x7FFA:0x7FFC], bytes((3, 0)))


if __name__ == "__main__":
    unittest.main()
