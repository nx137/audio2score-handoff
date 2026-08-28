#!/usr/bin/env python3
"""P4 聚焦自动化测试（候选 CSV schema / measure DP 硬约束 / 特征映射）。

本文件只验证 P4 结构化解码器与候选级数据管线的可测试接口，不修改任何
P3 生产导出器（``midi_to_score``）。覆盖：

* ``candidate_features`` 输出与 ``train_candidate_model.FEATURES`` 的列映射；
* ``write_candidate_table`` / ``build_candidate_dataset.build_dataset`` 的 CSV schema；
* measure DP 的“同 voice 下一起音”硬边界（``_candidate_sets`` 合法候选裁剪）与
  解码后同 voice 不重叠（``decode_hand`` + ``validate_voice_events``）。

运行方式（在 scripts/ 目录下）：
    python3 -m unittest test_p4_structured_decoder -v
    # 或 python3 -m unittest discover -s . -p 'test_p4_*.py' -v
"""
from __future__ import annotations

import csv
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import train_candidate_model as train_mod
from auto_label_candidates import (
    _deduplicate_notation_events,
    _read_alignment,
    build_auto_labeled_dataset,
    reference_score_events,
)
from build_candidate_dataset import build_dataset
from structured_duration_decoder import (
    DurationCandidate,
    _candidate_sets,
    _decode_measure_dp,
    candidate_feature_probability,
    candidate_features,
    candidate_probability,
    decode_hand,
    rank_candidates,
    write_candidate_table,
)
from train_candidate_model import probability_from_model, train_model
from voice_assignment import VoiceEvent, validate_voice_events

EPS = 1e-7

ANNOTATION_COLUMNS = {
    "piece", "hand", "review_priority", "suggested_review_class",
    "label", "review_class", "review_note",
}


def make_event(pitch: int, start: float, duration: float,
               voice: int = 1, hand: str = "RH") -> VoiceEvent:
    return VoiceEvent(pitch, start, duration, 80, voice, hand)


class TestCandidateFeaturesToTrainingFeatures(unittest.TestCase):
    """candidate_features dict 与训练 FEATURES 的映射关系。"""

    def _features(self, duration: float = 1.0) -> dict:
        event = make_event(60, 0.0, 1.0)
        candidate = DurationCandidate(duration, "key-release-grid", False, 0.5)
        return candidate_features(event, 1.0, 1.5, candidate, 1.0, 4.0)

    def test_training_features_are_subset_of_candidate_features(self):
        features = self._features()
        self.assertTrue(set(train_mod.FEATURES) <= set(features))

    def test_training_features_are_numeric_and_finite(self):
        features = self._features()
        for name in train_mod.FEATURES:
            with self.subTest(feature=name):
                self.assertIsInstance(features[name], (int, float))
                self.assertTrue(math.isfinite(float(features[name])))

    def test_candidate_source_kept_for_scoring_but_excluded_from_training(self):
        features = self._features()
        self.assertIn("candidate_source", features)
        self.assertNotIn("candidate_source", train_mod.FEATURES)
        self.assertIsInstance(features["candidate_source"], str)

    def test_feature_probability_matches_rule_probability(self):
        features = self._features()
        expected = candidate_probability(
            features["candidate_duration_ql"],
            features["key_duration_ql"],
            features["acoustic_duration_ql"],
            features["candidate_source"],
        )
        self.assertAlmostEqual(candidate_feature_probability(features), expected)

    def test_rule_probability_feature_is_exp_minus_score(self):
        features = self._features(duration=1.0)
        self.assertAlmostEqual(features["rule_probability"], math.exp(-0.5))

    def test_boolean_flags_are_ints(self):
        features = self._features()
        for name in ("candidate_crosses_barline", "candidate_has_barline",
                     "candidate_has_next_onset"):
            self.assertIsInstance(features[name], int)


