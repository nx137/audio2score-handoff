#!/usr/bin/env python3
"""Phase 2A S7: generate per-segment F/U/H/E review lists (trial8 review CSV format).

F-group definition for Phase 2A (no baseline comparison exists):
    F = rows where published_score_pedal (③) is non-none (start/change/stop)
        = the "③ 判读命中行" the user (annotator A) samples against
        reference_score.musicxml  (expansion plan §2.4).
U = acoustic_sustain or performance_pedal_action == uncertain
H = review_priority == high
E = reference_tie_start == 1 or review_note contains tie/换踩

Output per segment:  <out>/phase2A_A_review_<sid>.csv   (same 17 columns as
trial8 v1.3 lists; baseline_published_score_pedal is left empty for Phase 2A).
Review lists are working artifacts: do NOT commit them (exec §3 S7).

Usage:
    python tools/phase2a_generate_review.py SEG_DIR [SEG_DIR ...] [--out outputs/pedal_expansion/review]
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

F_VALUES = {"start", "change", "stop"}
REVIEW_COLS = ["segment_id", "row_no", "event_id", "hand", "pitch", "onset_ql",
               "onset_location", "groups", "acoustic_sustain",
               "performance_pedal_action", "published_score_pedal",
               "notation_decision", "review_class", "review_note",
               "baseline_published_score_pedal", "review_priority",
               "reference_tie_start"]


def process_segment(seg_dir: Path, out_dir: Path) -> dict:
    events_path = seg_dir / "events.csv"
    if not events_path.exists():
        raise SystemExit(f"missing {events_path}")
    sid = seg_dir.name
    with events_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    if len(header) < 30:
        raise SystemExit(f"{sid}: header has {len(header)} cols, expected >=30")
    idx = {name: i for i, name in enumerate(header)}
    data = rows[1:]
    # empty-cell gate on ①-④
    empties = []
    for rn, row in enumerate(data, start=1):
        for col in ("acoustic_sustain", "performance_pedal_action",
                    "published_score_pedal", "notation_decision"):
            if col in idx and not row[idx[col]].strip():
                empties.append((rn, col))
    groups_rows = []
    for rn, row in enumerate(data, start=1):
        def g(col):
            return row[idx[col]] if col in idx and idx[col] < len(row) else ""
        ac, pp, sp = g("acoustic_sustain"), g("performance_pedal_action"), g("published_score_pedal")
        groups = []
        if sp in F_VALUES:
            groups.append("F")
        if ac == "uncertain" or pp == "uncertain":
            groups.append("U")
        if g("review_priority").strip().lower() == "high":
            groups.append("H")
        if g("reference_tie_start").strip() == "1" or "tie" in g("review_note") or "换踩" in g("review_note"):
            groups.append("E")
        if groups:
            groups_rows.append((rn, row, groups))
    # write review csv
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"phase2A_A_review_{sid}.csv"
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(REVIEW_COLS)
        for rn, row, groups in groups_rows:
            vals = {c: (row[idx[c]] if c in idx and idx[c] < len(row) else "") for c in REVIEW_COLS}
            vals["segment_id"] = sid
            vals["row_no"] = rn
            vals["groups"] = "|".join(groups)
            vals["baseline_published_score_pedal"] = ""   # Phase 2A: no baseline
            w.writerow([vals[c] for c in REVIEW_COLS])
    # stats
    stat = {"sid": sid, "n_rows": len(data), "F": 0, "U": 0, "H": 0, "E": 0,
            "overlaps": Counter(), "empty14": len(empties), "file": str(out_path),
            "F_dual_coverage": 0, "F_no_perf": 0,
            "cross_scalar": Counter()}
    f_rows_idx = []
    for rn, row, groups in groups_rows:
        for g_ in groups:
            stat[g_] += 1
        if len(groups) > 1:
            stat["overlaps"]["|".join(sorted(groups))] += 1
        if "F" in groups:
            f_rows_idx.append((rn, row))
    # F-row ②/③ cross table
    ct = Counter()
    for rn, row in f_rows_idx:
        def g(col):
            return row[idx[col]] if col in idx and idx[col] < len(row) else ""
        sp, pp = g("published_score_pedal"), g("performance_pedal_action")
        key = (sp, pp if pp else "EMPTY")
        ct[key] += 1
        if pp in ("hold", "change", "release"):
            stat["F_dual_coverage"] += 1
        elif pp == "none":
            stat["F_no_perf"] += 1
    stat["cross"] = {f"{a}->{b}": n for (a, b), n in sorted(ct.items())}
    return stat


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", default="outputs/pedal_expansion/review")
    args = ap.parse_args()
    out_dir = Path(args.out)
    all_stats = []
    tot = Counter()
    for d in args.dirs:
        st = process_segment(Path(d), out_dir)
        all_stats.append(st)
        for k in ("n_rows", "F", "U", "H", "E", "F_dual_coverage", "F_no_perf"):
            tot[k] += st[k]
        print(f"[{st['sid']}] events={st['n_rows']} | F={st['F']} U={st['U']} "
              f"H={st['H']} E={st['E']} | overlaps={dict(st['overlaps'])} | "
              f"empty14={st['empty14']} | F dual-coverage={st['F_dual_coverage']} "
              f"F perf-none={st['F_no_perf']}")
        print(f"    F rows cross (③->②): {st['cross']}")
        print(f"    wrote {st['file']}")
    print("-" * 70)
    print(f"TOTAL events={tot['n_rows']} F={tot['F']} U={tot['U']} H={tot['H']} "
          f"E={tot['E']} | F dual-coverage={tot['F_dual_coverage']} "
          f"F perf-none={tot['F_no_perf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
