#!/usr/bin/env python3
"""Phase 2A S8-helper v3: score-domain annotator worksheet.

WHY v3
------
v1/v2 mapped a review row to a score measure with the row's ``onset_location``
column.  That column is produced by
``build_pedal_gold_standard._fmt_beat(onset_ql, segment.bar_ql)`` -- i.e. it is
the PERFORMANCE-domain uniform-tempo measure index (perf bar_ql, e.g. 4.0),
NOT the published-score measure number.  Whenever the perf index range and the
score measure range happen to overlap numerically the lookup silently
"succeeds" and yields the WRONG measure; that is why v2 produced plausible but
invalid sheets for Ballades / S145_2 / Miroirs.

v3 therefore works entirely in the SCORE domain:
  * row -> score QL      : events.csv ``reference_onset_ql`` (joined by row_no)
  * score QL -> measure  : the same measure-start convention used by
    tools/rebuild_segment_reference.py (cumulative score bar_ql from the score
    XML, first <part> only); the slice's first measure index is taken from
    segment_metadata.json ``score_start_measure`` - 1, which the S4 rebuild wrote
    with exactly that convention, so the two are self-consistent.
  * measure number shown : the measure's own ``number`` attribute in the SLICED
    reference_score.musicxml -- i.e. what the annotator sees in MuseScore.
  * evidence             : (a) raw <pedal> directions inside that measure of the
    sliced XML, (b) the nearest entries of reference_pedals.csv (true score QL)
    with their distance.

The worksheet is evidence, not a verdict: annotator A still confirms column 3
(published_score_pedal) against the rendered score.

Usage:
    python tools/phase2a_make_worksheet.py \
        --sampled outputs/pedal_expansion/review/sampled \
        --segments outputs/pedal_expansion/segments_v1 \
        [--tol 0.5] [--out-suffix _worksheet_score]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

EPS = 1e-7
ROOT = Path(__file__).resolve().parents[1]


def ln(tag: str) -> str:
    return tag.split("}")[-1]


def read_csv_named(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    header = rows[0]
    idx = {c: i for i, c in enumerate(header)}
    recs = []
    for row in rows[1:]:
        recs.append({c: (row[idx[c]] if idx[c] < len(row) else "") for c in header})
    return header, recs


def measure_starts(xml_path: Path):
    """Cumulative score-QL start of every measure of the first <part>.

    Identical convention to tools/rebuild_segment_reference.score_measure_starts
    (which selected the very measures that ended up in the slice).
    """
    root = ET.parse(str(xml_path)).getroot()
    starts, cur, bar = [], 0.0, 4.0
    for part in root:
        if ln(part.tag) != "part":
            continue
        for m in part.findall("measure"):
            starts.append(cur)
            attrs = m.find("attributes")
            if attrs is not None:
                beats = attrs.findtext("time/beats")
                beat_type = attrs.findtext("time/beat-type")
                if beats and beat_type:
                    bar = 4.0 * float(beats) / float(beat_type)
            cur += bar
        break
    return starts


def sliced_measures(xml_path: Path):
    """[(number_attr, [(pedal_type, offset_text), ...]), ...] in slice order."""
    root = ET.parse(str(xml_path)).getroot()
    out = []
    for part in root:
        if ln(part.tag) != "part":
            continue
        for m in part.findall("measure"):
            peds = []
            for d in m.findall("direction"):
                for dt in d.findall("direction-type"):
                    p = dt.find("pedal")
                    if p is not None:
                        o = d.find("offset")
                        peds.append((p.get("type", "?"),
                                     (o.text or "").strip() if o is not None else ""))
            out.append((m.get("number"), peds))
        break
    return out


def ref_pedal_rows(seg_dir: Path):
    path = seg_dir / "reference_pedals.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((float(r["position_ql"]), r.get("event_type", "")))
            except (KeyError, ValueError, TypeError):
                continue
    return sorted(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sampled", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--tol", type=float, default=0.5,
                    help="QL tolerance for listing nearby reference pedal marks")
    ap.add_argument("--out-suffix", default="_worksheet_score")
    a = ap.parse_args()

    seg_root = Path(a.segments)
    sdir = Path(a.sampled)
    build_log_path = seg_root / "build_log.json"
    build_log = json.loads(build_log_path.read_text(encoding="utf-8")) if build_log_path.exists() else []
    log_by_id = {e["segment_id"]: e for e in build_log}

    files = sorted(f for f in os.listdir(sdir)
                   if f.startswith("phase2A_A_review_") and f.endswith("_sample.csv"))
    if not files:
        raise SystemExit(f"no *_sample.csv under {sdir}")

    written = 0
    for fn in files:
        sid = fn[len("phase2A_A_review_"):-len("_sample.csv")]
        seg_dir = seg_root / sid
        _, sampled = read_csv_named(sdir / fn)
        meta_p, xmlp = seg_dir / "segment_metadata.json", seg_dir / "reference_score.musicxml"
        evp = seg_dir / "events.csv"
        for p in (meta_p, xmlp, evp):
            if not p.exists():
                print(f"{sid}: MISSING {p} -- skipped")
                break
        else:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            entry = log_by_id.get(sid)
            if entry is None:
                print(f"{sid}: not in build_log.json -- skipped")
                continue
            xml_rel = (entry.get("manifest") or {}).get("xml_score", "")
            full_xml = ROOT / "data" / "ASAP" / xml_rel
            if not full_xml.exists():
                print(f"{sid}: MISSING full score {full_xml} -- skipped")
                continue

            starts_full = measure_starts(full_xml)
            first = int(meta.get("score_start_measure", 0)) - 1
            last = int(meta.get("score_end_measure", 0)) - 1
            bar_ql = float(meta.get("score_bar_ql", 4.0))
            sliced = sliced_measures(xmlp)

            _, ev_recs = read_csv_named(evp)
            by_row = {i: r for i, r in enumerate(ev_recs, start=1)}
            ref_peds = ref_pedal_rows(seg_dir)

            if len(sliced) != last - first + 1:
                print(f"  [warn] slice length {len(sliced)} != expected {last - first + 1}")

            lines = [
                f"# segment={sid} domain=SCORE rows={len(sampled)} tol={a.tol}",
                f"# score window: measures {meta.get('score_start_measure')}..{meta.get('score_end_measure')}"
                f" | score_bar_ql={bar_ql} | score QL {meta.get('score_start_ql')}..{meta.get('score_end_ql')}",
                "# NOTE: onset_location below is PERFORMANCE-domain (uniform tempo) --"
                " use the 'score m.' column to locate the note in the sliced MusicXML.",
                "# row_no | perf onset_location | hand pitch | score m.<n> beat <b>"
                " | published_score_pedal(3) | performance_pedal_action(2) | class"
                " | <pedal> in that score measure | nearest reference_pedals (type dQL)",
            ]
            n_noref = n_nomeasure = n_withpedal = n_near = 0
            qls = []
            for row in sampled:
                rno_txt = row.get("row_no", "")
                try:
                    rno = int(rno_txt)
                except ValueError:
                    rno = -1
                ev = by_row.get(rno, {})
                ref_txt = (ev.get("reference_onset_ql", "") or "").strip()
                mnum, beat, pedstr, near = "--", "--", "(no score ref)", "(n/a)"
                if ref_txt:
                    try:
                        ql = float(ref_txt)
                    except ValueError:
                        ql = None
                    if ql is not None:
                        qls.append(ql)
                        i = bisect.bisect_right(starts_full, ql + EPS) - 1
                        i = max(0, min(i, len(starts_full) - 1))
                        k = i - first
                        if 0 <= k < len(sliced):
                            num, peds = sliced[k]
                            mnum = num if num is not None else str(i + 1)
                            beat = f"{(ql - starts_full[i]) / bar_ql + 1.0:.3f}"
                            if peds:
                                n_withpedal += 1
                                pedstr = "; ".join(f"{t}@{o}" if o else t for t, o in peds)
                            else:
                                pedstr = "(none)"
                        else:
                            n_nomeasure += 1
                            mnum = f"out-of-slice(idx {i})"
                else:
                    n_noref += 1
                if ref_peds and ref_txt:
                    try:
                        ql = float(ref_txt)
                        cand = [(abs(p - ql), t, p) for p, t in ref_peds
                                if abs(p - ql) <= a.tol + EPS]
                        cand.sort()
                        if cand:
                            n_near += 1
                            near = "; ".join(f"{t} d{d:.3f}(pos {p:g})" for d, t, p in cand[:2])
                        else:
                            near = "(none within tol)"
                    except ValueError:
                        pass
                lines.append(" | ".join([
                    str(rno_txt), row.get("onset_location", ""),
                    f"{row.get('hand','')} {row.get('pitch','')}",
                    f"score m.{mnum} beat {beat}",
                    row.get("published_score_pedal", ""),
                    row.get("performance_pedal_action", ""),
                    row.get("review_class", ""),
                    pedstr, near]))

            out = sdir / f"annotatorA{a.out_suffix}_{sid}.txt"
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            written += 1
            print("=" * 100)
            print(f"{sid} | sampled rows={len(sampled)} | slice measures={len(sliced)} "
                  f"(idx {first}..{last}, numbers {sliced[0][0]}..{sliced[-1][0]})")
            print(f"  rows w/o reference_onset_ql: {n_noref} | out-of-slice: {n_nomeasure}"
                  f" | mapped rows whose score measure has <pedal>: {n_withpedal}"
                  f" | rows with a reference_pedals entry within {a.tol} QL: {n_near}")
            if qls:
                print(f"  score QL span of mapped rows: {min(qls):g}..{max(qls):g}")
            print(f"  first data line: {lines[4]}")
            print(f"  worksheet WRITTEN: {out}")
    print(f"TOTAL worksheets written: {written}/{len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