class TestChordGroupDurationDecoding(unittest.TestCase):
    """同 voice、同起点事件必须以一个 MusicXML Chord 的时值联合解码。"""

    def test_measure_dp_selects_one_duration_for_all_chord_members(self):
        first = make_event(60, 0.0, 1.0)
        second = make_event(64, 0.0, 1.0)
        # 如果逐音独立选择，两个成员会分别偏好 0.5 和 1.0 QL；联合决策必须
        # 选择同一个离散时值，才能在导出层组成一个不重叠的 Chord。
        items = [
            (first, 1.0, 1.0, None, [
                DurationCandidate(0.5, "synthetic", False, 0.01),
                DurationCandidate(1.0, "synthetic", False, 0.80),
            ]),
            (second, 1.0, 1.0, None, [
                DurationCandidate(0.5, "synthetic", False, 0.80),
                DurationCandidate(1.0, "synthetic", False, 0.01),
            ]),
        ]
        _cost, choices = _decode_measure_dp(items, 0.0, 4.0)
        self.assertEqual(len(choices), 2)
        self.assertEqual(choices[0].duration_ql, choices[1].duration_ql)
        self.assertIn(choices[0].duration_ql, {0.5, 1.0})


class TestCandidateCsvSchema(unittest.TestCase):
    """候选 CSV 的 schema 一致性：表头覆盖 FEATURES，行结构统一，可回灌训练矩阵。"""

    @staticmethod
    def _write_table(tmp: str) -> Path:
        raw = [(60, 0.0, 1.0, 80), (62, 1.0, 0.5, 80)]
        out = Path(tmp) / "candidates.csv"
        write_candidate_table(raw, [(0.0, 1.5)], "RH", out, bar_ql=4.0)
        return out

    @staticmethod
    def _read_csv(path: Path) -> list[dict]:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_header_covers_training_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._read_csv(self._write_table(tmp))
        self.assertTrue(rows)
        header = set(rows[0])
        self.assertTrue(set(train_mod.FEATURES) <= header)
        self.assertIn("candidate_source", header)

    def test_all_rows_share_uniform_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._read_csv(self._write_table(tmp))
        reference = set(rows[0])
        for row in rows:
            with self.subTest(row=row):
                self.assertEqual(set(row), reference)

    def test_training_columns_are_float_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._read_csv(self._write_table(tmp))
        for row in rows:
            for name in train_mod.FEATURES:
                with self.subTest(feature=name):
                    float(row[name])  # 不应抛异常

    def test_matrix_round_trip_from_written_csv(self):
        """写出的 CSV 填上 0/1 标签后能直接构造训练矩阵（16 列）。"""
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._read_csv(self._write_table(tmp))
        for index, row in enumerate(rows):
            row["label"] = "1" if index % 2 == 0 else "0"
        x, y = train_mod._matrix(rows)
        self.assertEqual(len(y), len(rows))
        for vector in x:
            self.assertEqual(len(vector), len(train_mod.FEATURES))

    def test_build_dataset_csv_includes_annotation_columns(self):
        """P4d 数据管线 ``build_dataset`` 产出的 CSV 含复核标注列。"""
        with tempfile.TemporaryDirectory() as tmp:
            import pretty_midi

            midi_path = Path(tmp) / "tiny.mid"
            pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)
            instrument = pretty_midi.Instrument(program=0, name="Piano")
            beat = 60.0 / 90.0
            for pitch, start, dur in [
                (72, 0.0, 1.0), (74, 1.0, 1.0), (76, 2.0, 1.0),
                (48, 0.0, 2.0), (55, 2.0, 2.0),
            ]:
                instrument.notes.append(pretty_midi.Note(
                    velocity=80, pitch=pitch,
                    start=start * beat, end=(start + dur) * beat,
                ))
            pm.instruments.append(instrument)
            pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0.0))
            pm.write(str(midi_path))

            out = Path(tmp) / "dataset.csv"
            count = build_dataset(str(midi_path), str(out), "tiny")
            self.assertGreater(count, 0)
            rows = self._read_csv(out)
            self.assertTrue(rows)
            header = set(rows[0])
            self.assertTrue(set(train_mod.FEATURES) <= header)
            self.assertTrue(ANNOTATION_COLUMNS <= header)
            reference = set(rows[0])
            for row in rows:
                with self.subTest(row=row):
                    self.assertEqual(set(row), reference)


