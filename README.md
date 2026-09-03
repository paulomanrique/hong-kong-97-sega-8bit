# Hong Kong 97 — Sega 8-bit Edition

A native C/Z80 conversion of *Hong Kong 97* (HappySoft, 1995) for the Sega
Game Gear and Sega Master System. It was reimplemented from the SNES
disassembly developed for the earlier Mega Drive port. Both ROMs run directly
on their target hardware: neither embeds the SNES ROM nor interprets 65816
code. The current project version is **v0.0.1**.

Game Gear and Master System live together on the same `main` branch because
they share the native game core and offline asset pipeline. Target-specific
hardware adaptations are selected by `TARGET=gg` or `TARGET=sms`.

## Downloads

- **Master System:** [ready-to-play ROM on itch.io](https://sirvh.itch.io/hong-kong-97-master-system)
- **Game Gear v0.0.1:** built locally from a legally obtained source ROM using
  the reproducible process below. Generated commercial assets and compiled ROMs
  are intentionally not stored in this repository.

This repository intentionally contains no original-game ROM, extracted
graphics, extracted audio, generated commercial assets, or compiled `.gg` or
`.sms` file. Those files are regenerated locally from a user-supplied copy of
the original game and remain ignored by Git. The open MIDI arrangement used by
the port is included under `assets/music/`.

## Targets

| Target | Display | Color | Start input | Build output |
|---|---:|---:|---|---|
| Game Gear | 160×144 | 12-bit CRAM | Start | `build/gg/hong-kong-97-gg.gg` |
| Master System | 256×224 | 6-bit CRAM | Pause | `build/sms/hong-kong-97-sms.sms` |

Game Gear is the default build. Its gameplay imagery and sprites use a fixed
mapping from the source-derived 256×224 geometry. The title preserves its
original text pixels at native resolution, while the four English introduction
pages keep the original 8×8 glyphs and reflow them to the LCD's 20 columns.
The Master System target retains the full 256×224 presentation and requires an
SMS II-class VDP or a Mega Drive/Genesis Power Base Converter.

## Game behavior

- Boots directly to the first title/presentation screen in English.
- Only Game Gear Start or Master System Pause advances that first screen.
- The Konami Code (`Up Up Down Down Left Right Left Right 2 1`) enables
  invincibility and plays the “Eu sou cheteiro” screen and voice cue.
- D-pad moves Chan; button 1 or 2 fires.
- The original broken score display and the two Chinese screens after death
  are omitted.
- The MIDI is compiled offline to a compact native SN76489 event stream.
- Game logic, health, hitboxes, movement, and timing remain in one shared,
  target-native C core.

## Building

### Dependencies

- GNU Make and a C compiler for the host-side tests
- Python 3 with Pillow (`python3 -m pip install Pillow`)
- `ffmpeg` and `xxd`
- SDCC 4.2 or newer
- [devkitSMS](https://github.com/sverx/devkitSMS), checked out as a sibling
  directory and with `SMSlib`, `assets2banks`, and `ihx2sms` built
- The author-owned cheat assets from the public
  [Mega Drive port](https://github.com/paulomanrique/hong-kong-97-genesis),
  checked out beside this repository or supplied through `CHEAT_ASSETS`
- A legally obtained copy of the original SNES game

The expected source is the unheadered 524,288-byte No-Intro dump with SHA-1:

```text
6b518a19acea46ec62b7d7ce6604013f62a6906e
```

With `devkitSMS`, `hong-kong-97-genesis`, and
`hong-kong-97-sega-8bit` in the same parent directory:

```sh
make prepare ROM=/path/to/hk97.sfc
make gg
make sms
```

`make prepare` validates the source ROM and generates private derived assets.
`make` and `make gg` build Game Gear; `make sms` builds Master System. To keep
the dependencies in different locations, override their paths:

```sh
make prepare ROM=/path/to/hk97.sfc \
  DEVKITSMS=/path/to/devkitSMS \
  CHEAT_ASSETS=/path/to/hong-kong-97-genesis/res/egg
```

The included MIDI is used by default. `MIDI=/path/to/another.mid` selects a
different format-0 or format-1 Standard MIDI File.

After verification, create versioned local ROMs and SHA-256 sidecars with:

```sh
make release            # Game Gear
make TARGET=sms release # Master System
```

For v0.0.1, the default target produces
`release/hong-kong-97-gg-v0.0.1.gg`, its `.sha256` sidecar, and the convenient
unversioned `release/hong-kong-97-gg.gg` copy.

### Tests and verification

```text
make test        host game-logic and synthetic converter tests
make verify      Game Gear build, headers/RAM, boot, gameplay, and cheat flow
make verify-sms  the same gates for the Master System build
make verify-all  both targets
```

The verification targets expect a MesenCE build; set
`MESEN_BIN=/path/to/Mesen` when it is not installed at the default path used by
`tools/smoke.sh`.

## Repository layout

- `assets/music/`: the redistributable MIDI arrangement.
- `src/`: readable target-native game, renderer, input, and audio code.
- `tools/`: ROM validation, disassembly, extraction, graphics conversion, and
  MIDI-to-SN76489 compilation.
- `tests/`: synthetic converter tests and host-side game-logic checks.
- `docs/`: source mapping, measured target budgets, and porting notes.
- `work/`, `res/`, `generated/`, and `build/`: private or generated files;
  all are excluded from version control.

## License and legal

The reimplementation, tools, and documentation are MIT licensed; see
[`LICENSE`](LICENSE). The included MIDI is redistributed with permission as
documented in [`assets/music/README.md`](assets/music/README.md).

*Hong Kong 97* and its original graphics, audio, text, and other assets belong
to their respective rights holders. They are not included here. The Master
System ROM is distributed separately through the itch.io page linked above.
