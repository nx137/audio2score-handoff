#!/usr/bin/env python3
"""Phase 2A: independent audit of the score-side extraction behind column 3.

What is audited
---------------
The pipeline fills events.csv column ``published_score_pedal`` (column 3 of the review
sheets) like this::

    reference_pedals.csv  <- score_metrics.pedal_events(full score MusicXML)
                             position = measure_start + cursor + <offset>/divisions,
                             same-(hand,position) start+stop normalised into one "change"
    column 3              <- rebuild_segment_reference.recompute_score_pedal_column():
                             nearest reference_pedals entry by |position - reference_onset_ql|,
                             accepted when that distance <= PEDAL_MATCH_QL (0.25), else "none"

This tool re-derives the same quantity along a deliberately different route, so that a
mistake in slicing / window selection / coordinate domain / implementation shows up as a
disagreement instead of hiding inside a single code path:

  * it reads the FULL ASAP score MusicXML, never the per-segment slice;
  * own measure grid (time-signature aware), own cursor arithmetic, own normalisation;
  * own mapping of a row's score position (events.csv ``reference_onset_ql`` joined by
    ``row_no``) to a measure, reporting that measure's own ``number`` attribute;
  * own nearest-mark decision, compared against the recorded column 3;
  * cross-checks the segment's reference_pedals.csv against the marks of the full score
    (catches window selection / offset handling / slicing drift).

It is an audit, not a replacement: nothing is written except this tool's own JSON report,
and every mismatch is printed together with the raw <pedal> evidence for human adjudication.

Usage
-----
    python tools/phase2a_audit_extraction.py \
        --sampled outputs/pedal_expansion/review/sampled \
        --segments outputs/pedal_expansion/segments_v1 \
        [--selection outputs/pedal_expansion/selection_phase2A.json] \
        [--asap data/ASAP] [--tol 0.25] \
        [--out outputs/pedal_expansion/review/phase2a_extraction_audit.json]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

EPS = 1e-7
ROOT = Path(__file__).resolve().parents[1]


def ln(tag: str) -> str:
    return tag.split("}")[-1]


def read_csv_named(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return [], []
    header = rows[0]
    idx = {c: i for i, c in enumerate(header)}
    recs = [{c: (row[idx[c]] if idx[c] < len(row) else "") for c in header} for row in rows[1:]]
    return header, recs


def parts_hands(root: ET.Element) -> dict:
    hands = {}
    for item in root.findall("part-list/score-part"):
        name = (item.findtext("part-name") or "").lower()
        pid = item.get("id") or ""
        if any(tok in name for tok in ("r.h", "right", "rh")):
            hands[pid] = "RH"
        elif any(tok in name for tok in ("l.h", "left", "lh")):
            hands[pid] = "LH"
        else:
            hands[pid] = None
    return hands


def read_score(xml_path: Path):
    """Own parser -> (measure_starts, measure_numbers, raw_marks, normalised_marks)."""
    root = ET.parse(str(xml_path)).getroot()
    hands = parts_hands(root)
    starts, numbers, raw = [], [], []
    for part_index, part in enumerate(root.findall("part")):
        pid = part.get("id") or str(part_index)
        hand = hands.get(pid) or "LH"
        divisions = None
        measure_start = 0.0
        bar_ql = 4.0
        for measure in part.findall("measure"):
            if part_index == 0:
                starts.append(measure_start)
                numbers.append(measure.get("number"))
            cursor = 0.0
            for child in measure:
                tag = ln(child.tag)
                if tag == "attributes":
                    div = child.findtext("divisions")
                    if div:
                        divisions = int(div)
                    beats = child.findtext("time/beats")
                    beat_type = child.findtext("time/beat-type")
                    if beats and beat_type:
                        bar_ql = 4.0 * float(beats) / float(beat_type)
                elif tag == "backup" and divisions:
                    cursor -= int(child.findtext("duration") or 0) / divisions
                elif tag == "forward" and divisions:
                    cursor += int(child.findtext("duration") or 0) / divisions
                elif tag == "direction":
                    pedal = child.find("direction-type/pedal")
                    if pedal is not None and divisions:
                        offset = child.findtext("offset")
                        local = cursor + (int(offset) / divisions if offset else 0.0)
                        kind = pedal.get("type")
                        if kind in {"start", "change", "stop"}:
                            raw.append((hand, round(measure_start + local, 9), kind))
                elif tag == "note" and divisions and child.find("chord") is None:
                    cursor += int(child.findtext("duration") or 0) / divisions
            measure_start += bar_ql
    grouped = defaultdict(list)
    for hand, position, kind in raw:
        grouped[(hand, position)].append(kind)
    normalised = []
    for (hand, position), kinds in grouped.items():
        if "change" in kinds or ("stop" in kinds and "start" in kinds):
            normalised.append((hand, position, "change"))
            kinds = [k for k in kinds if k not in {"stop", "start", "change"}]
        normalised.extend((hand, position, k) for k in kinds)
    normalised.sort(key=lambda item: (item[1], item[0], item[2]))
    return starts, numbers, raw, normalised


def nearest(events, ql: float, tol: float):
    best, best_d = None, float("inf")
    for hand, position, kind in events:
        d = abs(position - ql)
        if d < best_d:
            best_d, best = d, (hand, position, kind)
    if best is None or best_d > tol + EPS:
        return None, best_d
    return best, best_d


def segment_score_paths(selection_path: Path, asap_root: Path) -> dict:
    out = {}
    if not selection_path.exists():
        return out
    data = json.loads(selection_path.read_text(encoding="utf-8"))
    for entry in data.get("segments", []):
        row = entry.get("row", {})
        composer = row.get("composer") or ""
        title = row.get("title") or ""
        rel = row.get("xml_score") or ""
        if not (composer and title and rel):
            continue
        seg_id = "%s_%s_%d" % (composer, title, int(entry.get("start_measure", 0)) + 1)
        out[seg_id] = (composer, title, rel, asap_root / rel)
    return out


def marks_in_window(events, ql_lo: float, ql_hi: float):
    return [e for e in events if ql_lo - EPS <= e[1] <= ql_hi + EPS]


def raw_in_measure(raw, starts, index: int, bar_ql: float):
    lo = starts[index]
    hi = starts[index + 1] if index + 1 < len(starts) else lo + bar_ql
    return [(h, p, t, round(p - lo, 4)) for (h, p, t) in raw if lo - EPS <= p <= hi + EPS]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sampled", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--selection",
                    default=str(ROOT / "outputs" / "pedal_expansion" / "selection_phase2A.json"))
    ap.add_argument("--asap", default="data/ASAP")
    ap.add_argument("--tol", type=float, default=0.25)
    ap.add_argument("--out",
                    default=str(ROOT / "outputs" / "pedal_expansion" / "review"
                                / "phase2a_extraction_audit.json"))
    a = ap.parse_args()

    sampled = Path(a.sampled)
    segments = Path(a.segments)
    asap_root = Path(a.asap)
    if not asap_root.is_absolute():
        asap_root = ROOT / asap_root
    paths = segment_score_paths(Path(a.selection), asap_root)

    files = sorted(f for f in os.listdir(sampled)
                   if f.startswith("phase2A_A_review_") and f.endswith("_sample.csv"))
    if not files:
        print("no *_sample.csv under %s" % sampled)
        return 1

    report = {"tol": a.tol, "segments": []}
    total_rows = total_match = total_mismatch = 0
    for fn in files:
        sid = fn[len("phase2A_A_review_"):-len("_sample.csv")]
        seg_dir = segments / sid
        print("===== %s =====" % sid)
        entry = {"segment_id": sid}
        try:
            info = paths.get(sid)
            if info is None:
                print("  [skip] segment id not found in %s" % a.selection)
                entry["status"] = "no-selection-entry"
                report["segments"].append(entry)
                continue
            score_path = info[3]
            if not score_path.exists():
                print("  [skip] missing full score %s" % score_path)
                entry["status"] = "missing-full-score"
                report["segments"].append(entry)
                continue
            starts, numbers, raw, marks = read_score(score_path)

            meta = {}
            meta_path = seg_dir / "segment_metadata.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            bar_ql = float(meta.get("score_bar_ql", 4.0))
            first = int(meta.get("score_start_measure", 1)) - 1
            last = int(meta.get("score_end_measure", 1)) - 1
            ql_lo = starts[first]
            ql_hi = starts[last + 1] if last + 1 < len(starts) else starts[last] + bar_ql
            in_win = marks_in_window(marks, ql_lo, ql_hi)
            print("  window: metadata measures %d..%d -> my idx %d..%d"
                  " (file numbers %s..%s) | my QL %g..%g"
                  % (first + 1, last + 1, first, last, numbers[first], numbers[last], ql_lo, ql_hi))
            print("  full-score pedal marks: raw=%d -> normalised=%d | in window=%d"
                  % (len(raw), len(marks), len(in_win)))

            ref_rows = []
            refp = seg_dir / "reference_pedals.csv"
            if refp.exists():
                _, recs = read_csv_named(refp)
                for r in recs:
                    try:
                        ref_rows.append((float(r.get("position_ql", "")), r.get("event_type", "")))
                    except (TypeError, ValueError):
                        continue
            worst = 0.0
            unmatched = []
            for pos, kind in ref_rows:
                best, bd = nearest(marks, pos, 1e9)
                if best is None:
                    unmatched.append((pos, kind, None))
                    continue
                worst = max(worst, bd)
                if bd > 1e-6:
                    unmatched.append((pos, kind, best[2], round(bd, 6)))
            print("  reference_pedals.csv rows=%d | max |pos_ref - pos_mine| = %.9f | not-exact=%d"
                  % (len(ref_rows), worst, len(unmatched)))
            for item in unmatched[:6]:
                print("     not-exact: %s" % (item,))

            ev_path = seg_dir / "events.csv"
            if not ev_path.exists():
                print("  [skip] missing %s" % ev_path)
                entry["status"] = "missing-events"
                report["segments"].append(entry)
                continue
            _, ev_recs = read_csv_named(ev_path)
            by_row = {i: r for i, r in enumerate(ev_recs, start=1)}

            _, sample = read_csv_named(sampled / fn)
            n_match = n_mismatch = n_noref = 0
            mismatches = []
            for row in sample:
                try:
                    rno = int(row.get("row_no", ""))
                except ValueError:
                    rno = -1
                recorded = (row.get("published_score_pedal", "") or "").strip() or "(empty)"
                ref_txt = ((by_row.get(rno) or {}).get("reference_onset_ql", "") or "").strip()
                if not ref_txt:
                    n_noref += 1
                    mine, dist, where, raws = "none", None, "no reference_onset_ql", []
                else:
                    ql = float(ref_txt)
                    i = bisect.bisect_right(starts, ql + EPS) - 1
                    i = max(0, min(i, len(starts) - 1))
                    native = numbers[i] if i < len(numbers) else "?"
                    beat = (ql - starts[i]) / bar_ql + 1.0
                    inside = first <= i <= last
                    best, dist = nearest(marks, ql, a.tol)
                    mine = best[2] if best else "none"
                    where = "m.%s beat %.3f%s" % (native, beat, "" if inside else " (OUTSIDE window)")
                    raws = raw_in_measure(raw, starts, i, bar_ql)
                ok = (mine == recorded)
                if ok:
                    n_match += 1
                else:
                    n_mismatch += 1
                    mismatches.append({
                        "row_no": row.get("row_no", ""), "onset_location": row.get("onset_location", ""),
                        "reference_onset_ql": ref_txt, "recorded": recorded, "mine": mine,
                        "distance_ql": None if dist is None else round(dist, 6), "where": where,
                        "raw_marks_in_measure": raws,
                    })
                    print("  MISMATCH row_no=%s recorded=%s mine=%s d=%s | %s | raw=%s"
                          % (row.get("row_no", ""), recorded, mine,
                             "n/a" if dist is None else round(dist, 6), where, raws))
            total_rows += len(sample)
            total_match += n_match
            total_mismatch += n_mismatch
            print("  rows=%d | match=%d | mismatch=%d | rows without reference_onset_ql=%d"
                  % (len(sample), n_match, n_mismatch, n_noref))
            entry.update({
                "rows": len(sample), "match": n_match, "mismatch": n_mismatch,
                "rows_without_reference_onset_ql": n_noref,
                "metadata_window": [first + 1, last + 1],
                "my_window_index": [first, last],
                "file_numbers_window": [numbers[first], numbers[last]],
                "full_score_raw_marks": len(raw), "full_score_normalised_marks": len(marks),
                "marks_in_window": len(in_win),
                "reference_pedals_rows": len(ref_rows),
                "ref_vs_mine_max_abs_diff": worst,
                "ref_vs_mine_not_exact": unmatched[:20],
                "mismatches": mismatches,
            })
        except Exception as exc:
            print("  [error] %s: %s" % (type(exc).__name__, exc))
            entry["status"] = "error: %s: %s" % (type(exc).__name__, exc)
        report["segments"].append(entry)

    report["total_rows"] = total_rows
    report["total_match"] = total_match
    report["total_mismatch"] = total_mismatch
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("=" * 96)
    print("TOTAL rows=%d match=%d mismatch=%d" % (total_rows, total_match, total_mismatch))
    print("VERDICT: %s" % ("all sampled rows agree with the independent re-derivation"
                           if total_mismatch == 0 else
                           "%d disagreement(s) -- see the MISMATCH lines" % total_mismatch))
    print("report written: %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
