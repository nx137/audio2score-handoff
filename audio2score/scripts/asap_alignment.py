#!/usr/bin/env python3
"""将 ASAP 的节拍对齐标注转换为 P4 候选自动标签所需的外部对齐 CSV。

ASAP 的 MusicXML 与演奏 MIDI 不共用 QL 时间轴。此脚本不做简单的同起音猜测，而是：

1. 用 ASAP 的逐拍标注把每个演奏 MIDI note-on 映射到 score MIDI 的秒时间；
2. 在 score MIDI 中只保留唯一的同音高、近邻起音匹配；
3. 用 score MIDI 的 tick/PPQ 位置回接参考 MusicXML 的真实事件；
4. 只将唯一的演奏事件—参考谱事件对应写入外部 alignment CSV。

不完整演奏、缺失标注、同音高重复起音和超出容差的对应都会写入拒绝表，绝不伪造
金标准。输出 CSV 可直接传给 ``auto_label_candidates.py --alignment``。
"""
from __future__ import annotations

import argparse
import csv
import json
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

import pretty_midi

from auto_label_candidates import ReferenceEvent, reference_score_events
from midi_to_score import midi_to_events, quantize_events, split_hands

EPS = 1e-7


class AlignmentError(ValueError):
    """ASAP 条目的结构或对齐信息不满足训练使用条件。"""


def _annotations_for(asap_root: Path, performance_rel: str,
                    annotations_rel: str = "asap_annotations.json") -> dict:
    annotations_path = asap_root / annotations_rel
    data = json.loads(annotations_path.read_text(encoding="utf-8"))
    try:
        return data[performance_rel]
    except KeyError as exc:
        raise AlignmentError(f"注释 JSON 中找不到演奏：{performance_rel}") from exc


def _interpolate(value: float, source: list[float], target: list[float]) -> float | None:
    """按同一拍序号在两个时间轴之间分段线性插值；端点之外不外推。"""
    if len(source) != len(target) or len(source) < 2:
        return None
    if value < source[0] - EPS or value > source[-1] + EPS:
        return None
    index = bisect_right(source, value) - 1
    index = min(max(index, 0), len(source) - 2)
    left, right = source[index], source[index + 1]
    if right - left <= EPS:
        return None
    ratio = (value - left) / (right - left)
    return target[index] + ratio * (target[index + 1] - target[index])


def _midi_notes_with_ql(path: Path) -> list[tuple[int, float, float]]:
    """读取 (pitch, seconds, exact-MIDI-QL)；QL 从 tick/PPQ 得到，不依赖瞬时速度。"""
    pm = pretty_midi.PrettyMIDI(str(path))
    notes = []
    for instrument in pm.instruments:
        for note in instrument.notes:
            ql = float(pm.time_to_tick(note.start)) / pm.resolution
            notes.append((note.pitch, note.start, ql))
    return sorted(notes, key=lambda row: (row[1], row[0]))


def _unique_nearest(candidates, expected: float, tolerance: float, value):
    """在容差内取唯一最近候选；并列最近或不存在均明确拒绝。"""
    matches = [item for item in candidates if abs(value(item) - expected) <= tolerance]
    if not matches:
        return None, "no-match"
    best_distance = min(abs(value(item) - expected) for item in matches)
    winners = [item for item in matches
               if abs(abs(value(item) - expected) - best_distance) <= EPS]
    if len(winners) != 1:
        return None, "ambiguous"
    return winners[0], "matched"


def _reference_index(events: list[ReferenceEvent]):
    index = defaultdict(list)
    for event in events:
        index[event.pitch].append(event)
    return index


