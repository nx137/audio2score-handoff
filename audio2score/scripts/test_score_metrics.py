#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from score_metrics import evaluate_score


XML = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>{duration}</duration><voice>1</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
'''

TIE_XML_CORRECT = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><voice>1</voice><type>whole</type>
        <tie type="start"/></note>
    </measure>
    <measure number="2">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type>
        <tie type="stop"/></note>
    </measure>
  </part>
</score-partwise>
'''

TIE_XML_BROKEN = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><voice>1</voice><type>whole</type>
        <tie type="start"/></note>
    </measure>
    <measure number="2">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
'''

CHORD_TWO_VOICE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>{melody_voice}</voice><type>quarter</type></note>
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><voice>{melody_voice}</voice><type>quarter</type><chord/></note>
      <backup><duration>4</duration></backup>
      <note><pitch><step>C</step><octave>3</octave></pitch><duration>4</duration><voice>{bass_voice}</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
'''

PEDAL_XML_REFERENCE = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <direction><direction-type><pedal type="start"/></direction-type></direction>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      <direction><direction-type><pedal type="stop"/></direction-type></direction>
      <direction><direction-type><pedal type="start"/></direction-type></direction>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
'''

PEDAL_XML_SYSTEM = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <direction><direction-type><pedal type="start"/></direction-type></direction>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      <direction><direction-type><pedal type="change"/></direction-type></direction>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
'''


class TestScoreMetrics(unittest.TestCase):
    def test_exact_single_event_scores_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.musicxml"
            system = root / "system.musicxml"
            alignment = root / "alignment.csv"
            reference.write_text(XML.format(duration=4), encoding="utf-8")
            system.write_text(XML.format(duration=4), encoding="utf-8")
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8")
            result = evaluate_score(system, reference, alignment)
        self.assertEqual(result["note"]["f1"], 1.0)
        self.assertEqual(result["duration"]["accuracy"], 1.0)
        self.assertIsNone(result["pedal"]["all"])

    def test_duration_error_is_not_pitch_or_onset_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.musicxml"
            system = root / "system.musicxml"
            alignment = root / "alignment.csv"
            reference.write_text(XML.format(duration=4), encoding="utf-8")
            system.write_text(XML.format(duration=8), encoding="utf-8")
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8")
            result = evaluate_score(system, reference, alignment)
        self.assertEqual(result["pitch"]["f1"], 1.0)
        self.assertEqual(result["onset"]["f1"], 1.0)
        self.assertEqual(result["note"]["tp"], 0)
        self.assertEqual(result["duration"]["accuracy"], 0.0)
        self.assertEqual(result["duration"]["mae_ql"], 1.0)

    def test_tie_chain_correct_when_system_matches_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.musicxml"
            system = root / "system.musicxml"
            alignment = root / "alignment.csv"
            reference.write_text(TIE_XML_CORRECT, encoding="utf-8")
            system.write_text(TIE_XML_CORRECT, encoding="utf-8")
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8")
            result = evaluate_score(system, reference, alignment)
        self.assertTrue(result["tie_chain"]["available"])
        self.assertEqual(result["tie_chain"]["reliably_mapped_reference_tied_events"], 1)
        self.assertEqual(result["tie_chain"]["accuracy"], 1.0)

    def test_tie_chain_detects_broken_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.musicxml"
            system = root / "system.musicxml"
            alignment = root / "alignment.csv"
            reference.write_text(TIE_XML_CORRECT, encoding="utf-8")
            system.write_text(TIE_XML_BROKEN, encoding="utf-8")
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8")
            result = evaluate_score(system, reference, alignment)
        self.assertTrue(result["tie_chain"]["available"])
        self.assertEqual(result["tie_chain"]["reliably_mapped_reference_tied_events"], 1)
        self.assertEqual(result["tie_chain"]["correct_chain_role_events"], 0)
        self.assertEqual(result["tie_chain"]["accuracy"], 0.0)

    def test_voice_consistency_uses_cluster_purity_not_raw_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.musicxml"
            system = root / "system.musicxml"
            alignment = root / "alignment.csv"
            reference.write_text(
                CHORD_TWO_VOICE_XML.format(melody_voice=1, bass_voice=2), encoding="utf-8")
            # 系统把参考谱的 voice 1/2 编号整体互换；純度指标不应因编号不同而判错。
            system.write_text(
                CHORD_TWO_VOICE_XML.format(melody_voice=2, bass_voice=1), encoding="utf-8")
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n"
                "RH,64,0,P1,1,64,0\n"
                "RH,48,0,P1,2,48,0\n", encoding="utf-8")
            result = evaluate_score(system, reference, alignment)
        self.assertTrue(result["voice_consistency"]["available"])
        self.assertEqual(result["voice_consistency"]["matched_note_events"], 3)
        self.assertEqual(result["voice_consistency"]["accuracy"], 1.0)

    def test_pedal_stop_start_same_position_normalizes_to_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.musicxml"
            system = root / "system.musicxml"
            alignment = root / "alignment.csv"
            reference.write_text(PEDAL_XML_REFERENCE, encoding="utf-8")
            system.write_text(PEDAL_XML_SYSTEM, encoding="utf-8")
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n"
                "RH,62,1,P1,1,62,1\n", encoding="utf-8")
            result = evaluate_score(system, reference, alignment)
        self.assertTrue(result["pedal"]["available"])
        self.assertEqual(result["pedal"]["reference_events"], 2)
        self.assertEqual(result["pedal"]["all"]["f1"], 1.0)
        self.assertEqual(result["pedal"]["by_type"]["start"]["f1"], 1.0)
        self.assertEqual(result["pedal"]["by_type"]["change"]["f1"], 1.0)


if __name__ == "__main__":
    unittest.main()
