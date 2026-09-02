#!/usr/bin/env python3
"""Finalize the project ROM's SEGA header after ihx2sms padding."""

from __future__ import annotations

import argparse
from pathlib import Path

ROM_SIZE = 512 * 1024
CHECKSUM_END = 256 * 1024
HEADER_START = 0x7FF0
HEADER_END = 0x8000
CHECKSUM_LOW = 0x7FFA


def calculate_checksum(rom: bytes | bytearray) -> int:
    """Checksum the size-code-0 span, excluding the complete SEGA header."""
    if len(rom) < CHECKSUM_END:
        raise ValueError("ROM is smaller than the 256 KiB checksum span")
    return (sum(rom[:HEADER_START])
            + sum(rom[HEADER_END:CHECKSUM_END])) & 0xFFFF


def finalize(path: Path, target: str) -> int:
    rom = bytearray(path.read_bytes())
    if len(rom) != ROM_SIZE:
        raise ValueError(f"ROM must be {ROM_SIZE} bytes after padding")
    if rom[HEADER_START:HEADER_START + 8] != b"TMR SEGA":
        raise ValueError("missing SEGA header at 0x7ff0")

    rom[0x7FFF] = 0x70 if target == "gg" else 0x40
    checksum = calculate_checksum(rom)
    rom[CHECKSUM_LOW] = checksum & 0xFF
    rom[CHECKSUM_LOW + 1] = checksum >> 8
    path.write_bytes(rom)
    return checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("sms", "gg"), required=True)
    parser.add_argument("rom", type=Path)
    args = parser.parse_args()
    try:
        checksum = finalize(args.rom, args.target)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"finalized {args.target.upper()} header: checksum {checksum:#06x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
