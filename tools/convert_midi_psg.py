#!/usr/bin/env python3
"""Compile a format-0/1 MIDI file to a frame-driven SN76489 stream.

The Hong Kong 97 arrangement uses MIDI channels 0, 1 and 5 for its three
pitched parts and channel 9 for drums. They map directly to the three tone
channels and the noise channel of the Master System PSG.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

PSG_CLOCK = 3_579_545
FRAME_NUMERATOR = 3_579_545
FRAME_DENOMINATOR = 59_736
TONE_CHANNELS = {0: 0, 1: 1, 5: 2}


@dataclass(frozen=True)
class Event:
    tick: int
    track: int
    order: int
    kind: str
    channel: int = 0
    a: int = 0
    b: int = 0


def read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("truncated MIDI VLQ")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, offset
    raise ValueError("MIDI VLQ exceeds four bytes")


def parse_midi(data: bytes) -> tuple[int, list[Event], int, list[str]]:
    if data[:4] != b"MThd" or len(data) < 14:
        raise ValueError("not a Standard MIDI File")
    header_size = int.from_bytes(data[4:8], "big")
    if header_size < 6 or len(data) < 8 + header_size:
        raise ValueError("invalid MIDI header")
    fmt, track_count, division = struct.unpack_from(">HHH", data, 8)
    if fmt not in (0, 1):
        raise ValueError(f"unsupported MIDI format {fmt}")
    if division & 0x8000:
        raise ValueError("SMPTE MIDI time division is not supported")

    offset = 8 + header_size
    events: list[Event] = []
    names: list[str] = []
    end_tick = 0
    for track_index in range(track_count):
        if data[offset:offset + 4] != b"MTrk" or offset + 8 > len(data):
            raise ValueError(f"missing MTrk chunk {track_index}")
        size = int.from_bytes(data[offset + 4:offset + 8], "big")
        track = data[offset + 8:offset + 8 + size]
        if len(track) != size:
            raise ValueError(f"truncated MTrk chunk {track_index}")
        offset += 8 + size

        pos = tick = order = 0
        running: int | None = None
        name = ""
        while pos < len(track):
            delta, pos = read_vlq(track, pos)
            tick += delta
            if pos >= len(track):
                raise ValueError("truncated MIDI event")
            status = track[pos]
            if status & 0x80:
                pos += 1
            elif running is not None:
                status = running
            else:
                raise ValueError("running status without channel status")

            if status == 0xFF:
                if pos >= len(track):
                    raise ValueError("truncated MIDI meta event")
                meta = track[pos]
                pos += 1
                length, pos = read_vlq(track, pos)
                payload = track[pos:pos + length]
                if len(payload) != length:
                    raise ValueError("truncated MIDI meta payload")
                pos += length
                if meta == 0x03:
                    name = payload.decode("latin-1", "replace")
                elif meta == 0x51 and length == 3:
                    events.append(Event(tick, track_index, order, "tempo",
                                        a=int.from_bytes(payload, "big")))
                    order += 1
                continue
            if status in (0xF0, 0xF7):
                length, pos = read_vlq(track, pos)
                pos += length
                running = None
                continue

            running = status
            opcode, channel = status & 0xF0, status & 0x0F
            width = 1 if opcode in (0xC0, 0xD0) else 2
            if pos + width > len(track):
                raise ValueError("truncated MIDI channel event")
            a = track[pos]
            b = track[pos + 1] if width == 2 else 0
            pos += width
            if opcode == 0x90:
                kind = "on" if b else "off"
                events.append(Event(tick, track_index, order, kind,
                                    channel, a, b))
            elif opcode == 0x80:
                events.append(Event(tick, track_index, order, "off",
                                    channel, a, b))
            elif opcode == 0xB0 and a in (7, 11):
                events.append(Event(tick, track_index, order, "control",
                                    channel, a, b))
            elif opcode == 0xE0 and (a != 0 or b != 64):
                raise ValueError("non-centered MIDI pitch bend is unsupported")
            order += 1
        names.append(name)
        end_tick = max(end_tick, tick)

    return division, events, end_tick, names


def tick_times(events: list[Event], end_tick: int,
               division: int) -> tuple[dict[int, int], int]:
    ticks = sorted({0, end_tick, *(event.tick for event in events)})
    tempos: dict[int, int] = {}
    for event in sorted(events, key=lambda e: (e.tick, e.track, e.order)):
        if event.kind == "tempo":
            tempos[event.tick] = event.a
    tempo = 500_000
    previous = elapsed = 0
    result: dict[int, int] = {}
    for tick in ticks:
        elapsed += (tick - previous) * tempo
        result[tick] = elapsed // division
        if tick in tempos:
            tempo = tempos[tick]
        previous = tick
    return result, result[end_tick]


def us_to_frame(microseconds: int) -> int:
    denominator = 1_000_000 * FRAME_DENOMINATOR
    return (microseconds * FRAME_NUMERATOR + denominator // 2) // denominator


def tone_period(note: int) -> int:
    frequency = 440.0 * math.pow(2.0, (note - 69) / 12.0)
    return max(1, min(1023, round(PSG_CLOCK / (32.0 * frequency))))


def attenuation(velocity: int, volume: int, expression: int) -> int:
    level = round(15 * velocity * volume * expression / (127 ** 3))
    return 15 - max(0, min(15, level))


def noise_control(note: int) -> int:
    if note <= 36:       # bass drum: lowest periodic-noise rate
        return 0xE2
    if note in (38, 40): # snare
        return 0xE6
    return 0xE4          # hats/cymbals: highest white-noise rate


def compile_stream(events: list[Event], tick_us: dict[int, int],
                   duration_us: int) -> tuple[bytes, dict[str, object]]:
    framed: dict[int, list[Event]] = {}
    dropped_channels: set[int] = set()
    for event in events:
        if event.kind == "tempo":
            continue
        if event.channel not in TONE_CHANNELS and event.channel != 9:
            dropped_channels.add(event.channel)
            continue
        frame = us_to_frame(tick_us[event.tick])
        framed.setdefault(frame, []).append(event)

    active: dict[int, list[tuple[int, int, int]]] = {
        channel: [] for channel in (*TONE_CHANNELS, 9)
    }
    controls = {channel: {7: 127, 11: 127} for channel in active}
    serial = 0
    tone_state: list[tuple[int | None, int]] = [(None, 15)] * 3
    noise_state: tuple[int, int] = (0xE4, 15)
    writes_by_frame: dict[int, bytes] = {}

    for frame in sorted(framed):
        for event in sorted(framed[frame], key=lambda e: (e.tick, e.track, e.order)):
            if event.kind == "control":
                controls[event.channel][event.a] = event.b
            elif event.kind == "on":
                serial += 1
                active[event.channel].append((serial, event.a, event.b))
            elif event.kind == "off":
                notes = active[event.channel]
                for index in range(len(notes) - 1, -1, -1):
                    if notes[index][1] == event.a:
                        del notes[index]
                        break

        writes = bytearray()
        next_tones: list[tuple[int | None, int]] = []
        for midi_channel, psg_channel in TONE_CHANNELS.items():
            selected = max(active[midi_channel], default=None)
            if selected is None:
                state = (None, 15)
            else:
                _, note, velocity = selected
                state = (tone_period(note), attenuation(
                    velocity, controls[midi_channel][7], controls[midi_channel][11]
                ))
            old_period, old_volume = tone_state[psg_channel]
            period, volume = state
            if period is not None and period != old_period:
                writes.extend((0x80 | (psg_channel << 5) | (period & 0x0F),
                               (period >> 4) & 0x3F))
            if volume != old_volume:
                writes.append(0x90 | (psg_channel << 5) | volume)
            next_tones.append(state)
        tone_state = next_tones

        selected_drum = max(active[9], default=None)
        if selected_drum is None:
            next_noise = (noise_state[0], 15)
        else:
            _, note, velocity = selected_drum
            next_noise = (noise_control(note), attenuation(
                velocity, controls[9][7], controls[9][11]
            ))
        if next_noise[0] != noise_state[0]:
            writes.append(next_noise[0])
        if next_noise[1] != noise_state[1]:
            writes.append(0xF0 | next_noise[1])
        noise_state = next_noise
        if writes:
            writes_by_frame[frame] = bytes(writes)

    total_frames = max(1, us_to_frame(duration_us))
    points = sorted(writes_by_frame)
    if not points or points[0] != 0:
        writes_by_frame[0] = bytes((0x9F, 0xBF, 0xDF, 0xFF))
        points = sorted(writes_by_frame)

    stream = bytearray()
    for index, frame in enumerate(points):
        next_frame = points[index + 1] if index + 1 < len(points) else total_frames
        delay = max(1, next_frame - frame)
        writes = writes_by_frame[frame]
        if len(writes) > 254:
            raise ValueError("too many PSG writes in one frame")
        stream.extend(struct.pack("<HB", delay, len(writes)))
        stream.extend(writes)
    stream.extend(b"\0\0\xFF")
    report = {
        "encoding": "psg-frame-events-v1",
        "frame_rate": FRAME_NUMERATOR / FRAME_DENOMINATOR,
        "total_frames": total_frames,
        "duration_seconds": duration_us / 1_000_000,
        "event_frames": len(points),
        "byte_count": len(stream),
        "tone_channel_map": {str(k): v for k, v in TONE_CHANNELS.items()},
        "drum_channel": 9,
        "dropped_channels": sorted(dropped_channels),
    }
    return bytes(stream), report


def convert(path: Path, output: Path, header: Path,
            manifest: Path) -> dict[str, object]:
    division, events, end_tick, names = parse_midi(path.read_bytes())
    times, duration_us = tick_times(events, end_tick, division)
    stream, report = compile_stream(events, times, duration_us)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(stream)
    header.write_text(
        "/* Generated by tools/convert_midi_psg.py. Do not edit. */\n"
        "#ifndef HK97_SMS_AUDIO_H\n#define HK97_SMS_AUDIO_H\n"
        f"#define SMS_MUSIC_TOTAL_FRAMES {report['total_frames']}u\n"
        "#endif\n",
        encoding="utf-8",
    )
    report.update({"source": path.name, "division": division,
                   "track_names": names})
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/music.psg"))
    parser.add_argument("--header", type=Path, default=Path("generated/sms_audio.h"))
    parser.add_argument("--manifest", type=Path,
                        default=Path("generated/music_manifest.json"))
    args = parser.parse_args()
    try:
        report = convert(args.midi, args.output, args.header, args.manifest)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"generated {report['event_frames']} PSG event frames, "
          f"{report['byte_count']} bytes, {report['duration_seconds']:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
