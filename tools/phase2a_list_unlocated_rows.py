#!/usr/bin/env python3
"""Phase 2A: list the events whose score-side onset is missing (no reference_onset_ql).

WHY
---
Column 3 (published_score_pedal) is derived from the row's score-side onset
(events.csv reference_onset_ql -> nearest entry of reference_pedals.csv within
PEDAL_MATCH_QL = 0.25).  A row whose reference_onset_ql is empty therefore has column 3
forced to "none" and CANNOT be checked by either audit tool: phase2a_audit_extraction.py
counts it under "rows without reference_onset_ql", phase2a_audit_score_pedal.py under
"no_reference_onset_ql".  Those rows still need a human eye: read the rendered score at
the printed location and confirm there is no pedal mark there.  This tool produces that
list, per segment, in a form the annotator can use directly.

WHERE THE FIELD LIVES
---------------------
NOT in the 17-column review sheets (phase2A_A_review_<seg>.csv) -- it lives in the
segment's events.csv and is joined by row_no == the 1-based data-row index of that file,
which is exactly the join the audit tools and the annotator worksheet use.  Reading the
review sheet directly returns an empty value for every row.

Usage
-----
    python tools/phase2a_list_unlocated_rows.py \
        [--segments outputs/pedal_expansion/segments_v1] \
        [--review outputs/pedal_expansion/review] \
        [--out outputs/pedal_expansion/evaluation/phase2a_unlocated_rows.json]

Read-only apart from its own JSON report (a work artifact; it is part of the Phase 2A
pre-annotator snapshot, see docs/trial8_phase2A_snapshot_exec.md).  Exit code 0 = report
written; the row lists are data, not an error.
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

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default=str(ROOT / "outputs" / "pedal_expansion" / "segments_v1"))
    ap.add_argument("--review", default=str(ROOT / "outputs" / "pedal_expansion" / "review"))
    ap.add_argument("--out", default=str(ROOT / "outputs" / "pedal_expansion" / "evaluation"
                                        / "phase2a_unlocated_rows.json"))
    a = ap.parse_args()

    seg_root = Path(a.segments)
    review_dir = Path(a.review)
    if not seg_root.exists():
        print("missing %s" % seg_root)
        return 1

    report = {"segments": []}
    total_events = total_unlocated = 0
    for seg in sorted(p for p in seg_root.iterdir() if p.is_dir()):
        ev_path = seg / "events.csv"
        if not ev_path.exists():
            continue
        sid = seg.name
        header, events = read_csv_named(ev_path)
        if "reference_onset_ql" not in header:
            print("=" * 100)
            print("%s: events.csv has no reference_onset_ql column -- skipped" % sid)
            report["segments"].append({"segment_id": sid, "status": "no-reference_onset_ql-column"})
            continue
        sheet = review_dir / ("phase2A_A_review_%s.csv" % sid)
        sample = review_dir / "sampled" / ("phase2A_A_review_%s_sample.csv" % sid)
        sheet_rows, sample_rows = row_no_set(sheet), row_no_set(sample)

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
        total_events += len(events)
        total_unlocated += len(unlocated)
        print("=" * 100)
        print("%s: events=%d | review_sheet_rows=%d | sample_rows=%d | rows without"
              " reference_onset_ql=%d" % (sid, len(events), len(sheet_rows), len(sample_rows),
                                          len(unlocated)))
        for u in unlocated:
            print("   row_no=%s | %s | hand=%s pitch=%s | score_pedal=%s | groups=%s"
                  " | in_review_sheet=%s in_sample=%s"
                  % (u["row_no"], u["onset_location"] or "(none)", u["hand"], u["pitch"],
                     u["published_score_pedal"] or "(none)", u["groups"] or "(none)",
                     "yes" if u["in_review_sheet"] else "no",
                     "yes" if u["in_sample"] else "no"))
        report["segments"].append({"segment_id": sid, "events": len(events),
                                   "review_sheet_rows": len(sheet_rows),
                                   "sample_rows": len(sample_rows),
                                   "unlocated_rows": unlocated})

    report["total_events"] = total_events
    report["total_unlocated"] = total_unlocated
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("=" * 100)
    print("TOTAL events=%d | rows without reference_onset_ql=%d" % (total_events, total_unlocated))
    print("These rows have no score-side onset: column 3 is forced to none and both audit"
          " tools skip them.")
    print("Human check: read the rendered score at onset_location and confirm no pedal mark.")
    print("report written: %s" % out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
