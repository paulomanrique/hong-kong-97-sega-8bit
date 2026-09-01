#!/usr/bin/env python3
"""Extract the Hong Kong 97 ROM from the No-Intro zip to work/hk97.sfc.

Validates the SHA1 so the other tools work on the expected dump. The ROM
is not versioned (work/ is in .gitignore).
"""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

EXPECTED_SHA1 = "6b518a19acea46ec62b7d7ce6604013f62a6906e"
OUT = Path(__file__).resolve().parent.parent / "work" / "hk97.sfc"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=Path,
                    help="expected .sfc file or a zip containing it")
    args = ap.parse_args()

    if OUT.exists():
        data = OUT.read_bytes()
        if hashlib.sha1(data).hexdigest() == EXPECTED_SHA1:
            print(f"ok (already exists): {OUT}")
            return 0
        print("work/hk97.sfc exists but has the wrong SHA1; re-extracting")

    if args.rom.suffix.lower() == ".zip":
        with zipfile.ZipFile(args.rom) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".sfc")]
            if len(names) != 1:
                print(f"ERROR: expected one .sfc in zip, found {len(names)}")
                return 1
            data = z.read(names[0])
    else:
        data = args.rom.read_bytes()

    sha1 = hashlib.sha1(data).hexdigest()
    if sha1 != EXPECTED_SHA1:
        print(f"ERROR: unexpected SHA1 {sha1} (expected {EXPECTED_SHA1})")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"ok: {OUT} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