class TestReferenceScoreAutoLabeling(unittest.TestCase):
    """参考 MusicXML 的候选自动标签：只保留唯一、可达的参考时值。"""

    def test_identical_quantized_midi_notes_are_merged_before_candidate_generation(self):
        """重复 MIDI note 只产生一个可记谱事件，保留最高力度。"""
        events = [(58, 224.875, 0.125, 10), (58, 224.875, 0.125, 50),
                  (60, 225.0, 0.25, 80)]
        deduplicated, merged = _deduplicate_notation_events(events)
        self.assertEqual(merged, 1)
        self.assertEqual(deduplicated, [(58, 224.875, 0.125, 50), (60, 225.0, 0.25, 80)])

    def test_controlled_midi_xml_yields_consistent_event_labels(self):
        root = Path(__file__).resolve().parents[1]
        midi = root / "samples" / "test_performance.mid"
        xml = root / "samples" / "test_score.musicxml"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "auto_labeled.csv"
            stats = build_auto_labeled_dataset(str(midi), str(xml), str(out), "controlled")
            rows = TestCandidateCsvSchema._read_csv(out)
        self.assertEqual(stats["alignment_method"], "onset-controlled")
        self.assertGreater(stats.get("labeled", 0), 0)
        self.assertTrue(rows)
        header = set(rows[0])
        self.assertTrue({"candidate_event_id", "label_source", "auto_label_status",
                         "reference_part", "reference_voice", "reference_duration_ql"} <= header)
        labeled = [row for row in rows if row["auto_label_status"] == "labeled"]
        self.assertTrue(labeled)
        by_event = {}
        for row in labeled:
            by_event.setdefault(row["candidate_event_id"], []).append(row)
        for event_id, group in by_event.items():
            with self.subTest(event_id=event_id):
                self.assertEqual(sum(row["label"] == "1" for row in group), 1)
                self.assertTrue(all(row["label"] in {"0", "1"} for row in group))
        ambiguous = [row for row in rows if row["auto_label_status"] != "labeled"]
        self.assertTrue(all(row["label"] == "" for row in ambiguous))

    def test_reference_parser_returns_events_with_hand_and_voice(self):
        root = Path(__file__).resolve().parents[1]
        events = reference_score_events(root / "samples" / "test_score.musicxml")
        self.assertTrue(events)
        self.assertTrue(all(event.hand in {"RH", "LH"} for event in events))
        self.assertTrue(all(event.voice for event in events))
        self.assertTrue(all(event.duration_ql > 0 for event in events))

    @staticmethod
    def _write_single_note_midi(path: Path, duration_ql: float = 1.0) -> None:
        import pretty_midi

        pm = pretty_midi.PrettyMIDI(initial_tempo=60.0)
        piano = pretty_midi.Instrument(program=0, name="Piano")
        piano.notes.append(pretty_midi.Note(
            velocity=80, pitch=60, start=0.0, end=duration_ql,
        ))
        pm.instruments.append(piano)
        pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0.0))
        pm.write(str(path))

    @staticmethod
    def _write_single_note_xml(path: Path, duration_divisions: int = 4) -> None:
        path.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1"><measure number="1">
    <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>{duration_divisions}</duration><voice>1</voice><type>quarter</type></note>
  </measure></part>
