#!/usr/bin/env python3
"""P4d：构造候选级人工复核与 LightGBM 训练数据。

标签不由脚本臆造；``review_class`` 由人工填写：
``independent-voice``、``notation-shortening`` 或 ``pedal-only``。
脚本只提供可复核优先级和规则建议，避免把启发式当作真值。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from analyze_pedal_durations import build_records
from midi_to_score import midi_to_events, quantize_events, split_hands
from structured_duration_decoder import (
    _candidate_sets,
    assign_voices,
    candidate_features,
)


def build_dataset(midi_path: str, output_path: str, label: str,
                  divisors=(8, 4, 3), max_voices=6, bar_ql=4.0) -> int:
    notes, pedals, _meta = midi_to_events(midi_path)
    qnotes = quantize_events(notes, divisors=divisors)
    rh, lh = split_hands(qnotes)
    records = build_records(midi_path, divisors=divisors)
    by_key = {(row.hand, row.pitch, round(row.onset_ql, 6)): row for row in records}
    rows = []
    for hand, events in (("RH", rh), ("LH", lh)):
        base = assign_voices(events, hand=hand, max_voices=max_voices)
        for event, key_duration, acoustic_duration, next_onset, candidates in _candidate_sets(
            base, pedals, bar_ql, divisors, None
        ):
            record = by_key.get((hand, event.pitch, round(event.start_ql, 6)))
            pedal_extension = acoustic_duration - key_duration
            priority = (
                "high" if record and record.truncated_by_current_single_voice
                else "medium" if pedal_extension > 0.25 else "normal"
            )
            for candidate in candidates:
                row = candidate_features(event, key_duration, acoustic_duration,
                                         candidate, next_onset, bar_ql)
                row.update({
                    "piece": label,
                    "hand": hand,
                    "review_priority": priority,
                    "suggested_review_class": (
                        "pedal-only" if pedal_extension > 0.25 and not candidate.crosses_barline
                        else "independent-voice" if record and record.truncated_by_current_single_voice
                        else "notation-shortening"
                    ),
                    "label": "",
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
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="构造 P4 候选级复核训练表")
    parser.add_argument("--midi", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--bar-ql", type=float, default=4.0)
    parser.add_argument("--max-voices", type=int, default=6)
    args = parser.parse_args()
    count = build_dataset(args.midi, args.out, args.label,
                          max_voices=args.max_voices, bar_ql=args.bar_ql)
    print(f"写出 {count} 个候选：{args.out}")


if __name__ == "__main__":
    main()
