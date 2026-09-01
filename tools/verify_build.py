#!/usr/bin/env python3
"""Structural checks for the generated Master System ROM and linker map."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("map", type=Path)
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    if len(rom) < 0x8000 or len(rom) % 0x4000:
        raise SystemExit(f"invalid banked ROM size: {len(rom)} bytes")
    if rom[0x7FF0:0x7FF8] != b"TMR SEGA":
        raise SystemExit("missing SEGA header at 0x7ff0")
    if b"SDSC" not in rom[:0x8000]:
        raise SystemExit("missing SDSC header in fixed ROM area")

    map_text = args.map.read_text(encoding="ascii", errors="replace")
    ram_match = re.search(
        r"^\s*_DATA\s+([0-9A-F]+)\s+([0-9A-F]+)", map_text,
        re.MULTILINE | re.IGNORECASE,
    )
    if not ram_match:
        raise SystemExit("linker map has no _DATA area")
    ram_start = int(ram_match.group(1), 16)
    ram_size = int(ram_match.group(2), 16)
    if ram_start < 0xC000 or ram_start + ram_size > 0xDFF0:
        raise SystemExit(
            f"RAM area exceeds safe range: {ram_start:#06x}+{ram_size:#x}"
        )

    print(
        f"ROM verified: {len(rom) // 1024} KiB, "
        f"SHA-256 {hashlib.sha256(rom).hexdigest()}, "
        f"RAM _DATA {ram_start:#06x}..{ram_start + ram_size:#06x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
