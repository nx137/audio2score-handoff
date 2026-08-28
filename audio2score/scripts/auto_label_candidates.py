#!/usr/bin/env python3
"""P4d：用对齐的参考 MusicXML 为演奏 MIDI 候选时值自动打标。

该模块严格区分两件事：

* ``reference_score_events`` 从参考谱读取符号时值、voice 和 tie 合并后的事件；
* ``build_auto_labeled_dataset`` 只在演奏音与参考谱音已有可靠对齐时写入 0/1 标签。

默认 ``onset`` 对齐仅适用于演奏 MIDI 与参考谱共用 QL 时间轴的受控样例。真实演奏
（如 ASAP）必须传入外部对齐表；没有唯一、高置信度对齐的事件保留空 ``label``，而不
把启发式结果伪装成金标准。
"""
from __future__ import annotations

import argparse
import csv
import math
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from analyze_pedal_durations import build_records
from midi_to_score import midi_to_events, quantize_events, split_hands
from reconcile_midi_xml import STEP_SEMIS
from structured_duration_decoder import _candidate_sets, assign_voices, candidate_features

EPS = 1e-7


@dataclass(frozen=True)
class ReferenceEvent:
    pitch: int
    start_ql: float
    duration_ql: float
    part_id: str
    voice: str
    hand: str
    tie_start: bool
    tie_stop: bool


def _pitch(note_el: ET.Element) -> int | None:
    pitch = note_el.find("pitch")
    if pitch is None:
        return None
    step = pitch.findtext("step")
    octave = pitch.findtext("octave")
    if step not in STEP_SEMIS or octave is None:
        return None
    alter = int(pitch.findtext("alter") or 0)
    return (int(octave) + 1) * 12 + STEP_SEMIS[step] + alter


def _part_hands(root: ET.Element) -> dict[str, str | None]:
    """按 part-name 推断双手；无法确认时由音高回退。"""
    out = {}
    for score_part in root.findall("part-list/score-part"):
        name = (score_part.findtext("part-name") or "").lower()
        part_id = score_part.get("id") or ""
        if any(token in name for token in ("r.h", "right", "rh")):
            out[part_id] = "RH"
        elif any(token in name for token in ("l.h", "left", "lh")):
            out[part_id] = "LH"
        else:
            out[part_id] = None
    return out


def reference_score_events(xml_path: str | Path) -> list[ReferenceEvent]:
    """读取 MusicXML 的真实音符事件，并按 ``part + voice + pitch`` 合并 tie 链。"""
    root = ET.parse(str(xml_path)).getroot()
    hands = _part_hands(root)
    events: list[list] = []
    open_ties: dict[tuple[str, str, int], int] = {}
    output: list[ReferenceEvent] = []

    for part_index, part in enumerate(root.findall("part")):
        part_id = part.get("id") or str(part_index)
        divisions = None
        bar_ql = 4.0
        measure_start = 0.0
        for measure in part.findall("measure"):
            cursor = 0.0
            last_start = 0.0
            for child in measure:
                if child.tag == "attributes":
                    div = child.findtext("divisions")
                    if div:
                        divisions = int(div)
                    beats = child.findtext("time/beats")
                    beat_type = child.findtext("time/beat-type")
                    if beats and beat_type:
                        bar_ql = 4.0 * float(beats) / float(beat_type)
                    continue
                if child.tag == "backup" and divisions:
                    cursor -= int(child.findtext("duration") or 0) / divisions
                    continue
                if child.tag == "forward" and divisions:
                    cursor += int(child.findtext("duration") or 0) / divisions
                    continue
                if child.tag != "note" or divisions is None or child.find("grace") is not None:
                    continue
                duration = int(child.findtext("duration") or 0) / divisions
                is_chord = child.find("chord") is not None
                start = last_start if is_chord else cursor
                pitch = _pitch(child)
                if pitch is not None:
                    voice = child.findtext("voice") or "1"
                    stream_key = (part_id, voice, pitch)
                    tie_types = {tie.get("type") for tie in child.findall("tie")}
                    has_start = "start" in tie_types
                    has_stop = "stop" in tie_types
                    absolute = measure_start + start
                    existing = open_ties.get(stream_key)
                    if has_stop and existing is not None:
                        events[existing][2] = absolute + duration - events[existing][1]
                        events[existing][7] = True
                        if not has_start:
                            del open_ties[stream_key]
                    else:
                        index = len(events)
                        events.append([pitch, absolute, duration, part_id, voice,
                                       hands.get(part_id), has_start, has_stop])
                        if has_start:
                            open_ties[stream_key] = index
                if not is_chord:
                    last_start = cursor
                    cursor += duration
            measure_start += bar_ql

    for pitch, start, duration, part_id, voice, hand, tie_start, tie_stop in events:
        resolved_hand = hand or ("RH" if pitch >= 60 else "LH")
        output.append(ReferenceEvent(pitch, round(start, 9), round(duration, 9), part_id,
                                     voice, resolved_hand, tie_start, tie_stop))
    return sorted(output, key=lambda item: (item.hand, item.start_ql, item.pitch, item.voice))