</score-partwise>
''', encoding="utf-8")

    def test_external_alignment_labels_score_duration_not_key_release(self):
        """真实演奏必须用外部可靠对齐；标签取参考谱时值而非 MIDI note-off。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            midi = tmp_path / "performance.mid"
            xml = tmp_path / "reference.musicxml"
            alignment = tmp_path / "alignment.csv"
            out = tmp_path / "labeled.csv"
            self._write_single_note_midi(midi, duration_ql=2.0)
            self._write_single_note_xml(xml, duration_divisions=8)  # 参考符号时值为 2 QL
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8",
            )
            stats = build_auto_labeled_dataset(
                str(midi), str(xml), str(out), "external", alignment_path=str(alignment),
            )
            rows = TestCandidateCsvSchema._read_csv(out)
        self.assertEqual(stats["alignment_method"], "external")
        self.assertEqual(stats.get("labeled"), 1)
        self.assertEqual(sum(row["label"] == "1" for row in rows), 1)
        positive = next(row for row in rows if row["label"] == "1")
        self.assertAlmostEqual(float(positive["candidate_duration_ql"]), 2.0)
        self.assertEqual(positive["label_source"], "reference-score")
        x, y = train_mod._matrix(rows)
        self.assertEqual(len(x), len(rows))
        self.assertEqual(set(y), {0, 1})

    def test_reference_duration_outside_candidate_set_remains_unlabeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            midi = tmp_path / "performance.mid"
            xml = tmp_path / "reference.musicxml"
            alignment = tmp_path / "alignment.csv"
            out = tmp_path / "unlabeled.csv"
            self._write_single_note_midi(midi, duration_ql=1.0)
            self._write_single_note_xml(xml, duration_divisions=15)  # 3.75 QL 不在该事件候选集
            alignment.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8",
            )
            stats = build_auto_labeled_dataset(
                str(midi), str(xml), str(out), "outside", alignment_path=str(alignment),
            )
            rows = TestCandidateCsvSchema._read_csv(out)
        self.assertEqual(stats.get("reference-duration-not-candidate"), 1)
        self.assertTrue(rows)
        self.assertTrue(all(row["auto_label_status"] == "reference-duration-not-candidate" for row in rows))
        self.assertTrue(all(row["label"] == "" for row in rows))
        x, y = train_mod._matrix(rows)
        self.assertEqual((x, y), ([], []))

    def test_reference_parser_accumulates_variable_measure_lengths(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "meter_change.musicxml"
            xml.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice></note>
    </measure>
    <measure number="2"><note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice></note></measure>
  </part>
</score-partwise>
''', encoding="utf-8")
            events = reference_score_events(xml)
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[1].start_ql, 3.0)

    def test_alignment_reader_rejects_missing_columns_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing = tmp_path / "missing.csv"
            duplicate = tmp_path / "duplicate.csv"
            missing.write_text("hand,pitch,onset_ql\nRH,60,0\n", encoding="utf-8")
            duplicate.write_text(
                "hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql\n"
                "RH,60,0,P1,1,60,0\n"
                "RH,60,0,P1,1,60,0\n", encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                _read_alignment(missing)
            with self.assertRaises(ValueError):
                _read_alignment(duplicate)

    def test_auto_labels_train_and_score_when_lightgbm_available(self):
        try:
            import lightgbm  # noqa: F401
        except ImportError:
            self.skipTest("未安装 LightGBM；自动标签 CSV 的矩阵兼容性已由其他测试覆盖")
        root = Path(__file__).resolve().parents[1]
        midi = root / "samples" / "test_performance.mid"
        xml = root / "samples" / "test_score.musicxml"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            candidates = tmp_path / "auto_labeled.csv"
            model = tmp_path / "candidate_model"
            stats = build_auto_labeled_dataset(str(midi), str(xml), str(candidates), "controlled")
            self.assertGreater(stats.get("labeled", 0), 0)
            count = train_model([candidates], model)
            scorer = probability_from_model(model)
            rows = TestCandidateCsvSchema._read_csv(candidates)
        self.assertGreater(count, 1)
        self.assertNotEqual(scorer, train_mod.candidate_probability)
        probabilities = scorer.score_rows(rows)
        self.assertEqual(len(probabilities), len(rows))
        self.assertTrue(all(0.0 < probability < 1.0 for probability in probabilities))

    def test_reference_parser_merges_cross_measure_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "tied.musicxml"
            xml.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Right Hand</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1"><attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>2</voice><tie type="start"/></note>
    </measure>
    <measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>2</voice><tie type="stop"/></note></measure>
  </part>
</score-partwise>
''', encoding="utf-8")
            events = reference_score_events(xml)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.part_id, event.voice, event.pitch), ("P1", "2", 60))
        self.assertAlmostEqual(event.start_ql, 0.0)
        self.assertAlmostEqual(event.duration_ql, 5.0)
        self.assertTrue(event.tie_start)
        self.assertTrue(event.tie_stop)


class TestMeasureDpHardConstraints(unittest.TestCase):
    """measure DP 的“同 voice 下一起音”硬约束与同 voice 不重叠保证。"""

    def test_next_onset_is_hard_boundary_despite_acoustic_extension(self):
        # 踏板把声学时值延长到 1.5，但同 voice 下一起音在 1.0 —— 合法候选必须被裁剪。
        base = [make_event(60, 0.0, 1.0), make_event(62, 1.0, 0.5)]
        items = _candidate_sets(base, [(0.0, 1.5)], 4.0, (8, 4, 3), None)
        event, key_duration, acoustic, next_onset, legal = items[0]
        self.assertEqual(event.pitch, 60)
        self.assertEqual(next_onset, 1.0)
        self.assertGreater(acoustic, 1.0)  # 声学证据越过下一起音
        ranked = rank_candidates(event.start_ql, key_duration, acoustic,
                                 next_onset, 4.0, (8, 4, 3))
        self.assertTrue(any(c.duration_ql > 1.0 + EPS for c in ranked))
        self.assertTrue(legal)
        self.assertTrue(all(c.duration_ql <= 1.0 + EPS for c in legal))

    def test_decode_hand_no_overlap_and_respects_next_onset(self):
        raw = [(60, 0.0, 1.0, 80), (62, 1.0, 1.0, 80), (64, 2.0, 1.0, 80),
               (65, 3.0, 1.0, 80), (67, 4.0, 1.0, 80)]
        decoded = decode_hand(raw, [(0.0, 6.0)], "RH", bar_ql=4.0, divisors=(8, 4, 3))
        validate_voice_events(decoded)  # 不抛异常即满足同 voice 不重叠
        by_voice: dict[int, list[VoiceEvent]] = {}
        for event in decoded:
            by_voice.setdefault(event.voice, []).append(event)
        for voice, stream_events in by_voice.items():
            onsets = sorted({e.start_ql for e in stream_events})
            for event in stream_events:
                next_onset = next((o for o in onsets if o > event.start_ql + EPS), None)
                if next_onset is not None:
                    self.assertLessEqual(event.end_ql, next_onset + EPS)

    def test_multivoice_sustain_not_truncated_by_other_voice(self):
        # 60 长音与 62 后续音分属不同 voice：持续音完整保留，且各自 voice 内不重叠。
        raw = [(60, 0.0, 2.0, 80), (62, 1.0, 1.0, 80), (64, 2.0, 1.0, 80)]
        decoded = decode_hand(raw, [], "RH", bar_ql=4.0, divisors=(8, 4, 3))
        validate_voice_events(decoded)
        sustained = next(e for e in decoded if e.pitch == 60)
        inner = next(e for e in decoded if e.pitch == 62)
        self.assertAlmostEqual(sustained.duration_ql, 2.0)
        self.assertNotEqual(sustained.voice, inner.voice)

    def test_cross_barline_tie_preserved_by_measure_dp(self):
        # 3.5QL 起的长音可跨 4.0 小节线：DP 应选出 tie 候选而非退化为小节内短音。
        raw = [(60, 3.5, 1.0, 80), (62, 4.0, 1.0, 80)]
        decoded = decode_hand(raw, [], "RH", bar_ql=4.0, divisors=(8, 4, 3))
        validate_voice_events(decoded)
        sustained = next(e for e in decoded if e.pitch == 60)
        self.assertAlmostEqual(sustained.duration_ql, 1.0)
        self.assertAlmostEqual(sustained.end_ql, 4.5)

    def test_dp_returns_one_choice_per_event_within_next_onset(self):
        base = [make_event(60, 0.0, 1.0), make_event(62, 1.0, 0.5),
                make_event(64, 1.5, 0.5)]
        items = _candidate_sets(base, [], 4.0, (8, 4, 3), None)
        self.assertEqual(len(items), 3)
        by_pitch = {event.pitch: (event, next_onset, legal)
                    for event, _key, _ac, next_onset, legal in items}
        self.assertEqual(by_pitch[62][1], 1.5)  # 62 的下一起音是 64
        cost, choices = _decode_measure_dp(items, 0.0, 4.0)
        self.assertEqual(len(choices), len(items))
        self.assertIsInstance(cost, float)
        for (event, _key, _ac, next_onset, legal), choice in zip(items, choices):
            self.assertIn(choice, legal)
            if next_onset is not None:
                self.assertLessEqual(event.start_ql + choice.duration_ql,
                                     next_onset + EPS)

    def test_validate_rejects_overlap_within_voice(self):
        bad = [make_event(60, 0.0, 1.0), make_event(62, 0.5, 0.5)]
        with self.assertRaises(ValueError):
            validate_voice_events(bad)


if __name__ == "__main__":
    unittest.main()
