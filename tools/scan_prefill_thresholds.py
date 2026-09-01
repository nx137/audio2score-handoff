#!/usr/bin/env python3
"""Retake / acoustic threshold sensitivity scan for the gold-standard prefill rules.

Recomputes the three prefill columns (acoustic_sustain, performance_pedal_action,
published_score_pedal) over the frozen 40-segment gold standard with alternative
RETAKE_QL / acoustic thresholds, and reports how often the rule output differs
from (a) the human-frozen annotation (events.csv current values) and (b) the
default 0.25 / 0.25 baseline.

The scan is READ-ONLY: events.csv is never written back.  It answers the paper
robustness question "how sensitive are the gold-standard semantic columns to the
0.25 retake threshold" and documents the historical coupling that
classify_acoustic reuses RETAKE_QL as its sustain threshold.

Usage:
    python tools/scan_prefill_thresholds.py [--out .../prefill_threshold_scan.json]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from itertools import product
from pathlib import Path

import prefill_events as pe

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"

RETAKE_GRID = [0.125, 0.25, 0.375, 0.5]
ACOUSTIC_GRID = [0.125, 0.25, 0.5]
BOUNDARY_QL = 0.25
SCORE_QL = 0.25

ANNOT_NAMES = ["acoustic_sustain", "performance_pedal_action", "published_score_pedal"]
SHORT = {"acoustic_sustain": "acoustic", "performance_pedal_action": "perf",
         "published_score_pedal": "score"}


def load_rows(sd: Path) -> list[dict]:
    with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "evaluation" / "prefill_threshold_scan.json"))
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    sids = [b["segment_id"] for b in bl]

    human = {c: Counter() for c in ("acoustic", "perf", "score")}
    n_gold = 0
    n_rows = 0
    for sid in sids:
        for r in load_rows(BASE / sid):
            n_rows += 1
            if not r.get("notation_decision"):
                continue
            n_gold += 1
            for col, c in (("acoustic_sustain", "acoustic"),
                           ("performance_pedal_action", "perf"),
                           ("published_score_pedal", "score")):
                v = (r.get(col) or "").strip()
                human[c][v if v else "(blank)"] += 1

    baseline = {}
    base_dist = {c: Counter() for c in ("acoustic", "perf", "score")}
    base_vs_human = {"acoustic": 0, "perf": 0, "score": 0, "any": 0}
    for sid in sids:
        sd = BASE / sid
        meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
        s0, s1 = float(meta["start_ql"]), float(meta["end_ql"])
        ivs = pe.parse_pedal_intervals(sd / "pedal_intervals.csv")
        refp = pe.parse_ref_pedals(sd / "reference_pedals.csv")
        for idx, r in enumerate(load_rows(sd)):
            if not r:
                continue
            onset = float(r["onset_ql"])
            pcol = (r.get("pedal_extension_ql") or "").strip()
            pv = float(pcol) if pcol else 0.0
            comp = (
                pe.classify_acoustic(pv, onset, s0, s1, acoustic_ql=0.25, boundary_ql=BOUNDARY_QL),
                pe.classify_perf(onset, ivs, s0, s1, retake_ql=0.25, boundary_ql=BOUNDARY_QL),
                pe.classify_score(onset, refp, score_ql=SCORE_QL),
            )
            for ci, name in enumerate(SHORT.values()):
                base_dist[name][comp[ci]] += 1
            if not r.get("notation_decision"):
                continue
            baseline[(sid, idx)] = comp
            row_diff = False
            for ci, col in enumerate(ANNOT_NAMES):
                cur = (r.get(col) or "").strip()
                if cur and comp[ci] != cur:
                    base_vs_human[SHORT[col]] += 1
                    row_diff = True
            if row_diff:
                base_vs_human["any"] += 1

    scans = {}
    for retake_ql, aco_ql in product(RETAKE_GRID, ACOUSTIC_GRID):
        key = "r=%.3f,a=%.3f" % (retake_ql, aco_ql)
        if (retake_ql, aco_ql) == (0.25, 0.25):
            scans[key] = {"retake_ql": retake_ql, "acoustic_ql": aco_ql,
                          "computed_dist": {c: dict(m) for c, m in base_dist.items()},
                          "vs_human": base_vs_human,
                          "vs_baseline": {"gold_diff_rows": 0, "flip_change_release": 0,
                                           "flip_acoustic_yes_no": 0},
                          "per_segment": {}, "gold_rows_checked": n_gold}
            continue
        dist = {c: Counter() for c in ("acoustic", "perf", "score")}
        vs_human = {"acoustic": 0, "perf": 0, "score": 0, "any": 0}
        vs_base = {"gold_diff_rows": 0, "flip_change_release": 0, "flip_acoustic_yes_no": 0}
        per_seg = Counter()
        for sid in sids:
            sd = BASE / sid
            meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
            s0, s1 = float(meta["start_ql"]), float(meta["end_ql"])
            ivs = pe.parse_pedal_intervals(sd / "pedal_intervals.csv")
            refp = pe.parse_ref_pedals(sd / "reference_pedals.csv")
            for idx, r in enumerate(load_rows(sd)):
                if not r:
                    continue
                onset = float(r["onset_ql"])
                pcol = (r.get("pedal_extension_ql") or "").strip()
                pv = float(pcol) if pcol else 0.0
                comp = (
                    pe.classify_acoustic(pv, onset, s0, s1, acoustic_ql=aco_ql, boundary_ql=BOUNDARY_QL),
                    pe.classify_perf(onset, ivs, s0, s1, retake_ql=retake_ql, boundary_ql=BOUNDARY_QL),
                    pe.classify_score(onset, refp, score_ql=SCORE_QL),
                )
                for ci, name in enumerate(SHORT.values()):
                    dist[name][comp[ci]] += 1
                if not r.get("notation_decision"):
                    continue
                row_diff = False
                for ci, col in enumerate(ANNOT_NAMES):
                    cur = (r.get(col) or "").strip()
                    if cur and comp[ci] != cur:
                        vs_human[SHORT[col]] += 1
                        row_diff = True
                if row_diff:
                    vs_human["any"] += 1
                base = baseline.get((sid, idx))
                if base is None:
                    continue
                if base != comp:
                    vs_base["gold_diff_rows"] += 1
                    per_seg[sid] += 1
                if {base[1], comp[1]} == {"change", "release"}:
                    vs_base["flip_change_release"] += 1
                if {base[0], comp[0]} == {"yes", "no"}:
                    vs_base["flip_acoustic_yes_no"] += 1
        scans[key] = {"retake_ql": retake_ql, "acoustic_ql": aco_ql,
                      "computed_dist": {c: dict(m) for c, m in dist.items()},
                      "vs_human": vs_human, "vs_baseline": vs_base,
                      "per_segment": dict(per_seg)}

    out = {"n_segments": len(sids), "n_rows_all": n_rows, "n_rows_gold": n_gold,
           "thresholds": {"retake": RETAKE_GRID, "acoustic": ACOUSTIC_GRID,
                           "boundary": BOUNDARY_QL, "score": SCORE_QL},
           "human_dist": {c: dict(m) for c, m in human.items()}, "scans": scans}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# 金标准预填阈值敏感性扫描", "",
             "- 片段数: %d, 全部行: %d, gold 行: %d" % (len(sids), n_rows, n_gold), "",
             "## 人工定稿列分布", "", "| 列 | 值分布 |", "|---|---|"]
    for c in ("acoustic", "perf", "score"):
        items = ", ".join("%s=%d" % (k, v) for k, v in sorted(human[c].items()))
        lines.append("| %s | %s |" % (c, items))
    lines += ["", "## 扫描结果（vs baseline r=0.25, a=0.25；仅 gold 行）", "",
              "| retake | acoustic | perf 分布 | vs_human(perf) | diff 行 | flip change/release | flip yes/no |",
              "|---|---|---|---|---|---|---|"]
    for key, s in scans.items():
        pd = s["computed_dist"]["perf"]
        pdist = ", ".join("%s=%d" % (k, v) for k, v in sorted(pd.items()))
        lines.append("| %.3f | %.3f | %s | %d | %d | %d | %d |" % (
            s["retake_ql"], s["acoustic_ql"], pdist, s["vs_human"]["perf"],
            s["vs_baseline"]["gold_diff_rows"], s["vs_baseline"]["flip_change_release"],
            s["vs_baseline"]["flip_acoustic_yes_no"]))
    lines += ["", "输出: " + str(path)]
    print(chr(10).join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
