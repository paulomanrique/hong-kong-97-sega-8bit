# Notes from one Claude to another: lessons from the SNES→Mega Drive port (HK97)

From whoever built hong-kong-97-genesis to whoever builds the next one.
That project's code is a living reference — when something here feels
abstract, go read `../hong-kong-97-genesis/tools/` and `src/`.

## Strategy that worked

- **Reimplement in C/SGDK guided by the disassembly; do not translate asm.**
  The disassembly is the source of truth for constants (per-frame speeds,
  timers, tables), not a text to convert line by line.
- **Write your own 65816 tracer** (recursive descent from the vectors,
  tracking the M/X flags via REP/SEP to size immediates). DiztinGUIsh is
  GUI-only — useless for automation; copy `tools/trace65816.py` from HK97
  and adapt it. You feed indirect jump tables in manually as extra entries
  (read the table from the ROM and generate the targets); watch out for
  two patterns: handlers via `JML [$dp]` with separate bank/addr tables,
  and returns pushed with `PEA` — the RTL returns to **address+1**.
- **Consolidate everything into a `docs/mapping.md`** (routine→C function,
  RAM→variable, the format of each table). It's the document you'll reread
  constantly.
- **Small, frequent commits.** And nail the `.gitignore` BEFORE the first
  `git add -A`: the ROM, everything derived from it, and downloaded tools
  (I committed the whole BizHawk by accident — 529 files).

## SNES data traps that bit me

- **IPL (SPC) upload blocks have a 4-byte header** (len, addr). I got the
  offset wrong TWICE by forgetting this. Any pointer to "block data" =
  header position + 4.
- **A tilemap entry's tile index is 10 bits.** If you generate sequential
  maps with an added base (e.g. 0x200+i), it silently overflows mid-screen
  — my "background cut in half" bug.
- **Video registers may be initialized from a table at RESET**
  (value/addr triples). If you don't find BGMODE/base writes in the trace,
  look for the init loop.
- **Color math (CGWSEL/CGADSUB/COLDATA) is part of the visuals.** Compare
  against real-hardware screenshots early: in HK97 the whole gameplay had
  a fixed color subtract I only noticed in a side-by-side. Cheap MD fix:
  bake it into the palette (subtract/add per channel, `(v&0x1F)*8` for 8
  bits) and keep the raw palette for flash effects.
- **Common pattern: a 2bpp BG used as a linear text framebuffer**
  (sequential tilemap + glyphs drawn as pixels). If the game writes
  (VMADD, VMDATA) pairs via DMA mode 4, that's it.
- Validate the decompressor **against known sizes** (palette = 0x20/0x200,
  full-screen tiles = 0x7000). A Python screen simulator (VRAM + a CGRAM
  shadow + the load primitives) pays for itself: it produces pixel-perfect
  PNGs that become the rescomp assets directly.

## Audio

- **Don't guess the sample rate.** Dump the real audio:
  `EmuHawk --dump-type=wave --dump-name=out.wav --dump-length=1800
  --dump-close rom.sfc`, and measure the loop period by autocorrelation.
  I assumed a "plausible" 16 kHz and it was 8 kHz — the user heard it
  instantly.
- SPC pitch → Hz: `rate = 32000 * P / 0x1000`. DSP writes are usually
  indirect (`MOV X,#$F2 / MOV (X),A` or reg/value tables) — don't only
  search for `MOV $F2,#imm`.
- SGDK: `SND_PCM_startPlay(..., loop)` handles a sample-as-music; BRR
  decode is standard (9 bytes/block, 4 filters).

## SGDK — specific gotchas

- `VDP_setScreenWidth256()` exists and gives 1:1 coordinates with the SNES.
- **Plane A lives at $E000** (not $C000) in the default layout — if a
  graphic "doesn't appear", probe VRAM/CRAM in the emulator before
  theorizing.
- VRAM budget: user tiles can start at 16 (you don't need the reserved 256
  if you don't use the system font); the sprite engine allocates ~420
  tiles at the END of VRAM — a full photo (896 tiles) + text + extras
  invades it if you don't plan.
- **Never apply a palette before finishing loading tiles/map** —
  accumulate into a target buffer and apply on fade-in; otherwise the load
  "flashes" on screen (a glitch the user notices).
- Indexed IMAGE palettes preserve the PNG indices — but check WHICH index
  is the visible color: I lost an hour to index-1-black text on black (the
  white was index 2).
- `sizeof(resource)` works for a rescomp WAV.

## Testing (the project's biggest multiplier)

- **BizHawk + Lua is the way**: `EmuHawk --lua=script.lua rom.gen`.
  - The ROM MUST have a `.gen`/`.md` extension — `.bin` opens a GUI
    platform dialog and stalls everything silently.
  - Absolute paths in Lua; log to a file from line 1 + `pcall`;
    `client.exit()` at the end.
  - **Fades eat input**: to navigate screens, spam a button in a loop, not
    a timed single press.
  - Probe `memory.usememorydomain("VRAM"/"CRAM")` to debug invisible
    graphics. Worth gold.
  - Mesen 2 `--testrunner` didn't work (script never loads, no error).
    Don't insist.
- **Run the original SNES ROM in the SAME BizHawk** and capture
  screenshots at the same milestones for a side-by-side. Buttons differ
  (confirm on the SNES is usually B/Y, not Start) — find out by testing,
  not by assuming.
- Test builds with a `#define` override (e.g. boss on the first spawn) to
  reach deep states in seconds.
- If something stalls with no explanation, screenshot the desktop via
  PowerShell (`CopyFromScreen`) — there may be a dialog invisible to you.

## Environment (this machine)

- SGDK 2.11 at `C:\SGDK`; copy HK97's `build.ps1` (it sets GDK/JAVA).
- PowerShell 5.1: no `&&`; double quotes inside a here-string passed to git
  break the message — write commit messages without `"`.
- BizHawk already downloaded at `../hong-kong-97-genesis/tools/bizhawk/`.
- ffmpeg available (via winget) for audio conversions.
- The user tests in Kega Fusion (`C:\Games\Sega - Mega Drive\Kega`) — **do
  not open an emulator in front of them without warning**; run BizHawk
  `-WindowStyle Minimized` for verification and tell them when it's ready
  to test.
- Prefer a `Start`-only menu confirm when you add a title screen, so any
  future button combo can't collide with menu confirmation.

Good luck. Measure before you assume — the three times I got burned here
were the three times it "looked obvious".
