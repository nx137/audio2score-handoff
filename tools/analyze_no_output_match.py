#!/usr/bin/env python3
"""Attribution analysis for the remaining no_output_match gold events.

A gold event (notation_decision set) is classified no_output_match when the
rendered pipe MusicXML has no note of the same hand+pitch whose onset falls
within ONSET_TOL (0.125 QL) of the gold onset.

For each such event we locate the nearest rendered note of the same hand+pitch
(any onset distance) and bucket the offset, so the report shows whether the
residual cases (v12: 124) are all quantisation-grid alignment issues (the note
exists but on a neighbouring grid slot) or contain something else.

Usage:
    python tools/analyze_no_output_match.py [--pipe p4_rule] [--out .../no_output_match_analysis.json]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from evaluate_gold_standard import BASE, ONSET_TOL, parse_notes

ROOT = Path(__file__).resolve().parents[1]


def nearest_same(notes: list[dict], hand: str, pitch: int, onset: float):
    best = None
    best_d = None
    for n in notes:
        if n["hand"] == hand and n["pitch"] == pitch:
            d = abs(n["onset"] - onset)
            if best_d is None or d < best_d:
                best_d, best = d, n
    return best, best_d


def bucket(offset: float) -> str:
    if offset <= ONSET_TOL:
        return "within_tol_should_not_happen"
    if offset <= 0.25:
        return "0.125-0.25"
    if offset <= 0.5:
        return "0.25-0.5"
    return "gt_0.5"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipe", default="p4_rule")
    ap.add_argument("--out", default=str(BASE / "evaluation" / "no_output_match_analysis.json"))
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    buckets = Counter()
    by_hand = Counter()
    by_class = Counter()
    by_seg = Counter()
    samples = []
    total_gold = 0
    total_nom = 0

    for b in bl:
        sid = b["segment_id"]
        sd = BASE / sid
        meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
        start_ql = float(meta["start_ql"])
        notes = parse_notes(sd / (args.pipe + ".musicxml"))
        with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if not r.get("notation_decision"):
                continue
            total_gold += 1
            g = {"hand": r["hand"], "pitch": int(r["pitch"]),
                 "onset": float(r["onset_ql"]) - start_ql}
            found = None
            for n in notes:
                if (n["hand"] == g["hand"] and n["pitch"] == g["pitch"]
                        and abs(n["onset"] - g["onset"]) <= ONSET_TOL):
                    found = n
                    break
            if found is not None:
                continue
            total_nom += 1
            near, near_d = nearest_same(notes, g["hand"], g["pitch"], g["onset"])
            if near is None:
                bk = "no_same_pitch_in_output"
            else:
                bk = bucket(near_d)
            buckets[bk] += 1
            by_hand[g["hand"]] += 1
            by_class[r.get("review_class") or "none"] += 1
            by_seg[sid] += 1
            if len(samples) < 60:
                samples.append({
                    "segment": sid, "event_id": r["event_id"], "hand": g["hand"],
                    "pitch": g["pitch"], "onset": round(g["onset"], 4),
                    "ref_dur": float(r["notation_decision"]),
                    "review_class": r.get("review_class") or "",
                    "nearest_onset_offset": None if near_d is None else round(near_d, 4),
                    "nearest_dur": None if near is None else round(near["dur"], 4),
                    "review_note": (r.get("review_note") or "")[:120],
                })

    out = {
        "pipe": args.pipe, "total_gold": total_gold, "total_no_output_match": total_nom,
        "by_bucket": dict(buckets), "by_hand": dict(by_hand), "by_class": dict(by_class),
        "by_segment": dict(by_seg), "samples": samples,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# no_output_match 归因分析（pipe=" + args.pipe + "）", "",
             "- gold 事件: %d, no_output_match: %d (%.2f%%)" % (
                 total_gold, total_nom, 100.0 * total_nom / total_gold if total_gold else 0.0), "",
             "## 最近同 pitch 音符 onset 偏移分桶", "", "| 分桶 | 数量 |", "|---|---|"]
    for k, v in sorted(buckets.items()):
        lines.append("| %s | %d |" % (k, v))
    lines += ["", "## 按 hand / review_class", "",
              "- hand: " + ", ".join("%s=%d" % (k, v) for k, v in sorted(by_hand.items())),
              "- class: " + ", ".join("%s=%d" % (k, v) for k, v in sorted(by_class.items())), "",
              "## 按片段（前 15）", ""]
    for k, v in sorted(by_seg.items(), key=lambda x: -x[1])[:15]:
        lines.append("- %s: %d" % (k, v))
    lines += ["", "输出: " + str(path)]
    print(chr(10).join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
