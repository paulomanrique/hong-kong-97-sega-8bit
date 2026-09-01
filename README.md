# Hong Kong 97 — Sega Master System port

Native C/Z80 conversion of *Hong Kong 97* (HappySoft, 1995) for the Sega
Master System. The complete gameplay specification and extraction pipeline come
from the existing Mega Drive port and its SNES disassembly. The shipping ROM
does not interpret 65816 code and does not contain the original SNES ROM.

The target is 256×224 NTSC Mode 4 and therefore requires an SMS II-class VDP,
Game Gear VDP, or a Mega Drive/Genesis Power Base Converter. Game logic,
coordinates, timings, hitboxes, object behavior, score bugs, screen flow, and
the six-background cycle remain source-derived. The asset pipeline documents
the smaller target's visual conversions and fails when a hardware budget is
exceeded.

## Required source ROM

Supply the unheadered 524,288-byte ROM whose SHA-1 is
`6b518a19acea46ec62b7d7ce6604013f62a6906e`. It is read only to regenerate
commercial graphics, audio, and tables locally; all such outputs are ignored by
Git.

```sh
make prepare ROM=/path/to/hk97.sfc
make verify
```

Dependencies: Python 3, Pillow, NumPy, SDCC 4.x, a sibling `devkitSMS`
checkout, and the locally built `ihx2sms` from that checkout. Headless runtime
verification uses MesenCE through `tools/smoke.sh`.

## Architecture

- `tools/`: deterministic ROM validation, source disassembly, extraction, and
  SMS asset conversion.
- `src/`: readable target-native game/runtime code compiled by SDCC.
- `generated/`: banked commercial data regenerated from the user's ROM.
- `tests/`: synthetic converter tests and host-side game-logic checks.
- `docs/source-mapping.md`: SNES routine/table to C behavior map inherited
  from the measured Mega Drive conversion.

The original's hidden fourth language-menu option remains. Mega Drive-port
extras (Konami code, cheats, creator branding, jingle, and invented blinking
`PRESS START`) are deliberately excluded from the fidelity baseline.

