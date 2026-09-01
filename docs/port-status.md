# Port status

## Current result

The project builds a native Z80/SMSlib ROM and reaches live gameplay through
the complete intro flow. The shipping code is readable C; the 65816 tracer is
an offline source-of-truth tool only. The original SNES ROM is neither embedded
nor executed.

The user-selected boot behavior is:

1. Select English internally (`language = 2`).
2. Start on the original first intro/title screen.
3. Accept only Start/Pause to continue from that screen. The Konami Code there
   enables invincibility and opens the author-branded cheat screen with PCM
   voice playback.
4. Continue through the four English intro pages.
5. Enter gameplay, show only the first game-over screen, and loop.

The original language selection, story screens, and hidden fourth menu option
remain generated and addressable, but the current boot path skips them.

## Measured target budgets

| Resource | Measured result |
|---|---:|
| Static screens | 27 plus 6 gameplay backgrounds |
| Largest screen bundle | 15,904 bytes |
| Static background patterns | at most 440 |
| Gameplay background patterns | exactly 256 per background |
| Shared sprite source pairs | 278 exact 8×16 units |
| Runtime sprite cache | 92 pairs / 184 patterns at indices 256–439 |
| Maximum sprites on one scanline | 8 |
| Runtime object slots | 12 |
| MIDI duration | 46.17888 seconds |
| Compiled PSG stream | 2,479 bytes / 376 event frames |
| Cheat PCM | 23,712 samples at 5,753 Hz / 11,856 bytes |
| Linked RAM data | 1,544 bytes (`l__DATA` in the linker map) |

The 184-pattern sprite limit is physical, not arbitrary. In 224-line mode the
name table begins at VRAM `$3700`; uploading all 256 patterns in the sprite half
would overwrite it. The runtime therefore caches 92 exact 8×16 source pairs in
indices 256–439, and the converter rejects an individual source frame that
exceeds eight sprites on any scanline. Independent objects can still exceed the
hardware scanline limit when they overlap; the VDP then applies its normal
sprite-drop behavior.

## Explicit target adaptations

- SMS Mode 4 provides one 16-color background palette and one 16-color sprite
  palette. Static photos and their text overlays are composed offline from the
  ROM-derived layers and quantized to the target palette.
- The broken score display and its HUD assets are omitted at the user's
  request, leaving all 256 background patterns available to gameplay.
- The 96×96 boss frame is reduced to 64 pixels wide. This is the only explicit
  sprite-geometry demake; boss logic, hitbox, HP, motion, and timing remain the
  source-derived values.
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

## Verification gates

Run all gates with:

```sh
make verify
```

This runs the host gameplay test, synthetic graphics/PCM converter tests,
builds the ROM, captures boot and gameplay frames with MesenCE, validates the
SEGA and SDSC headers, and checks the linker map against SMS RAM limits. Kega
Fusion 3.64 on Maylee is the interactive inspection target.
