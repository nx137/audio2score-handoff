#!/usr/bin/env python3
"""Half-pedal feasibility survey over the frozen 40-segment gold standard.

Searches for evidence of half-pedal / partial-pedal / sostenuto usage across:
  - events.csv semantic columns + review_note (free text)
  - pedal_intervals.csv (CC64 carry no half-pedal depth info - expect 0 hits)
  - reference_pedals.csv event_type values (published score pedal marks)

Output: hit list + a verdict (model half-pedal semantics vs record as a known
limitation) based on the observed frequency.

Usage:
    python tools/analyze_half_pedal.py [--out .../half_pedal_survey.json]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"

KEYWORDS = ["half", "partial", "1/2", "half-pedal", "half pedal", "sostenuto",
            "mezzo", "quarter-pedal", "three-quarter", "半踏", "halfpedal"]

ANNOT_COLS = ["acoustic_sustain", "performance_pedal_action",
              "published_score_pedal", "review_note"]


def hits_in_text(text: str) -> list[str]:
    low = text.lower()
    return [kw for kw in KEYWORDS if kw.lower() in low]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "evaluation" / "half_pedal_survey.json"))
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    sids = [b["segment_id"] for b in bl]

    hits = []
    col_dist = Counter()
    kw_dist = Counter()
    event_type_dist = Counter()
    n_intervals = 0

    for sid in sids:
        sd = BASE / sid
        with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if not r.get("notation_decision"):
                continue
            for col in ANNOT_COLS:
                val = (r.get(col) or "").strip()
                if not val:
                    continue
                for kw in hits_in_text(val):
                    hits.append({"segment": sid, "event_id": r.get("event_id", ""),
                                 "column": col, "value": val[:120], "keyword": kw})
                    col_dist[col] += 1
                    kw_dist[kw] += 1
        ipath = sd / "pedal_intervals.csv"
        if ipath.exists():
            with ipath.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            n_intervals += len(rows)
            for r in rows:
                for v in r.values():
                    for kw in hits_in_text(v or ""):
                        hits.append({"segment": sid, "event_id": "pedal_interval",
                                     "column": "pedal_intervals", "value": (v or "")[:120],
                                     "keyword": kw})
                        col_dist["pedal_intervals"] += 1
                        kw_dist[kw] += 1
        rpath = sd / "reference_pedals.csv"
        if rpath.exists():
            with rpath.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            for r in rows:
                et = (r.get("event_type") or "").strip()
                event_type_dist[et if et else "(blank)"] += 1
                for v in r.values():
                    for kw in hits_in_text(v or ""):
                        hits.append({"segment": sid, "event_id": "ref_pedal",
                                     "column": "reference_pedals", "value": (v or "")[:120],
                                     "keyword": kw})
                        col_dist["reference_pedals"] += 1
                        kw_dist[kw] += 1

    out = {
        "n_segments": len(sids),
        "n_pedal_intervals": n_intervals,
        "n_hits": len(hits),
        "by_column": dict(col_dist),
        "by_keyword": dict(kw_dist),
        "reference_pedal_event_types": dict(event_type_dist),
        "hits": hits[:200],
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    if len(hits) == 0:
        verdict = "no-evidence（建议作为已知局限记录，不做半踏建模）"
    elif len(hits) <= 10:
        verdict = "weak（样本过少，不建议建模，记录为局限）"
    else:
        verdict = "evidence（需进一步人工复核后决定是否建模）"

    lines = ["# 半踏（half-pedal）可行性调查", "",
             "- 片段数: %d, 踏板区间数: %d, 关键词命中: %d" % (len(sids), n_intervals, len(hits)), "",
             "## 命中分布", "", "| 列 | 命中数 |", "|---|---|"]
    for k, v in sorted(col_dist.items()):
        lines.append("| %s | %d |" % (k, v))
    lines += ["", "## 关键词", ""]
    for k, v in sorted(kw_dist.items()):
        lines.append("- %s: %d" % (k, v))
    lines += ["", "## 出版谱踏板标记类型分布", "", "| event_type | 数量 |", "|---|---|"]
    for k, v in sorted(event_type_dist.items()):
        lines.append("| %s | %d |" % (k, v))
    lines += ["", "## 结论: %s" % verdict, "", "输出: " + str(path)]
    print(chr(10).join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
