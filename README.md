# Hong Kong 97 — Sega Master System port

A native C/Z80 conversion of *Hong Kong 97* (HappySoft, 1995) for the Sega
Master System. It was reimplemented from the SNES disassembly developed for
the earlier Mega Drive port. The result runs directly on the target hardware:
it neither embeds the SNES ROM nor interprets 65816 code.

**[Download the ready-to-play Master System ROM on itch.io](https://sirvh.itch.io/hong-kong-97-master-system)**

This repository intentionally contains no original-game ROM, extracted
graphics, extracted audio, generated commercial assets, or compiled `.sms`
file. Those files are regenerated locally from a user-supplied copy of the
original game and remain ignored by Git. The open MIDI arrangement used by the
port is included under `assets/music/`.

## Port behavior

- Boots directly to the first title/presentation screen in English.
- Only Start/Pause advances that first screen.
- The Konami Code (`Up Up Down Down Left Right Left Right 2 1`) enables
  invincibility and plays the “Eu sou cheteiro” screen and voice cue.
- D-pad moves Chan; button 1 or 2 fires.
- The original broken score display and the two Chinese screens after death
  are omitted.
- The MIDI is compiled offline to a compact native SN76489 event stream.
- The 96-pixel boss is reduced to 64 pixels to fit the Master System's limit of
  eight sprites on one scanline. Game logic, health, hitboxes, and movement
  remain target-native C.

The target is 256×224 NTSC Mode 4 and requires an SMS II-class VDP, Game Gear
VDP, or a Mega Drive/Genesis Power Base Converter.

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

With `devkitSMS`, `hong-kong-97-genesis`, and this repository in the same
parent directory:

```sh
python3 -m pip install Pillow
make prepare ROM=/path/to/hk97.sfc
make
```

The resulting ROM is `build/hong-kong-97-sms.sms`. `make prepare` validates
the source ROM before extracting anything. To keep the other repositories in
different locations, override their paths:

```sh
make prepare ROM=/path/to/hk97.sfc \
  DEVKITSMS=/path/to/devkitSMS \
  CHEAT_ASSETS=/path/to/hong-kong-97-genesis/res/egg
```

The included MIDI is used by default. `MIDI=/path/to/another.mid` selects a
different format-0 or format-1 Standard MIDI File.

### Tests and verification

```sh
make test       # host game-logic and synthetic converter tests
make verify     # tests, ROM build, header/RAM checks, and MesenCE smoke flow
```

`make verify` expects a MesenCE build; set `MESEN_BIN=/path/to/Mesen` when it
is not installed at the default path used by `tools/smoke.sh`.

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
to their respective rights holders. They are not included here. The generated
ROM is available separately from the itch.io page linked above.
