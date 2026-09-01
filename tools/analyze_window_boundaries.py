#!/usr/bin/env python3
"""Window boundary protocol analysis for the pedal F1 evaluation.

For every frozen segment, classifies each CC64 pedal interval against the
segment window [start_ql, end_ql]:

    fully_inside : start_ql <= start and end <= end_ql
    cross_start  : start < start_ql and start_ql < end <= end_ql
    cross_end    : start_ql <= start < end_ql and end > end_ql
    cross_both   : start < start_ql and end > end_ql

(intervals with no overlap with the window are filtered at build time;
 boundary-equal cases count as inside).

Then replicates _ref_events() of evaluate_gold_standard.py for the four
protocols (unclipped / inwindow / visible / clipped), reports the reference
start/stop counts per protocol, the per-pipe rendered pedal event counts, and
the protocol sensitivity deltas.  This measures how large the boundary effect
is on the pedal F1 numbers and whether the recommended inwindow protocol is
stable.

Usage:
    python tools/analyze_window_boundaries.py [--out .../window_boundary_analysis.json]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from evaluate_gold_standard import BASE, _ref_events, parse_pedals

ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-9


def classify(s: float, e: float, s0: float, s1: float) -> str:
    inside_s = s >= s0 - EPS
    inside_e = e <= s1 + EPS
    if inside_s and inside_e:
        return "fully_inside"
    if not inside_s and inside_e:
        return "cross_start"
    if inside_s and not inside_e:
        return "cross_end"
    return "cross_both"


def load_ivs(sd: Path) -> list[tuple[float, float, float, float]]:
    ivs = []
    with (sd / "pedal_intervals.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("start_ql", "").strip():
                ivs.append((float(r["start_ql"]), float(r["end_ql"]),
                            float(r["clipped_start_ql"]), float(r["clipped_end_ql"])))
    return ivs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "evaluation" / "window_boundary_analysis.json"))
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    sids = [b["segment_id"] for b in bl]

    total_cat = Counter()
    total_ref = {p: {"starts": 0, "stops": 0} for p in ("unclipped", "inwindow", "visible", "clipped")}
    total_pipe = Counter()
    per_seg = {}

    for sid in sids:
        sd = BASE / sid
        meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
        s0, s1 = float(meta["start_ql"]), float(meta["end_ql"])
        ivs = load_ivs(sd)
        cats = Counter(classify(s, e, s0, s1) for s, e, cs, ce in ivs)
        total_cat.update(cats)
        parsed = {"sid": sid, "start_ql": s0, "end_ql": s1, "ivs": ivs}
        seg = {"cats": dict(cats), "ref": {}, "pipe": {}}
        for proto in ("unclipped", "inwindow", "visible", "clipped"):
            st, sp = _ref_events(parsed, proto)
            seg["ref"][proto] = {"starts": len(st), "stops": len(sp)}
            total_ref[proto]["starts"] += len(st)
            total_ref[proto]["stops"] += len(sp)
        ped = parse_pedals(sd / "p4_rule.musicxml")
        pstarts = [o + s0 for t, o in ped if t in ("start", "change")]
        pstops = [o + s0 for t, o in ped if t in ("stop", "change")]
        seg["pipe"] = {"starts": len(pstarts), "stops": len(pstops)}
        total_pipe["starts"] += len(pstarts)
        total_pipe["stops"] += len(pstops)
        per_seg[sid] = seg

    # protocol sensitivity (start/stop reference deltas vs inwindow)
    sens = {}
    for proto in ("unclipped", "visible", "clipped"):
        sens[proto] = {
            "start_delta": total_ref[proto]["starts"] - total_ref["inwindow"]["starts"],
            "stop_delta": total_ref[proto]["stops"] - total_ref["inwindow"]["stops"],
        }

    out = {
        "n_segments": len(sids),
        "interval_categories": dict(total_cat),
        "reference_counts_by_protocol": total_ref,
        "pipe_p4_rule_events": dict(total_pipe),
        "protocol_sensitivity_vs_inwindow": sens,
        "per_segment": per_seg,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# 窗口边界协议分析", "",
             "- 片段数: %d" % len(sids), "",
             "## 区间分类（40 片段汇总）", "", "| 类别 | 数量 |", "|---|---|"]
    for k in ("fully_inside", "cross_start", "cross_end", "cross_both"):
        lines.append("| %s | %d |" % (k, total_cat[k]))
    lines += ["", "## 四口径参考事件数（汇总）", "",
              "| protocol | starts | stops |", "|---|---|---|"]
    for proto in ("unclipped", "inwindow", "visible", "clipped"):
        lines.append("| %s | %d | %d |" % (proto, total_ref[proto]["starts"], total_ref[proto]["stops"]))
    lines += ["", "## p4_rule 输出踏板事件（窗口内）", "",
              "| 类型 | 数量 |", "|---|---|",
              "| starts | %d |" % total_pipe["starts"],
              "| stops | %d |" % total_pipe["stops"], "",
              "## 协议敏感性（vs inwindow 的参考事件数增量）", "",
              "| protocol | start_delta | stop_delta |", "|---|---|---|"]
    for proto in ("unclipped", "visible", "clipped"):
        lines.append("| %s | %+d | %+d |" % (proto, sens[proto]["start_delta"], sens[proto]["stop_delta"]))
    lines += ["", "## 边界事件最集中的片段（Top 8，按 cross_start+cross_end+cross_both）", ""]
    ranked = sorted(per_seg.items(), key=lambda kv: -(sum(kv[1]["cats"].get(k, 0) for k in ("cross_start", "cross_end", "cross_both"))))
    for sid, seg in ranked[:8]:
        lines.append("- %s: %s" % (sid, seg["cats"]))
    lines += ["", "输出: " + str(path)]
    print(chr(10).join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
