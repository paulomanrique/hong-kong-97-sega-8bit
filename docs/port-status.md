# Port status

## Current result

The approved Game Gear build is release **v0.0.1**. Its SDSC two-field BCD
version is `0.01`, while the complete semantic version is stored in the SDSC
name and the repository's `VERSION` file.

The unified repository is named `hong-kong-97-sega-8bit`; both targets are
maintained on `main`, with target selection handled by the Makefile rather than
long-lived platform branches.

The project builds native Z80/SMSlib ROMs for Game Gear and Master System and
reaches live gameplay through the complete intro flow on both targets. The
shipping code is readable C; the 65816 tracer is an offline source-of-truth
tool only. The original SNES ROM is neither embedded nor executed.

The user-selected boot behavior is:

1. Select English internally (`language = 2`).
2. Start on the original first intro/title screen.
3. Accept only Game Gear Start or Master System Pause to continue from that
   screen. The Konami Code there enables invincibility and opens the
   author-branded cheat screen with PCM voice playback.
4. Continue through the four English intro pages.
5. Enter gameplay, show only the first game-over screen, and loop.

The original language selection, story screens, and hidden fourth menu option
remain generated and addressable, but the current boot path skips them.

## Measured target budgets

| Resource | Game Gear | Master System |
|---|---:|---:|
| Power-of-two padded ROM | 512 KiB | 512 KiB |
| Static screens + gameplay backgrounds | 27 + 6 | 27 + 6 |
| Largest screen bundle | 13,104 bytes | 15,904 bytes |
| Maximum static background patterns | 352 | 440 |
| Gameplay background patterns | 256 | 256 |
| Exact shared sprite source pairs | 206 | 278 |
| Runtime sprite cache | 96 pairs / 192 patterns | 92 pairs / 184 patterns |
| Maximum per-frame sprites on one scanline | 6 | 8 |
| Linked RAM data | 1,606 bytes | 1,545 bytes |

Both targets use 12 runtime object slots, the 46.17888-second MIDI arrangement,
a 2,479-byte / 376-event-frame PSG stream, and 23,712 cheat-voice samples at
5,753 Hz (11,856 packed bytes).

The cache limits are physical, not arbitrary. The SMS 224-line name table at
VRAM `$3700` leaves indices 256–439 for 92 exact 8×16 sprite pairs. The Game
Gear name table at `$3800` leaves indices 256–447 for 96 pairs. The converter
rejects any individual frame that exceeds eight sprites on a scanline.
Independent objects can still exceed the hardware limit when they overlap; the
VDP then applies its normal sprite-drop behavior.

## Explicit target adaptations

- Both Mode 4 targets provide one 16-color background palette and one 16-color
  sprite palette. SMS emits 2-bit components in 16 CRAM bytes; Game Gear emits
  4-bit components as 16 little-endian 12-bit colors in 32 bytes. Palette and
  fade writes are synchronized to VBlank as required by the Game Gear manual.
- Game Gear maps the source-derived 256×224 scene to the centered 160×144 LCD
  viewport at virtual coordinates `(48,24)`. Gameplay backgrounds and sprite
  art use the same fixed ratios, while gameplay coordinates, hitboxes, object
  state, and timing remain unchanged in the shared logic core.
- The active Game Gear title and English introduction use a readability-specific
  offline composition made only from ROM-derived layers. The title's complete
  160-pixel text window is copied at native resolution and the portraits are
  fitted below it. Introduction photos are fitted into the space left by their
  text; the original 8×8 glyph cells are kept pixel-for-pixel and reflowed to
  the LCD's 20 columns instead of being reduced to 5×5 pixels. Text colors and
  patterns are protected during palette and tile-budget conversion.
- The broken score display and its HUD assets are omitted at the user's
  request, leaving all 256 background patterns available to gameplay.
- On SMS only, the 96×96 boss frame is reduced to 64 pixels wide to meet the
  eight-sprites-per-scanline limit. Game Gear applies the same viewport mapping
  as every other sprite, producing a 60-pixel-wide boss. Boss logic, hitbox,
  HP, motion, and timing remain source-derived.
- The open `assets/music/hk97.mid` arrangement replaces the original sampled loop. MIDI
  channels 0, 1, and 5 map directly to PSG tone channels 0, 1, and 2; General
  MIDI drum channel 9 maps to PSG noise. The conversion is offline and the ROM
  plays a compact native register-event stream once per video frame.
- Per the user's request, the current boot defaults to English and bypasses the
  original language/story sequence.
- The title-screen Konami Code enables invincibility only. Its short voice cue
  is converted to unsigned PCM4 and drives all three PSG tone channels during
  playback; MIDI resumes after the cue.
- Per the user's request, the second and third Chinese game-over screens are
  not generated or shown.
- Game Gear audio initialization writes `$FF` to stereo port `$06`, routing
  all three tone channels and noise to both headphone sides.

## Verification gates

Run the Game Gear gates with `make verify`, the SMS gates with
`make verify-sms`, or both with:

```sh
make verify-all
```

Each target runs the host gameplay test and synthetic graphics/PCM converter
tests, builds its ROM, captures boot, live gameplay, and Konami-code cheat
frames with MesenCE, validates the target-specific SEGA region nibble and SDSC
header, recomputes the SEGA checksum, requires 512 KiB power-of-two padding,
and checks the linker map against RAM limits. The 512 KiB images use size
nibble 0, as measured from commercial 512 KiB Game Gear reference headers,
rather than retaining devkitSMS's 32 KiB nibble C. The checksum covers the
size-code-0 logical span through 256 KiB while excluding the complete header;
the project finalizer replaces `ihx2sms`'s fixed 32 KiB checksum. Kega Fusion
3.64 on Maylee remains the interactive SMS inspection target.
