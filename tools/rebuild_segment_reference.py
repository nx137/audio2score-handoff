#!/usr/bin/env python3
"""Rebuild score-side reference artifacts with the correct coordinate mapping.

Root cause
----------
build_pedal_gold_standard.py mixed two incommensurable coordinate systems:

* PERFORMANCE QL -- a nominal time stamp on the performance time axis
  (onset_ql = seconds * tempo_bpm / 60).
* SCORE QL -- the published-score MIDI beat position (midi_score tick / PPQ),
  accumulated per measure from the start of the piece.

segment.start_ql / segment.end_ql are PERFORMANCE QL, but they were used to
filter SCORE-QL data:

* write_reference_files() filtered reference_score_events() / pedal_events()
  by segment.start_ql/end_ql, so reference_events.csv and reference_pedals.csv
  selected the WRONG score positions.  For Chopin_Scherzos_20_254 the
  performance window [1012, 1028) selected score measures 338-342 instead of
  the true 595-608 (the two windows happen to share the same numeric range).
* slice_musicxml() sliced measures by the PERFORMANCE measure index, so
  reference_score.musicxml contained the wrong measures.
* segment_metadata.json inherited time_signature / bar_ql from the PERFORMANCE
  MIDI, whose time-signature metadata can be wrong (e.g. Yamaha 4/4 recorded
  for a published 3/4 piece).
* prefill_events.classify_score() matched performance onset_ql against
  score-QL pedal positions, corrupting published_score_pedal.

Fix
---
Map the performance window onto a SCORE QL window with the external alignment
CSV (performance onset_ql <-> reference_onset_ql), then rebuild:

* reference_events.csv      (score events inside the score window)
* reference_pedals.csv      (score pedal marks inside the score window)
* reference_score.musicxml  (sliced by the correct score measures)
* segment_metadata.json     (adds score_* fields; keeps old performance fields)
* events.csv                (recomputes ONLY published_score_pedal)

The five performance/acoustic annotation columns and all information columns
of events.csv are left untouched: their data sources never touched score QL.

Usage
-----
    python tools/rebuild_segment_reference.py                 # all 40 segments
    python tools/rebuild_segment_reference.py --segment ID    # one segment
    python tools/rebuild_segment_reference.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "audio2score" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

from auto_label_candidates import reference_score_events  # noqa: E402
from score_metrics import pedal_events  # noqa: E402
from build_pedal_gold_standard import slice_musicxml  # noqa: E402

EPS = 1e-7
SCORE_MARGIN_QL = 0.5    # extra score-QL margin around the mapped window
PEDAL_MATCH_QL = 0.25    # published_score_pedal matching window (rule 2.3)

BASE = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"
ALIGN_DIR = BASE / "_alignments"


def read_alignment(path: Path) -> list[tuple[float, float]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append((float(row["onset_ql"]), float(row["reference_onset_ql"])))
            except (KeyError, ValueError):
                continue
    return sorted(rows, key=lambda item: item[0])


def interp_ref(rows: list[tuple[float, float]], perf_ql: float) -> float | None:
    if not rows:
        return None
    if perf_ql <= rows[0][0] + EPS:
        return rows[0][1]
    if perf_ql >= rows[-1][0] - EPS:
        return rows[-1][1]
    lo, hi = 0, len(rows) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if rows[mid][0] <= perf_ql:
            lo = mid
        else:
            hi = mid
    p1, r1 = rows[lo]
    p2, r2 = rows[hi]
    if p2 - p1 <= EPS:
        return r1
    return r1 + (perf_ql - p1) * (r2 - r1) / (p2 - p1)


def map_score_window(rows, start_ql: float, end_ql: float) -> tuple[float, float, str] | None:
    # Three-level fallback:
    #   1. strict  - aligned rows inside the exact performance window (best;
    #                for Chopin_Scherzos_20_254 this yields [1783, 1824))
    #   2. margin  - aligned rows inside a small margin around the window
    #   3. interp  - boundary interpolation over the whole alignment
    # Method 1 avoids over-extending the score window with rows beyond the
    # performance window (e.g. perf 1028.38 -> ref 1825 would add a measure).
    strict = [r for (_p, r) in rows if start_ql - EPS <= _p <= end_ql + EPS]
    if strict:
        return min(strict), max(strict), "strict"
    margin = [r for (_p, r) in rows
              if start_ql - SCORE_MARGIN_QL - EPS <= _p <= end_ql + SCORE_MARGIN_QL + EPS]
    if margin:
        return min(margin), max(margin), "margin"
    s0, s1 = interp_ref(rows, start_ql), interp_ref(rows, end_ql)
    if s0 is None or s1 is None or s1 <= s0 + EPS:
        return None
    return s0, s1, "interp"


def score_measure_starts(xml_path: Path) -> list[float]:
    root = ET.parse(str(xml_path)).getroot()
    part = root.find("part")
    if part is None:
        return []
    starts = []
    measure_start = 0.0
    bar_ql = 4.0
    for measure in part.findall("measure"):
        starts.append(measure_start)
        attrs = measure.find("attributes")
        if attrs is not None:
            beats = attrs.findtext("time/beats")
            beat_type = attrs.findtext("time/beat-type")
            if beats and beat_type:
                bar_ql = 4.0 * float(beats) / float(beat_type)
        measure_start += bar_ql
    return starts


def score_time_sig(xml_path: Path) -> tuple[int, int]:
    root = ET.parse(str(xml_path)).getroot()
    part = root.find("part")
    if part is not None:
        for measure in part.findall("measure"):
            attrs = measure.find("attributes")
            if attrs is None:
                continue
            beats = attrs.findtext("time/beats")
            beat_type = attrs.findtext("time/beat-type")
            if beats and beat_type:
                return int(float(beats)), int(float(beat_type))
    return 4, 4


def measure_index_range(starts: list[float], s0: float, s1: float) -> tuple[int, int]:
    if not starts:
        return 0, 0
    first = 0
    for i, s in enumerate(starts):
        if s <= s0 + EPS:
            first = i
    last = len(starts) - 1
    for i, s in enumerate(starts):
        if s >= s1 - EPS:
            last = i - 1
            break
    last = max(last, first)
    return first, last


def fmt_beat(offset_ql: float, bar_ql: float) -> str:
    measure = int(math.floor(offset_ql / bar_ql)) + 1
    beat = (offset_ql % bar_ql) + 1.0
    return "m.%d beat %.3f" % (measure, beat)


def recompute_score_pedal_column(seg_dir: Path, ref_pedals: list) -> int:
    events_path = seg_dir / "events.csv"
    raw = events_path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return -1
    header, body = rows[0], rows[1:]
    col = {name: i for i, name in enumerate(header)}
    if "published_score_pedal" not in col or "reference_onset_ql" not in col:
        return -1
    c_psp, c_ro = col["published_score_pedal"], col["reference_onset_ql"]
    changed = 0
    for r in body:
        if not r:
            continue
        onset_txt = r[c_ro] if c_ro < len(r) else ""
        try:
            onset = float(onset_txt)
        except ValueError:
            onset = None
        if onset is None:
            value = "none"
        else:
            best, best_d = None, float("inf")
            for p in ref_pedals:
                d = abs(float(p["position_ql"]) - onset)
                if d < best_d:
                    best_d, best = d, p
            value = best["event_type"] if (best is not None and best_d <= PEDAL_MATCH_QL) else "none"
        if c_psp >= len(r):
            r.extend([""] * (c_psp - len(r) + 1))
        if r[c_psp] != value:
            r[c_psp] = value
            changed += 1
    with events_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\r\n" if newline == "\r\n" else "\n")
        first = header[0]
        writer.writerow([("\ufeff" if has_bom else "") + first] + header[1:])
        writer.writerows(body)
    return changed


def rebuild_segment(seg_id: str, dry_run: bool = False) -> dict:
    record = {"segment_id": seg_id}
    seg_dir = BASE / seg_id
    align_path = ALIGN_DIR / (seg_id + ".csv")
    if not seg_dir.exists() or not align_path.exists():
        record["status"] = "missing-input"
        return record

    build_log = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    entry = next((b for b in build_log if b["segment_id"] == seg_id), None)
    if entry is None:
        record["status"] = "not-in-build-log"
        return record
    meta = entry["metadata"]
    manifest = entry["manifest"]
    perf_start_ql = float(meta["start_ql"])
    perf_end_ql = float(meta["end_ql"])

    xml_rel = manifest.get("xml_score", "")
    xml_path = ROOT / "data" / "ASAP" / xml_rel
    if not xml_path.exists():
        record["status"] = "missing-xml"
        return record

    rows = read_alignment(align_path)
    mapped = map_score_window(rows, perf_start_ql, perf_end_ql)
    if mapped is None:
        record["status"] = "no-alignment-coverage"
        record["perf_start_ql"] = perf_start_ql
        record["perf_end_ql"] = perf_end_ql
        return record
    score_start_ql, score_end_ql, mapping_method = mapped
    starts = score_measure_starts(xml_path)
    first, last = measure_index_range(starts, score_start_ql, score_end_ql)
    s_num, s_den = score_time_sig(xml_path)
    score_bar_ql = 4.0 * s_num / s_den

    record["perf_start_ql"] = perf_start_ql
    record["perf_end_ql"] = perf_end_ql
    record["mapping_method"] = mapping_method
    record["score_start_ql"] = round(score_start_ql, 6)
    record["score_end_ql"] = round(score_end_ql, 6)
    record["score_start_measure"] = first + 1
    record["score_end_measure"] = last + 1
    record["score_time_signature"] = [s_num, s_den]

    if dry_run:
        record["status"] = "dry-run"
        return record

    events = reference_score_events(str(xml_path))
    sel_events = [e for e in events if score_start_ql - EPS <= e.start_ql < score_end_ql]
    with (seg_dir / "reference_events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "hand", "pitch", "start_ql", "start_location", "duration_ql",
            "part_id", "voice", "tie_start", "tie_stop",
        ])
        writer.writeheader()
        for e in sorted(sel_events, key=lambda item: (item.hand, item.start_ql, item.pitch)):
            writer.writerow({
                "hand": e.hand, "pitch": e.pitch,
                "start_ql": "%.6f" % e.start_ql,
                "start_location": fmt_beat(e.start_ql, score_bar_ql),
                "duration_ql": "%.6f" % e.duration_ql,
                "part_id": e.part_id, "voice": e.voice,
                "tie_start": int(e.tie_start), "tie_stop": int(e.tie_stop),
            })

    pedals = pedal_events(str(xml_path))
    sel_pedals = [p for p in pedals if score_start_ql - EPS <= p.position_ql < score_end_ql]
    with (seg_dir / "reference_pedals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "hand", "position_ql", "position_location", "event_type",
        ])
        writer.writeheader()
        for p in sel_pedals:
            writer.writerow({
                "hand": p.hand,
                "position_ql": "%.6f" % p.position_ql,
                "position_location": fmt_beat(p.position_ql, score_bar_ql),
                "event_type": p.event_type,
            })

    slice_musicxml(xml_path, seg_dir / "reference_score.musicxml", first, last)

    meta_path = seg_dir / "segment_metadata.json"
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    m["score_start_ql"] = round(score_start_ql, 6)
    m["score_end_ql"] = round(score_end_ql, 6)
    m["score_start_measure"] = first + 1
    m["score_end_measure"] = last + 1
    m["score_bar_ql"] = score_bar_ql
    m["score_time_signature"] = [s_num, s_den]
    m["coordinate_fix"] = {
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "method": "alignment-mapped-score-window",
        "note": ("time_signature/bar_ql are PERFORMANCE-MIDI metadata (may be "
                 "wrong, e.g. Yamaha 4/4 vs published 3/4); score_time_signature / "
                 "score_bar_ql are the published-score values used for all "
                 "score-side artifacts."),
    }
    meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ref_pedal_rows = list(csv.DictReader(
        (seg_dir / "reference_pedals.csv").open(encoding="utf-8-sig", newline="")))
    changed = recompute_score_pedal_column(seg_dir, ref_pedal_rows)

    record["status"] = "rebuilt"
    record["n_score_events"] = len(sel_events)
    record["n_score_pedals"] = len(sel_pedals)
    record["published_score_pedal_changed"] = changed
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", action="append", default=[],
                        help="segment id(s); default: all segments in build_log")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    build_log = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    seg_ids = args.segment or [b["segment_id"] for b in build_log]

    results = []
    for sid in seg_ids:
        rec = rebuild_segment(sid, args.dry_run)
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False))

    out = BASE / "evaluation" / "segment_reference_rebuild.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_ok = sum(1 for r in results if r["status"] in ("rebuilt", "dry-run"))
    print("[done] %d/%d segments processed -> %s" % (n_ok, len(results), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
