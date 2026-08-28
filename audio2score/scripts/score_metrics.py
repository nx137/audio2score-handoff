#!/usr/bin/env python3
"""C 阶段：以可靠外部对齐为前提的 MusicXML 相对参考谱评分。

本模块评估的是系统 MusicXML 与参考 MusicXML 的符号一致性，而非 MIDI note-off
或踏板造成的声学延长。每个被纳入的参考事件必须先由 ASAP 外部对齐 CSV 唯一关联到
输入演奏；无法可靠映射的参考事件不进入分母，并在结果中明确报告。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from auto_label_candidates import ReferenceEvent, _read_alignment, reference_score_events

EPS = 1e-9


@dataclass(frozen=True)
class PedalEvent:
    hand: str
    position_ql: float
    event_type: str


def _f1(tp: int, predicted: int, reference: int) -> dict:
    precision = tp / predicted if predicted else 0.0
    recall = tp / reference if reference else 0.0
    return {
        "tp": tp,
        "predicted": predicted,
        "reference": reference,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _part_hands(root: ET.Element) -> dict[str, str | None]:
    out = {}
    for item in root.findall("part-list/score-part"):
        name = (item.findtext("part-name") or "").lower()
        part_id = item.get("id") or ""
        if any(token in name for token in ("r.h", "right", "rh")):
            out[part_id] = "RH"
        elif any(token in name for token in ("l.h", "left", "lh")):
            out[part_id] = "LH"
        else:
            out[part_id] = None
    return out


def pedal_events(xml_path: str | Path) -> list[PedalEvent]:
    """读取 MusicXML pedal start/change/stop，并将同位 stop/start 规范化为 change。"""
    root = ET.parse(str(xml_path)).getroot()
    hands = _part_hands(root)
    result = []
    for part_index, part in enumerate(root.findall("part")):
        part_id = part.get("id") or str(part_index)
        hand = hands.get(part_id) or "LH"
        divisions = None
        measure_start = 0.0
        bar_ql = 4.0
        for measure in part.findall("measure"):
            cursor = 0.0
            for child in measure:
                if child.tag == "attributes":
                    div = child.findtext("divisions")
                    if div:
                        divisions = int(div)
                    beats, beat_type = child.findtext("time/beats"), child.findtext("time/beat-type")
                    if beats and beat_type:
                        bar_ql = 4 * float(beats) / float(beat_type)
                elif child.tag == "backup" and divisions:
                    cursor -= int(child.findtext("duration") or 0) / divisions
                elif child.tag == "forward" and divisions:
                    cursor += int(child.findtext("duration") or 0) / divisions
                elif child.tag == "direction":
                    pedal = child.find("direction-type/pedal")
                    if pedal is not None:
                        offset = child.findtext("offset")
                        local = cursor + (int(offset) / divisions if offset and divisions else 0.0)
                        event_type = pedal.get("type")
                        if event_type in {"start", "change", "stop"}:
                            result.append(PedalEvent(hand, round(measure_start + local, 9), event_type))
                elif child.tag == "note" and divisions and child.find("chord") is None:
                    cursor += int(child.findtext("duration") or 0) / divisions
            measure_start += bar_ql
    grouped = defaultdict(list)
    for event in result:
        grouped[(event.hand, round(event.position_ql, 9))].append(event.event_type)
    normalized = []
    for (hand, position), types in grouped.items():
        if "change" in types or ("stop" in types and "start" in types):
            normalized.append(PedalEvent(hand, position, "change"))
            types = [item for item in types if item not in {"stop", "start", "change"}]
        normalized.extend(PedalEvent(hand, position, item) for item in types)
    return sorted(normalized, key=lambda item: (item.hand, item.position_ql, item.event_type))


def _anchors(alignment: dict) -> dict[str, list[tuple[float, float]]]:
    """从可靠音符对齐得到演奏 QL→参考 QL 的单调分段线性锚点。"""
    by_hand = defaultdict(set)
    for (hand, _pitch, onset), (_part, _voice, _ref_pitch, ref_onset) in alignment.items():
        by_hand[hand].add((float(onset), float(ref_onset)))
    return {hand: sorted(points) for hand, points in by_hand.items() if points}


def _map_position(value: float, points: list[tuple[float, float]]) -> float | None:
    if not points:
        return None
    if len(points) == 1:
        left_x, left_y = points[0]
        return left_y if abs(value - left_x) <= EPS else None
    if value < points[0][0] - EPS or value > points[-1][0] + EPS:
        return None
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x - EPS <= value <= right_x + EPS:
            if right_x - left_x <= EPS:
                continue
            ratio = (value - left_x) / (right_x - left_x)
            return left_y + ratio * (right_y - left_y)
    return points[-1][1] if abs(value - points[-1][0]) <= EPS else None


def _reference_subset(reference: list[ReferenceEvent], alignment: dict) -> list[ReferenceEvent]:
    index = {(event.part_id, event.voice, event.pitch, round(event.start_ql, 6)): event
             for event in reference}
    selected = {}
    for ref_key in alignment.values():
        event = index.get(ref_key)
        if event:
            selected[ref_key] = event
    return sorted(selected.values(), key=lambda event: (event.hand, event.start_ql, event.pitch, event.voice))


def _match(predicted, reference, predicate, cost):
    """按最小代价贪婪求一对一匹配；候选代价先全局排序以免顺序影响结果。"""
    candidates = []
    for pred_index, pred in enumerate(predicted):
        for ref_index, ref in enumerate(reference):
            if predicate(pred, ref):
                candidates.append((cost(pred, ref), pred_index, ref_index))
    used_pred, used_ref, matches = set(), set(), []
    for _cost, pred_index, ref_index in sorted(candidates):
        if pred_index not in used_pred and ref_index not in used_ref:
            used_pred.add(pred_index)
            used_ref.add(ref_index)
            matches.append((pred_index, ref_index))
    return matches


def _metric_event(event: ReferenceEvent, mapped_onset: float) -> dict:
    return {
        "hand": event.hand,
        "pitch": event.pitch,
        "onset_ql": mapped_onset,
        "duration_ql": event.duration_ql,
        "tie_start": event.tie_start,
        "tie_stop": event.tie_stop,
        "voice": event.voice,
    }


def evaluate_score(system_xml: str | Path, reference_xml: str | Path, alignment_csv: str | Path,
                   onset_tolerance: float = 0.125, duration_tolerance: float = 0.25,
                   pedal_tolerance: float = 0.25) -> dict:
    """评估单一系统输出；无可靠对齐时抛错而非生成貌似精确的分数。"""
    alignment = _read_alignment(alignment_csv)
    anchors = _anchors(alignment)
    if not anchors:
        raise ValueError("可靠对齐锚点不足，无法将系统输出映射至参考谱时间轴")
    reference_all = reference_score_events(reference_xml)
    reference = _reference_subset(reference_all, alignment)
    if not reference:
        raise ValueError("对齐 CSV 未关联到任何参考 MusicXML 事件")
    system_all = reference_score_events(system_xml)
    predicted, unmapped = [], 0
    for event in system_all:
        mapped_onset = _map_position(event.start_ql, anchors.get(event.hand, []))
        if mapped_onset is None:
            unmapped += 1
            continue
        predicted.append(_metric_event(event, mapped_onset))
    expected = [_metric_event(event, event.start_ql) for event in reference]
    same_hand = lambda p, r: p["hand"] == r["hand"]
    pitch_matches = _match(
        predicted, expected,
        lambda p, r: same_hand(p, r) and p["pitch"] == r["pitch"],
        lambda p, r: abs(p["onset_ql"] - r["onset_ql"]),
    )
    onset_matches = _match(
        predicted, expected,
        lambda p, r: same_hand(p, r) and p["pitch"] == r["pitch"]
        and abs(p["onset_ql"] - r["onset_ql"]) <= onset_tolerance,
        lambda p, r: abs(p["onset_ql"] - r["onset_ql"]),
    )
    note_matches = _match(
        predicted, expected,
        lambda p, r: same_hand(p, r) and p["pitch"] == r["pitch"]
        and abs(p["onset_ql"] - r["onset_ql"]) <= onset_tolerance
        and abs(p["duration_ql"] - r["duration_ql"]) <= duration_tolerance,
        lambda p, r: abs(p["onset_ql"] - r["onset_ql"]) + abs(p["duration_ql"] - r["duration_ql"]),
    )
    duration_errors = [abs(predicted[p]["duration_ql"] - expected[r]["duration_ql"])
                       for p, r in onset_matches]
    duration_correct = sum(error <= duration_tolerance for error in duration_errors)
    tied_matches = [(p, r) for p, r in onset_matches
                    if expected[r]["tie_start"] or expected[r]["tie_stop"]]
    tied_correct = sum(
        predicted[p]["tie_start"] == expected[r]["tie_start"]
        and predicted[p]["tie_stop"] == expected[r]["tie_stop"]
        for p, r in tied_matches
    )

    # 声部一致性：MusicXML voice 编号在系统与参考谱之间没有天然对应关系，直接比较
    # 原始编号会把任意的编号选择误判为错误。改用聚类纯度：把每个系统 voice 里的匹配
    # 事件按参考 voice 分组，取多数票，占比即为一致率；无匹配事件时不给出该指标。
    voice_clusters: dict[str, Counter] = defaultdict(Counter)
    for pred_index, ref_index in note_matches:
        voice_clusters[predicted[pred_index]["voice"]][expected[ref_index]["voice"]] += 1
    voice_correct = sum(counter.most_common(1)[0][1] for counter in voice_clusters.values())
    voice_total = len(note_matches)

    reference_pedals = pedal_events(reference_xml)
    system_pedals = pedal_events(system_xml)
    mapped_pedals = []
    for event in system_pedals:
        position = _map_position(event.position_ql, anchors.get(event.hand, []))
        if position is not None:
            mapped_pedals.append(PedalEvent(event.hand, position, event.event_type))
    pedal_matches = _match(
        mapped_pedals, reference_pedals,
        lambda p, r: p.hand == r.hand and p.event_type == r.event_type
        and abs(p.position_ql - r.position_ql) <= pedal_tolerance,
        lambda p, r: abs(p.position_ql - r.position_ql),
    )
    by_type = {}
    for event_type in ("start", "change", "stop"):
        pred = [item for item in mapped_pedals if item.event_type == event_type]
        ref = [item for item in reference_pedals if item.event_type == event_type]
        matches = _match(pred, ref,
                         lambda p, r: p.hand == r.hand and abs(p.position_ql-r.position_ql) <= pedal_tolerance,
                         lambda p, r: abs(p.position_ql-r.position_ql))
        by_type[event_type] = _f1(len(matches), len(pred), len(ref))
    pedal_available = bool(reference_pedals)
    return {
        "schema_version": "score-metrics-v1",
        "parameters": {
            "onset_tolerance_ql": onset_tolerance,
            "duration_tolerance_ql": duration_tolerance,
            "pedal_tolerance_ql": pedal_tolerance,
        },
        "coverage": {
            "reference_events_total": len(reference_all),
            "reference_events_reliably_aligned": len(reference),
            "system_events_total": len(system_all),
            "system_events_mapped_to_reference_axis": len(predicted),
            "system_events_outside_alignment_span": unmapped,
        },
        "pitch": _f1(len(pitch_matches), len(predicted), len(expected)),
        "onset": _f1(len(onset_matches), len(predicted), len(expected)),
        "note": _f1(len(note_matches), len(predicted), len(expected)),
        "duration": {
            "matched_events": len(duration_errors),
            "accuracy": duration_correct / len(duration_errors) if duration_errors else None,
            "mae_ql": statistics.fmean(duration_errors) if duration_errors else None,
            "median_absolute_error_ql": statistics.median(duration_errors) if duration_errors else None,
        },
        "tie_chain": {
            "available": bool(tied_matches),
            "reliably_mapped_reference_tied_events": len(tied_matches),
            "correct_chain_role_events": tied_correct,
            "accuracy": tied_correct / len(tied_matches) if tied_matches else None,
        },
        "voice_consistency": {
            "available": voice_total > 0,
            "matched_note_events": voice_total,
            "majority_consistent_events": voice_correct,
            "accuracy": voice_correct / voice_total if voice_total else None,
        },
        "pedal": {
            "available": pedal_available,
            "reference_events": len(reference_pedals),
            "system_events_mapped": len(mapped_pedals),
            "all": _f1(len(pedal_matches), len(mapped_pedals), len(reference_pedals)) if pedal_available else None,
            "by_type": by_type if pedal_available else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="C 阶段 MusicXML 相对参考谱评分")
    parser.add_argument("--system-xml", required=True)
    parser.add_argument("--reference-xml", required=True)
    parser.add_argument("--alignment", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--onset-tol", type=float, default=0.125)
    parser.add_argument("--dur-tol", type=float, default=0.25)
    parser.add_argument("--pedal-tol", type=float, default=0.25)
    args = parser.parse_args()
    result = evaluate_score(args.system_xml, args.reference_xml, args.alignment, args.onset_tol,
                            args.dur_tol, args.pedal_tol)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写出 {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
