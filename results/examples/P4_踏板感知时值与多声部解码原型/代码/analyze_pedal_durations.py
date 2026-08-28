#!/usr/bin/env python3
"""踏板感知时值评测：区分键盘释放、声学持续与当前符号时值。

本脚本不修改 MIDI→MusicXML 生产输出。它建立 P4 的评测基线：

* key duration：MIDI note-on 至 note-off，近似键盘按键保持时长；
* acoustic duration：若 note-off 发生在 CC64 踏板踩下区间，则延至踏板释放；
* notation duration：复走当前量化、分手与单 voice 防重叠后的符号输入时值。

三者不应被强行视为同一标签。特别是 acoustic duration 的增长多由踏板产生，
不应自动转换为 MusicXML 的 tie 或长时值。
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from midi_to_score import clip_to_next_onset, midi_to_events, quantize_events, split_hands


@dataclass
class DurationRecord:
    hand: str
    pitch: int
    onset_ql: float
    key_duration_ql: float
    acoustic_duration_ql: float
    notation_duration_ql: float
    pedal_extended_ql: float
    notation_minus_key_ql: float
    notation_minus_acoustic_ql: float
    next_hand_onset_ql: float | None
    truncated_by_current_single_voice: bool


def pedal_release_after(key_end: float, pedals: list[tuple[float, float]]) -> float:
    """返回 CC64 对该按键释放造成的声学结束；无延长时返回 key_end。"""
    for pedal_start, pedal_end in pedals:
        if pedal_start - 1e-9 <= key_end < pedal_end - 1e-9:
            return pedal_end
    return key_end


def _raw_by_hand(notes, pedals):
    records = {"RH": [], "LH": []}
    rh, lh = split_hands(notes)
    for hand, events in (("RH", rh), ("LH", lh)):
        for pitch, onset, key_dur, _velocity in sorted(events, key=lambda x: (x[0], x[1])):
            acoustic_end = pedal_release_after(onset + key_dur, pedals)
            records[hand].append({
                "pitch": pitch,
                "onset": onset,
                "key_duration": key_dur,
                "acoustic_duration": acoustic_end - onset,
                "pedal_extended": acoustic_end - (onset + key_dur),
            })
    return records


def _notation_by_hand(notes, divisors):
    rh, lh = split_hands(notes)
    return {
        "RH": clip_to_next_onset(rh, divisors=divisors),
        "LH": clip_to_next_onset(lh, divisors=divisors),
    }


def _next_onsets(events):
    onsets = sorted({event[1] for event in events})
    return {onset: onsets[i + 1] if i + 1 < len(onsets) else None
            for i, onset in enumerate(onsets)}


def build_records(midi_path: str, divisors=(8, 4, 3)) -> list[DurationRecord]:
    raw_notes, pedals, _meta = midi_to_events(midi_path)
    qnotes = quantize_events(raw_notes, divisors=divisors)
    raw = _raw_by_hand(raw_notes, pedals)
    notation = _notation_by_hand(qnotes, divisors)

    result: list[DurationRecord] = []
    for hand in ("RH", "LH"):
        raw_by_pitch: dict[int, list] = {}
        notation_by_pitch: dict[int, list] = {}
        for event in raw[hand]:
            raw_by_pitch.setdefault(event["pitch"], []).append(event)
        for event in notation[hand]:
            notation_by_pitch.setdefault(event[0], []).append(event)
        next_by_onset = _next_onsets(notation[hand])

        # quantize_events 不改变事件数；以同手、同音高、时间顺序配对，可以回溯
        # 当前符号时值对原始键盘事件的影响，而不把 XML 排版误差混入该阶段。
        for pitch in sorted(set(raw_by_pitch) | set(notation_by_pitch)):
            raw_events = raw_by_pitch.get(pitch, [])
            notation_events = notation_by_pitch.get(pitch, [])
            if len(raw_events) != len(notation_events):
                raise ValueError(
                    f"{hand} pitch {pitch}: raw={len(raw_events)}, notation={len(notation_events)}；"
                    "量化阶段不应增删事件。"
                )
            for source, target in zip(raw_events, notation_events):
                _p, notation_onset, notation_dur, _velocity = target
                next_onset = next_by_onset[notation_onset]
                current_cut = (
                    next_onset is not None
                    and source["key_duration"] > notation_dur + 1e-6
                    and source["onset"] + source["key_duration"] > next_onset + 1e-6
                )
                result.append(DurationRecord(
                    hand=hand,
                    pitch=pitch,
                    onset_ql=source["onset"],
                    key_duration_ql=source["key_duration"],
                    acoustic_duration_ql=source["acoustic_duration"],
                    notation_duration_ql=notation_dur,
                    pedal_extended_ql=source["pedal_extended"],
                    notation_minus_key_ql=notation_dur - source["key_duration"],
                    notation_minus_acoustic_ql=notation_dur - source["acoustic_duration"],
                    next_hand_onset_ql=next_onset,
                    truncated_by_current_single_voice=current_cut,
                ))
    return sorted(result, key=lambda row: (row.onset_ql, row.hand, row.pitch))


def summarize(records: list[DurationRecord], tolerance=0.25) -> dict:
    n = len(records)
    pedal = [row for row in records if row.pedal_extended_ql > tolerance]
    short_key = [row for row in records if row.notation_minus_key_ql < -tolerance]
    short_acoustic = [row for row in records if row.notation_minus_acoustic_ql < -tolerance]
    single_voice = [row for row in records if row.truncated_by_current_single_voice]
    close_key = [row for row in records if abs(row.notation_minus_key_ql) <= tolerance]
    close_acoustic = [row for row in records if abs(row.notation_minus_acoustic_ql) <= tolerance]
    return {
        "note_count": n,
        "tolerance_ql": tolerance,
        "notation_within_tolerance_of_key_release": len(close_key),
        "notation_within_tolerance_of_acoustic_end": len(close_acoustic),
        "pedal_extended_notes": len(pedal),
        "notation_shorter_than_key_release": len(short_key),
        "notation_shorter_than_acoustic_end": len(short_acoustic),
        "current_single_voice_truncation_candidates": len(single_voice),
        "by_hand": dict(Counter(row.hand for row in records)),
    }


def write_csv(records: list[DurationRecord], output: Path):
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(records[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in records)


def _fmt(row: DurationRecord) -> str:
    next_text = "—" if row.next_hand_onset_ql is None else f"{row.next_hand_onset_ql:.3f}"
    return (
        f"| {row.hand} | {row.pitch} | {row.onset_ql:.3f} | {row.key_duration_ql:.3f} | "
        f"{row.acoustic_duration_ql:.3f} | {row.notation_duration_ql:.3f} | "
        f"{row.pedal_extended_ql:.3f} | {next_text} |"
    )


def write_markdown(records: list[DurationRecord], summary: dict, output: Path, label: str):
    cases = sorted(
        (row for row in records if row.truncated_by_current_single_voice),
        key=lambda row: (row.key_duration_ql - row.notation_duration_ql), reverse=True,
    )[:20]
    pedal_cases = sorted(
        (row for row in records if row.pedal_extended_ql > summary["tolerance_ql"]),
        key=lambda row: row.pedal_extended_ql, reverse=True,
    )[:12]
    lines = [
        f"# P4a：踏板感知时值评测 — {label}",
        "",
        "## 口径",
        "",
        "- **键盘时值**：MIDI `note_on → note_off`。",
        "- **声学时值**：若 `note_off` 落在 CC64 踏板踩下区间，延至相应踏板释放；同音重新触键造成的声学重叠未在此统计中额外建模。",
        "- **当前符号时值**：复走现有量化、左右手拆分和单 voice 防重叠截断后的时值。它是当前 MusicXML 导出层的输入，不等于原始 MIDI 的 `note_off`。",
        f"- 本报告以 `{summary['tolerance_ql']:.2f}` QL（一个十六分音符）作为“接近”的容差。",
        "",
        "## 汇总",
        "",
        "| 指标 | 数值 | 解释 |",
        "|---|---:|---|",
        f"| 音符数 | {summary['note_count']} | 左右手合计 |",
        f"| 符号时值接近键盘释放 | {summary['notation_within_tolerance_of_key_release']} | 与 raw `note_off` 的差在容差内 |",
        f"| 符号时值接近声学结束 | {summary['notation_within_tolerance_of_acoustic_end']} | 踏板延长也计入 |",
        f"| 踏板显著延长的音 | {summary['pedal_extended_notes']} | 声学时值比键盘时值多超过容差 |",
        f"| 符号时值短于键盘释放 | {summary['notation_shorter_than_key_release']} | 不应直接认定为错误；可能需独立声部或本就应为短符号时值 |",
        f"| 符号时值短于声学结束 | {summary['notation_shorter_than_acoustic_end']} | 通常包含踏板带来的合理差异 |",
        f"| 单 voice 截断候选 | {summary['current_single_voice_truncation_candidates']} | 原键盘时值跨越同手下一起音，P4b 多声部需重点处理 |",
        "",
        "## 单 voice 截断候选（按键盘时值损失排序，前 20 条）",
        "",
        "| 手 | 音高(MIDI) | 起音 QL | 键盘时值 | 声学时值 | 当前符号时值 | 踏板延长 | 下一同手起音 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(_fmt(row) for row in cases) if cases else lines.append("| — | — | — | — | — | — | — | — |")
    lines.extend([
        "",
        "## 踏板显著延长案例（前 12 条）",
        "",
        "| 手 | 音高(MIDI) | 起音 QL | 键盘时值 | 声学时值 | 当前符号时值 | 踏板延长 | 下一同手起音 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    lines.extend(_fmt(row) for row in pedal_cases) if pedal_cases else lines.append("| — | — | — | — | — | — | — | — |")
    lines.extend([
        "",
        "## 如何用于 P4b / P4c",
        "",
        "1. “踏板显著延长”只作为声学持续证据，不直接强制生成 tie。",
        "2. “单 voice 截断候选”优先进入多声部候选图：若其音高、旋律连续性与声部占用允许，则保留长时值并分配独立 voice。",
        "3. P4c 的全局解码器以小节合法、同 voice 不交叠为硬约束；键盘/声学时值的偏差只作为软代价。",
        "4. 后续 LightGBM 学习的是“候选时值、voice 与 tie 的概率”，不直接回归无约束浮点 `note_off`。",
    ])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="P4a 踏板感知时值评测")
    parser.add_argument("--midi", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", default=None)
    parser.add_argument("--divisors", default="8,4,3")
    parser.add_argument("--tolerance", type=float, default=0.25)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = args.label or Path(args.midi).stem
    divisors = tuple(int(item) for item in args.divisors.split(","))
    records = build_records(args.midi, divisors=divisors)
    summary = summarize(records, tolerance=args.tolerance)
    stem = Path(args.midi).stem
    write_csv(records, out_dir / f"{stem}_duration_records.csv")
    (out_dir / f"{stem}_duration_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(records, summary, out_dir / f"{stem}_duration_report.md", label)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
