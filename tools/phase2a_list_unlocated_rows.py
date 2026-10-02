#!/usr/bin/env python3
"""Phase 2A: rows whose score-side onset is missing (no reference_onset_ql).

WHY
---
Column 3 (published_score_pedal) is derived from the row's score-side onset
(events.csv reference_onset_ql -> nearest entry of reference_pedals.csv within
PEDAL_MATCH_QL = 0.25).  A row without that onset has column 3 forced to "none" and is
skipped by both audit tools (phase2a_audit_extraction.py counts it under "rows without
reference_onset_ql", phase2a_audit_score_pedal.py under "no_reference_onset_ql").  Those
rows need a human eye instead: read the rendered score at the printed location and confirm
there is no pedal mark there.

TWO SCOPES -- read this before using a number
---------------------------------------------
events.csv holds ALL performance events of the segment's window; the review sheet
(phase2A_A_review_<seg>.csv, 783 rows in total for the five segments) is a SUBSET of it.
For the five segments 4569 events exist and 1884 of them have no score-side onset, but only
6 of those 1884 are inside the review sheets.

  --scope review (default)  the review sheets, i.e. the rows the annotator sees AND the
                            rows both audit tools iterate -> headline numbers 1/0/1/3/1 = 6
  --scope all               every events.csv row -> 111/45/588/862/278 = 1884

Both counts are always printed and stored; --scope only decides which row list is printed
and stored in detail.  See docs/trial8_phase2A_coordinate_conventions.md section 8.

WHERE THE FIELD LIVES
---------------------
NOT in the 17-column review sheets -- it lives in the segment's events.csv and is joined by
row_no == the 1-based data-row index of that file, the same join the audit tools and the
annotator worksheet use.  Reading the review sheet for it returns empty for every row.

Usage
-----
    python tools/phase2a_list_unlocated_rows.py [--scope review|all] [--max-print 50] \
        [--segments outputs/pedal_expansion/segments_v1] \
        [--review outputs/pedal_expansion/review] \
        [--out outputs/pedal_expansion/evaluation/phase2a_unlocated_rows.json]

Read-only apart from its own JSON report (part of the Phase 2A pre-annotator snapshot, see
docs/trial8_phase2A_snapshot_exec.md).  Exit code 0 = report written; the row lists are
data, not an error.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read_csv_named(path: Path):
    """Header + records; blank rows are NOT skipped (so indices match the audit join)."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return [], []
    header = rows[0]
    idx = {c: i for i, c in enumerate(header)}
    recs = [{c: (row[idx[c]] if idx[c] < len(row) else "") for c in header} for row in rows[1:]]
    return header, recs

def row_no_set(path: Path) -> set:
    if not path.exists():
        return set()
    _, recs = read_csv_named(path)
    out = set()
    for rec in recs:
        try:
            out.add(int((rec.get("row_no") or "").strip()))
        except ValueError:
            continue
    return out

def fmt(u: dict) -> str:
    return ("   row_no=%-6s | %-22s | hand=%-2s pitch=%-3s | score_pedal=%-7s | groups=%-6s"
            " | in_review_sheet=%-3s in_sample=%s"
            % (u["row_no"], u["onset_location"] or "(none)", u["hand"] or "-", u["pitch"] or "-",
               u["published_score_pedal"] or "(none)", u["groups"] or "(none)",
               "yes" if u["in_review_sheet"] else "no", "yes" if u["in_sample"] else "no"))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default=str(ROOT / "outputs" / "pedal_expansion" / "segments_v1"))
    ap.add_argument("--review", default=str(ROOT / "outputs" / "pedal_expansion" / "review"))
    ap.add_argument("--scope", choices=("review", "all"), default="review",
                    help="row list to print/store in detail (counts are always both)")
    ap.add_argument("--max-print", type=int, default=50)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "pedal_expansion" / "evaluation"
                                        / "phase2a_unlocated_rows.json"))
    a = ap.parse_args()

    seg_root, review_dir = Path(a.segments), Path(a.review)
    if not seg_root.exists():
        print("missing %s" % seg_root)
        return 1

    report = {"scope": a.scope, "segments": []}
    t_events = t_review = t_all = 0
    for seg in sorted(p for p in seg_root.iterdir() if p.is_dir()):
        ev_path = seg / "events.csv"
        if not ev_path.exists():
            continue
        sid = seg.name
        header, events = read_csv_named(ev_path)
        if "reference_onset_ql" not in header:
            print("=" * 104)
            print("%s: events.csv has no reference_onset_ql column -- skipped" % sid)
            report["segments"].append({"segment_id": sid, "status": "no-reference_onset_ql-column"})
            continue
        sheet_rows = row_no_set(review_dir / ("phase2A_A_review_%s.csv" % sid))
        sample_rows = row_no_set(review_dir / "sampled" / ("phase2A_A_review_%s_sample.csv" % sid))

        unlocated = []
        for index, rec in enumerate(events, start=1):
            if (rec.get("reference_onset_ql") or "").strip():
                continue
            unlocated.append({
                "row_no": index,
                "onset_location": rec.get("onset_location", ""),
                "onset_ql": rec.get("onset_ql", ""),
                "hand": rec.get("hand", ""),
                "pitch": rec.get("pitch", ""),
                "published_score_pedal": rec.get("published_score_pedal", ""),
                "groups": rec.get("groups", ""),
                "in_review_sheet": index in sheet_rows,
                "in_sample": index in sample_rows,
            })
        in_review = [u for u in unlocated if u["in_review_sheet"]]
        t_events += len(events)
        t_review += len(in_review)
        t_all += len(unlocated)

        print("=" * 104)
        print("%s: events=%d | review_sheet_rows=%d | sample_rows=%d"
              " | without score-side onset: IN REVIEW SHEET=%d | in all events=%d"
              % (sid, len(events), len(sheet_rows), len(sample_rows), len(in_review), len(unlocated)))
        shown = in_review if a.scope == "review" else unlocated
        for u in shown[:max(a.max_print, 0)]:
            print(fmt(u))
        if len(shown) > a.max_print:
            print("   ... %d more not printed (--scope %s, --max-print %d; full list in the"
                  " JSON report)" % (len(shown) - a.max_print, a.scope, a.max_print))
        report["segments"].append({
            "segment_id": sid, "events": len(events), "review_sheet_rows": len(sheet_rows),
            "sample_rows": len(sample_rows), "unlocated_in_review_sheet": len(in_review),
            "unlocated_in_all_events": len(unlocated), "rows": shown})

    report["total_events"] = t_events
    report["total_unlocated_in_review_sheet"] = t_review
    report["total_unlocated_in_all_events"] = t_all
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("=" * 104)
    print("TOTAL events=%d | without score-side onset: IN REVIEW SHEET=%d | in all events=%d"
          % (t_events, t_review, t_all))
    print("Rows without a score-side onset have column 3 forced to none and are skipped by"
          " both audit tools.")
    print("Human check: read the rendered score at onset_location and confirm no pedal mark.")
    print("report written: %s" % out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