def _read_alignment(path: str | Path) -> dict[tuple[str, int, float], tuple[str, str, int, float]]:
    """读取显式对齐 CSV。

    必需列：``hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,
    reference_onset_ql``。一行定义一个量化演奏事件与一个参考谱事件的可靠对应。
    """
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"hand", "pitch", "onset_ql", "reference_part", "reference_voice",
                "reference_pitch", "reference_onset_ql"}
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"对齐 CSV 缺少列：{sorted(missing)}")
    result = {}
    for row in rows:
        key = (row["hand"], int(row["pitch"]), round(float(row["onset_ql"]), 6))
        value = (row["reference_part"], row["reference_voice"], int(row["reference_pitch"]),
                 round(float(row["reference_onset_ql"]), 6))
        if key in result:
            raise ValueError(f"对齐 CSV 含重复演奏事件：{key}")
        result[key] = value
    return result


def _deduplicate_notation_events(events):
    """合并 MIDI 中无法在符号谱区分的完全重叠重复音。

    同一手内相同音高、量化起音和量化键盘时值的多条 MIDI note 不能构成
    有意义的双音；保留力度最高的一条，既避免重复候选行，也不丢失可记谱信息。
    返回 ``(events, merged_count)``，供批处理汇总审计。
    """
    selected = {}
    for pitch, onset, duration, velocity in events:
        key = (pitch, round(onset, 9), round(duration, 9))
        previous = selected.get(key)
        if previous is None or velocity > previous[3]:
            selected[key] = (pitch, onset, duration, velocity)
    deduplicated = sorted(selected.values(), key=lambda item: (item[1], item[0], -item[2], -item[3]))
    return deduplicated, len(events) - len(deduplicated)


def _onset_alignment(performance, reference, onset_tolerance: float) -> dict:
    """受控样例的保守同音高/同起音对齐；存在歧义的项不返回。"""
    reference_by_key = defaultdict(list)
    for item in reference:
        reference_by_key[(item.hand, item.pitch)].append(item)
    aligned = {}
    for hand, pitch, onset in performance:
        matches = [item for item in reference_by_key[(hand, pitch)]
                   if abs(item.start_ql - onset) <= onset_tolerance]
        if len(matches) == 1:
            item = matches[0]
            aligned[(hand, pitch, round(onset, 6))] = (
                item.part_id, item.voice, item.pitch, round(item.start_ql, 6)
            )
    return aligned