def build_asap_alignment(asap_root: str | Path, performance_rel: str, output_path: str | Path,
                         rejected_path: str | Path | None = None,
                         score_note_tolerance_sec: float = 0.08,
                         xml_note_tolerance_ql: float = 0.125,
                         divisors=(8, 4, 3), max_events: int | None = None,
                         annotations_rel: str = "asap_annotations.json") -> dict:
    """为一个 ASAP 演奏生成保守外部对齐 CSV，并返回可追溯统计。"""
    root = Path(asap_root)
    metadata_path = root / "metadata.csv"
    with metadata_path.open(encoding="utf-8", newline="") as handle:
        metadata = list(csv.DictReader(handle))
    rows = [row for row in metadata if row["midi_performance"] == performance_rel]
    if len(rows) != 1:
        raise AlignmentError(f"metadata.csv 中演奏条目数应为 1，实际为 {len(rows)}：{performance_rel}")
    item = rows[0]
    annotations = _annotations_for(root, performance_rel, annotations_rel)
    if not annotations.get("score_and_performance_aligned", False):
        raise AlignmentError("ASAP 标注声明该演奏与参考谱未完整对齐，不能用于 P4 自动监督")
    perf_beats = [float(value) for value in annotations["performance_beats"]]
    score_beats = [float(value) for value in annotations["midi_score_beats"]]
    if len(perf_beats) != len(score_beats) or len(perf_beats) < 2:
        raise AlignmentError("ASAP 演奏/参考谱节拍标注长度不一致或不足两个点")

    performance_path = root / item["midi_performance"]
    score_midi_path = root / item["midi_score"]
    xml_path = root / item["xml_score"]
    for path in (performance_path, score_midi_path, xml_path):
        if not path.exists():
            raise AlignmentError(f"ASAP 条目缺少文件：{path}")

    raw_notes, _pedals, _meta = midi_to_events(str(performance_path))
    qnotes = quantize_events(raw_notes, divisors=divisors)
    rh, lh = split_hands(qnotes)
    performance_events = [("RH", pitch, onset) for pitch, onset, _duration, _velocity in rh]
    performance_events += [("LH", pitch, onset) for pitch, onset, _duration, _velocity in lh]
    # midi_to_events 的 QL 使用首个速度；显式记录并以同一规则回接量化事件。
    perf_pm = pretty_midi.PrettyMIDI(str(performance_path))
    first_tempo = float(perf_pm.get_tempo_changes()[1][0])
    seconds_per_ql = 60.0 / first_tempo
    # ``quantize_events`` 会移动 onset，不能把量化 onset 当作原始事件键。按同 pitch
    # 的最近原始 onset 回接秒时间；若最近项并列则明确拒绝。
    raw_by_pitch = defaultdict(list)
    for pitch, start_ql, _duration, _velocity in raw_notes:
        raw_by_pitch[pitch].append((start_ql, start_ql * seconds_per_ql))

    score_by_pitch = defaultdict(list)
    for pitch, seconds, ql in _midi_notes_with_ql(score_midi_path):
        score_by_pitch[pitch].append((pitch, seconds, ql))
    reference_by_pitch = _reference_index(reference_score_events(xml_path))

    accepted, rejected, stats = [], [], Counter()
    seen_alignment_keys = set()
    ordered_events = sorted(performance_events, key=lambda row: (row[2], row[0], row[1]))
    if max_events is not None:
        if max_events <= 0:
            raise AlignmentError("max_events 必须为正整数")
        ordered_events = ordered_events[:max_events]
        stats["input-events-truncated"] = len(performance_events) - len(ordered_events)
    for hand, pitch, onset_ql in ordered_events:
        key = (hand, pitch, round(onset_ql, 6))
        raw_matches = raw_by_pitch.get(pitch, [])
        if not raw_matches:
            rejected.append({"hand": hand, "pitch": pitch, "onset_ql": onset_ql,
                             "reason": "missing-raw-performance-event"})
            stats["missing-raw-performance-event"] += 1
            continue
        best_gap = min(abs(raw_ql - onset_ql) for raw_ql, _seconds in raw_matches)
        nearest = [(raw_ql, seconds) for raw_ql, seconds in raw_matches
                   if abs(abs(raw_ql - onset_ql) - best_gap) <= EPS]
        if len(nearest) != 1:
            rejected.append({"hand": hand, "pitch": pitch, "onset_ql": onset_ql,
                             "reason": "ambiguous-quantized-performance-event"})
            stats["ambiguous-quantized-performance-event"] += 1
            continue
        expected_score_sec = _interpolate(nearest[0][1], perf_beats, score_beats)
        if expected_score_sec is None:
            rejected.append({"hand": hand, "pitch": pitch, "onset_ql": onset_ql,
                             "reason": "outside-or-invalid-beat-map"})
            stats["outside-or-invalid-beat-map"] += 1
            continue
        score_note, reason = _unique_nearest(
            score_by_pitch[pitch], expected_score_sec, score_note_tolerance_sec,
            lambda item: item[1],
        )
        if score_note is None:
            rejected.append({"hand": hand, "pitch": pitch, "onset_ql": onset_ql,
                             "reason": f"score-midi-{reason}"})
            stats[f"score-midi-{reason}"] += 1
            continue
        reference_event, reason = _unique_nearest(
            reference_by_pitch[pitch], score_note[2], xml_note_tolerance_ql,
            lambda item: item.start_ql,
        )
        if reference_event is None:
            rejected.append({"hand": hand, "pitch": pitch, "onset_ql": onset_ql,
                             "reason": f"musicxml-{reason}"})
            stats[f"musicxml-{reason}"] += 1
            continue
        alignment_key = (hand, pitch, round(onset_ql, 6))
        if alignment_key in seen_alignment_keys:
            rejected.append({"hand": hand, "pitch": pitch, "onset_ql": onset_ql,
                             "reason": "duplicate-alignment-key"})
            stats["duplicate-alignment-key"] += 1
            continue
        seen_alignment_keys.add(alignment_key)
        accepted.append({
            "hand": hand,
            "pitch": pitch,
            "onset_ql": f"{onset_ql:.6f}",
            "reference_part": reference_event.part_id,
            "reference_voice": reference_event.voice,
            "reference_pitch": reference_event.pitch,
            "reference_onset_ql": f"{reference_event.start_ql:.6f}",
        })
        stats["aligned"] += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["hand", "pitch", "onset_ql", "reference_part", "reference_voice",
               "reference_pitch", "reference_onset_ql"]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(accepted)
    if rejected_path:
        rejected_output = Path(rejected_path)
        rejected_output.parent.mkdir(parents=True, exist_ok=True)
        with rejected_output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["hand", "pitch", "onset_ql", "reason"])
            writer.writeheader()
            writer.writerows(rejected)
    return {
        "performance": performance_rel,
        "rows": len(accepted),
        "rejected": len(rejected),
        "score_note_tolerance_sec": score_note_tolerance_sec,
        "xml_note_tolerance_ql": xml_note_tolerance_ql,
        **dict(stats),
    }


def main():
    parser = argparse.ArgumentParser(description="把 ASAP 节拍标注转换为 P4 外部对齐 CSV")
    parser.add_argument("--asap-root", required=True, help="ASAP 数据集根目录")
    parser.add_argument("--performance", required=True, help="metadata.csv 内 midi_performance 相对路径")
    parser.add_argument("--out", required=True, help="外部对齐 CSV 输出路径")
    parser.add_argument("--rejected-out", help="被保守拒绝的事件 CSV 输出路径")
    parser.add_argument("--score-note-tolerance-sec", type=float, default=0.08)
    parser.add_argument("--xml-note-tolerance-ql", type=float, default=0.125)
    parser.add_argument("--max-events", type=int,
                        help="仅处理按起音排序后的前 N 个量化事件；用于小规模管线试运行")
    args = parser.parse_args()
    stats = build_asap_alignment(
        args.asap_root, args.performance, args.out, args.rejected_out,
        args.score_note_tolerance_sec, args.xml_note_tolerance_ql,
        max_events=args.max_events,
    )
    print("；".join(f"{key}={value}" for key, value in stats.items()))


if __name__ == "__main__":
    main()
