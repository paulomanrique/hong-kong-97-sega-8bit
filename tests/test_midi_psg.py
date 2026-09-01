#!/usr/bin/env python3
"""Synthetic verification for the MIDI-to-SN76489 compiler."""

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "convert_midi_psg", ROOT / "tools" / "convert_midi_psg.py"
)
assert SPEC and SPEC.loader
midi = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = midi
SPEC.loader.exec_module(midi)


def vlq(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def midi_file(track: bytes, division: int = 96) -> bytes:
    body = track + b"\x00\xff\x2f\x00"
    return (b"MThd" + struct.pack(">IHHH", 6, 0, 1, division) +
            b"MTrk" + struct.pack(">I", len(body)) + body)


class MidiPsgTests(unittest.TestCase):
    def test_tone_and_drum_compile_to_small_looping_stream(self) -> None:
        # Channel 0 middle C and channel 9 snare, both lasting one quarter.
        track = (b"\x00\xff\x51\x03\x07\xa1\x20" +
                 b"\x00\x90\x3c\x7f" + b"\x00\x99\x26\x64" +
                 vlq(96) + b"\x80\x3c\x00" +
                 b"\x00\x89\x26\x00")
        division, events, end_tick, _ = midi.parse_midi(midi_file(track))
        times, duration = midi.tick_times(events, end_tick, division)
        stream, report = midi.compile_stream(events, times, duration)
        self.assertEqual(report["dropped_channels"], [])
        self.assertGreaterEqual(report["event_frames"], 2)
        self.assertLess(len(stream), 64)
        self.assertTrue(stream.endswith(b"\x00\x00\xff"))
        self.assertIn(0x9F, stream)  # tone channel 0 is silenced on note-off
        self.assertIn(0xF0 | 15, stream)  # noise channel is silenced

    def test_convert_writes_header_and_manifest(self) -> None:
        track = b"\x00\x95\x45\x60" + vlq(48) + b"\x85\x45\x00"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song.mid"
            source.write_bytes(midi_file(track))
            report = midi.convert(source, root / "music.psg",
                                  root / "sms_audio.h", root / "music.json")
            self.assertGreater(report["total_frames"], 0)
            self.assertIn("SMS_MUSIC_TOTAL_FRAMES",
                          (root / "sms_audio.h").read_text())
            self.assertTrue((root / "music.psg").read_bytes().endswith(
                b"\x00\x00\xff"))


if __name__ == "__main__":
    unittest.main()