def build_auto_labeled_dataset(midi_path: str, reference_xml_path: str, output_path: str,
                               piece: str, alignment_path: str | None = None,
                               divisors=(8, 4, 3), max_voices=6, bar_ql=4.0,
                               onset_tolerance=0.125, duration_tolerance=0.125,
                               window=None) -> dict:
    """构建附带参考谱标签的候选表，并返回统计。

    每个唯一对齐事件至多标记一个候选为 ``label=1``。若参考时值未落入当前候选集、
    对齐缺失或候选并列，标签保持空，记录具体 ``auto_label_status``。
    """
    notes, pedals, _meta = midi_to_events(midi_path)
    if window is not None:
        lo, hi = window
        notes = [n for n in notes if lo <= n[1] < hi]
    qnotes = quantize_events(notes, divisors=divisors)
    rh, lh = split_hands(qnotes)
    rh, rh_merged = _deduplicate_notation_events(rh)
    lh, lh_merged = _deduplicate_notation_events(lh)
    merged_duplicate_events = rh_merged + lh_merged
    records = build_records(midi_path, divisors=divisors, window=window)
    by_record = {(row.hand, row.pitch, round(row.onset_ql, 6)): row for row in records}
    reference = reference_score_events(reference_xml_path)
    reference_index = {(event.part_id, event.voice, event.pitch, round(event.start_ql, 6)): event
                       for event in reference}
    if alignment_path:
        alignment = _read_alignment(alignment_path)
        alignment_method = "external"
    else:
        performance = [(hand, pitch, onset) for hand, events in (("RH", rh), ("LH", lh))
                       for pitch, onset, _duration, _velocity in events]
        alignment = _onset_alignment(performance, reference, onset_tolerance)
        alignment_method = "onset-controlled"

    rows = []
    stats = Counter()
    for hand, raw_events in (("RH", rh), ("LH", lh)):
        base = assign_voices(raw_events, hand=hand, max_voices=max_voices)
        for event, key_duration, acoustic_duration, next_onset, candidates in _candidate_sets(
                base, pedals, bar_ql, divisors, None):
            event_key = (hand, event.pitch, round(event.start_ql, 6))
            ref_key = alignment.get(event_key)
            reference_event = reference_index.get(ref_key) if ref_key else None
            # 防御性去重：同一离散时值即使由重复网格路径提出，亦只保留一个候选。
            # 这保证每个自动监督事件最多有一个正例。
            unique_candidates = {}
            for candidate in candidates:
                candidate_key = round(candidate.duration_ql, 9)
                previous = unique_candidates.get(candidate_key)
                if previous is None or candidate.score < previous.score:
                    unique_candidates[candidate_key] = candidate
            candidates = sorted(unique_candidates.values(), key=lambda candidate: candidate.score)
            matching = []
            if reference_event:
                matching = [candidate for candidate in candidates
                            if abs(candidate.duration_ql - reference_event.duration_ql)
                            <= duration_tolerance]
            # 去重后的候选集合中，只有唯一候选落在时值容差内才可监督；
            # 多个不同离散时值同样接近参考值时，标签必须保持为空。
            if len(matching) == 1:
                matched_duration = round(matching[0].duration_ql, 9)
                status = "labeled"
            elif reference_event and not matching:
                matched_duration = None
                status = "reference-duration-not-candidate"
            elif reference_event:
                matched_duration = None
                status = "ambiguous-candidate"
            else:
                matched_duration = None
                status = "unmatched"
            stats[status] += 1
            record = by_record.get(event_key)
            priority = ("high" if record and record.truncated_by_current_single_voice else
                        "medium" if acoustic_duration - key_duration > 0.25 else "normal")
            event_id = f"{piece}:{hand}:{event.pitch}:{event.start_ql:.6f}:{event.voice}"
            for candidate in candidates:
                row = candidate_features(event, key_duration, acoustic_duration, candidate,
                                         next_onset, bar_ql)
                row.update({
                    "piece": piece,
                    "hand": hand,
                    "candidate_event_id": event_id,
                    "review_priority": priority,
                    "label": "1" if matched_duration is not None and
                             round(candidate.duration_ql, 9) == matched_duration else
                             "0" if matched_duration is not None else "",
                    "label_source": "reference-score" if matched_duration is not None else "",
                    "auto_label_status": status,
                    "alignment_method": alignment_method,
                    "reference_part": reference_event.part_id if reference_event else "",
                    "reference_voice": reference_event.voice if reference_event else "",
                    "reference_onset_ql": reference_event.start_ql if reference_event else "",
                    "reference_duration_ql": reference_event.duration_ql if reference_event else "",
                    "reference_tie_start": int(reference_event.tie_start) if reference_event else "",
                    "reference_tie_stop": int(reference_event.tie_stop) if reference_event else "",
                    "review_class": "",
                    "review_note": "",
                })
                rows.append(row)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows), "events": sum(stats.values()), "alignment_method": alignment_method,
            "merged_duplicate_events": merged_duplicate_events, **dict(stats)}


def main():
    parser = argparse.ArgumentParser(description="P4 用参考 MusicXML 自动构造候选标签")
    parser.add_argument("--midi", required=True, help="演奏 MIDI")
    parser.add_argument("--reference-xml", required=True, help="参考 MusicXML")
    parser.add_argument("--out", required=True, help="候选级 CSV 输出")
    parser.add_argument("--piece", required=True)
    parser.add_argument("--alignment", help="真实演奏的外部可靠对齐 CSV；省略仅用于共用 QL 时间轴的受控样例")
    parser.add_argument("--bar-ql", type=float, default=4.0)
    parser.add_argument("--max-voices", type=int, default=6)
    args = parser.parse_args()
    stats = build_auto_labeled_dataset(args.midi, args.reference_xml, args.out, args.piece,
                                       args.alignment, max_voices=args.max_voices,
                                       bar_ql=args.bar_ql)
    print("；".join(f"{key}={value}" for key, value in stats.items()))


if __name__ == "__main__":
    main()
