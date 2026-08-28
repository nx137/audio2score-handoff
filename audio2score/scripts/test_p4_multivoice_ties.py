#!/usr/bin/env python3
"""P4 聚焦自动化测试（tie 链按 voice 隔离）。

验证 P4b 多声部导出器把跨小节延音以成员级 start/continue/stop tie 表达，
并且每条 tie 链完整落在单一 music21 voice 内，不跨 voice 串音。本文件不修改
任何 P3 生产导出器（``midi_to_score``）。

运行方式（在 scripts/ 目录下）：
    python3 -m unittest test_p4_multivoice_ties -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock as mock
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from music21 import chord as m21chord
from music21 import clef

from p4_multivoice_score import (
    _music_element,
    _voice_measure_elements,
    build_multivoice_part,
    decode_midi_to_voice_events,
    sanitize_pedal_retakes,
    split_voice_events_at_barlines,
)
from structured_duration_decoder import decode_hand
from voice_assignment import VoiceEvent

BAR_QL = 4.0


def make_event(pitch: int, start: float, duration: float,
               voice: int, hand: str = "RH") -> VoiceEvent:
    return VoiceEvent(pitch, start, duration, 80, voice, hand)


class TestTieChainVoiceIsolation(unittest.TestCase):
    def test_split_assigns_start_stop_roles_per_voice(self):
        events = [make_event(60, 3.5, 1.0, 1), make_event(62, 3.5, 0.5, 2)]
        segments = split_voice_events_at_barlines(events, BAR_QL)
        roles = {}
        for event, role in segments:
            key = (event.voice, round(event.start_ql, 3), round(event.duration_ql, 3))
            roles[key] = role
        # voice 1 跨小节线长音切成 start + stop 两段
        self.assertEqual(roles[(1, 3.5, 0.5)], "start")
        self.assertEqual(roles[(1, 4.0, 0.5)], "stop")
        # voice 2 同起音短音不跨线，无 tie 角色
        self.assertEqual(roles[(2, 3.5, 0.5)], None)

    def test_split_continue_role_for_multi_measure_span(self):
        event = make_event(60, 7.5, 6.0, 1)  # 7.5 → 13.5，跨 8.0 / 12.0 两条线
        segments = split_voice_events_at_barlines([event], BAR_QL)
        self.assertEqual(len(segments), 3)
        detail = [(round(e.start_ql, 3), round(e.duration_ql, 3), role)
                  for e, role in segments]
        self.assertEqual(detail, [
            (7.5, 0.5, "start"),
            (8.0, 4.0, "continue"),
            (12.0, 1.5, "stop"),
        ])

    def test_build_part_keeps_tie_chain_inside_single_voice(self):
        events = [make_event(60, 3.5, 1.0, 1), make_event(62, 3.5, 0.5, 2)]
        part = build_multivoice_part(events, "Piano R.H.", clef.TrebleClef(),
                                     90.0, (4, 4), None)
        tied = []
        untied = []
        for measure in part.getElementsByClass("Measure"):
            for voice in measure.getElementsByClass("Voice"):
                for element in voice.notes:
                    tie_type = getattr(getattr(element, "tie", None), "type", None)
                    entry = (voice.id, round(float(element.offset), 3), str(element.pitch))
                    if tie_type:
                        tied.append((*entry, tie_type))
                    else:
                        untied.append(entry)
        # 跨线 tie 链 start→stop 完整落在 voice 1
        self.assertIn(("1", 3.5, "C4", "start"), tied)
        self.assertIn(("1", 0.0, "C4", "stop"), tied)
        # 所有带 tie 的音都在 voice 1
        self.assertTrue(all(voice_id == "1" for voice_id, *_rest in tied))
        # voice 2 的音没有 tie
        self.assertEqual([entry for entry in untied if entry[0] == "2"],
                         [("2", 3.5, "D4")])

    def test_chord_members_keep_member_level_ties(self):
        # 同 onset/duration/voice 的两音跨小节 → 组成 Chord，两端各带 tie。
        events = [make_event(60, 3.5, 1.0, 1), make_event(64, 3.5, 1.0, 1)]
        segments = split_voice_events_at_barlines(events, BAR_QL)
        element = _music_element([(e, r) for e, r in segments if r == "start"])
        self.assertIsInstance(element, m21chord.Chord)
        self.assertEqual(len(element.notes), 2)
        self.assertEqual({n.tie.type for n in element.notes}, {"start"})

    def test_music_element_rejects_inconsistent_tie_roles(self):
        group = [(make_event(60, 0.0, 0.5, 1), "start"),
                 (make_event(64, 0.0, 0.5, 1), "stop")]
        with self.assertRaises(ValueError):
            _music_element(group)

    def test_voice_measure_elements_rejects_overlap(self):
        segments = [(make_event(60, 0.0, 1.0, 1), None),
                    (make_event(62, 0.5, 0.5, 1), None)]
        with self.assertRaises(ValueError):
            _voice_measure_elements(segments, 0, BAR_QL)

    def test_decode_then_build_isolates_tie_chain_by_voice(self):
        # 端到端：结构化解码选出跨线 tie 后，导出仍把链隔离在单一 voice 内。
        raw = [(60, 3.5, 1.0, 80), (62, 4.0, 1.0, 80)]
        decoded = decode_hand(raw, [], "RH", bar_ql=BAR_QL, divisors=(8, 4, 3))
        sustained = next(e for e in decoded if e.pitch == 60)
        inner = next(e for e in decoded if e.pitch == 62)
        self.assertNotEqual(sustained.voice, inner.voice)

        part = build_multivoice_part(decoded, "Piano R.H.", clef.TrebleClef(),
                                     90.0, (4, 4), None)
        tied_by_voice = {}
        for measure in part.getElementsByClass("Measure"):
            for voice in measure.getElementsByClass("Voice"):
                for element in voice.notes:
                    tie_type = getattr(getattr(element, "tie", None), "type", None)
                    if tie_type:
                        tied_by_voice.setdefault(voice.id, []).append(
                            (measure.number, round(float(element.offset), 3),
                             str(element.pitch), tie_type)
                        )
        # 只有 voice 1 带 tie，且同时含 start 与 stop（链自洽）。
        self.assertEqual(set(tied_by_voice), {"1"})
        chain = tied_by_voice["1"]
        self.assertIn("start", {entry[3] for entry in chain})
        self.assertIn("stop", {entry[3] for entry in chain})


class TestNoPedalDecoderSwitch(unittest.TestCase):
    def test_no_pedal_passes_empty_intervals_to_decoder(self):
        notes = [(60, 0.0, 0.5, 80)]
        pedals = [(0.0, 2.0)]
        meta = {"tempo_bpm": 120.0, "time_sigs": [(4, 4, 0.0)]}
        decoded = {"RH": [], "LH": []}

        with mock.patch("p4_multivoice_score.midi_to_events",
                        return_value=(notes, pedals, meta)), \
             mock.patch("p4_multivoice_score.decode_score_hands",
                        return_value=decoded) as decoder:
            result = decode_midi_to_voice_events("input.mid", use_pedal=False)

        self.assertEqual(result[1], pedals)
        self.assertEqual(decoder.call_args.args[2], [])

    def test_pedal_mode_passes_intervals_to_decoder(self):
        notes = [(60, 0.0, 0.5, 80)]
        pedals = [(0.0, 2.0)]
        meta = {"tempo_bpm": 120.0, "time_sigs": [(4, 4, 0.0)]}
        decoded = {"RH": [], "LH": []}

        with mock.patch("p4_multivoice_score.midi_to_events",
                        return_value=(notes, pedals, meta)), \
             mock.patch("p4_multivoice_score.decode_score_hands",
                        return_value=decoded) as decoder:
            decode_midi_to_voice_events("input.mid", use_pedal=True)

        self.assertEqual(decoder.call_args.args[2], pedals)


class TestPedalRetakeNormalization(unittest.TestCase):
    """同一 MusicXML 落点的踏板 stop/start 应序列化为 change。"""

    @staticmethod
    def _write_xml(path: Path, separated: bool = False) -> None:
        spacer = "<note><rest/><duration>4</duration></note>" if separated else ""
        path.write_text(
            "<score-partwise version=\"3.1\"><part-list><score-part id=\"P1\">"
            "<part-name>Piano</part-name></score-part></part-list><part id=\"P1\">"
            "<measure number=\"1\"><direction><direction-type><pedal type=\"stop\"/>"
            "</direction-type></direction>" + spacer +
            "<direction><direction-type><pedal type=\"start\"/></direction-type>"
            "</direction></measure></part></score-partwise>",
            encoding="utf-8",
        )

    def test_same_location_stop_start_becomes_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "retake.musicxml"
            self._write_xml(path)
            sanitize_pedal_retakes(path)
            pedals = ET.parse(path).getroot().findall(".//pedal")
        self.assertEqual([pedal.get("type") for pedal in pedals], ["change"])

    def test_separated_stop_start_remains_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "separated.musicxml"
            self._write_xml(path, separated=True)
            sanitize_pedal_retakes(path)
            pedals = ET.parse(path).getroot().findall(".//pedal")
        self.assertEqual([pedal.get("type") for pedal in pedals], ["stop", "start"])
