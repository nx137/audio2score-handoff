#!/usr/bin/env python3
"""Phase 2A S8-helper: build per-segment annotator-A worksheets.

Joins the sampled F-row list (reviewer fill-in CSV) with the pedal direction
markers found *directly* in that segment's reference_score.musicxml, so
annotator A can check column 3 (published_score_pedal) against the score
without hunting through MuseScore for every row.

Column access is BY NAME (never by hard-coded position): the review CSVs are
17 cols + reviewer_confirm + reviewer_note = 19 cols, and hand-written integer
indices drift easily (onset_ql sits at index 5).

SAFETY RULE: a worksheet is written ONLY when the direct measure-number match
is complete (every onset_location measure exists in the MusicXML measure
number set). Otherwise the tool prints diagnostics and writes nothing -- a
mis-aligned comparison sheet must never reach the annotator. Use --offset N
only after main control has confirmed the correct shift.

Usage:
    python tools/phase2a_make_worksheet.py \
        --sampled outputs/pedal_expansion/review/sampled \
        --segments outputs/pedal_expansion/segments_v1 \
        [--offset N] [--out-suffix _worksheet]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from xml.etree import ElementTree as ET

LOC_RE = re.compile(r"\s*m\.(\d+)")


def ln(tag: str) -> str:
    return tag.split("}")[-1]


def read_csv_named(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    idx = {c: i for i, c in enumerate(header)}
    recs = []
    for row in rows[1:]:
        recs.append({c: (row[idx[c]] if idx[c] < len(row) else "") for c in header})
    return header, recs


def xml_index(xmlp):
    root = ET.parse(xmlp).getroot()
    all_no, ped_by_meas, skipped = [], {}, 0
    for part in root.iter():
        if ln(part.tag) != "part":
            continue
        for m in part.findall("measure"):
            try:
                no = int(str(m.get("number")).strip())
            except Exception:
                skipped += 1
                continue
            all_no.append(no)
            peds = []
            for d in m.findall("direction"):
                for dt in d.findall("direction-type"):
                    p = dt.find("pedal")
                    if p is not None:
                        off = ""
                        o = d.find("offset")
                        if o is not None and o.text and o.text.strip():
                            off = o.text.strip()
                        peds.append((p.get("type", "?"), off))
            if peds:
                ped_by_meas[no] = peds
    return all_no, ped_by_meas, skipped


def parse_measure(loc):
    mm = LOC_RE.match(loc or "")
    return int(mm.group(1)) if mm else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sampled", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--offset", type=int, default=None,
                    help="measured shift: xml_measure = csv_measure - offset (only after main-control confirmation)")
    ap.add_argument("--out-suffix", default="_worksheet")
    a = ap.parse_args()

    sdir = a.sampled
    files = sorted(f for f in os.listdir(sdir)
                   if f.startswith("phase2A_A_review_") and f.endswith("_sample.csv"))
    if not files:
        raise SystemExit(f"no *_sample.csv under {sdir}")

    written = 0
    for fn in files:
        sid = fn[len("phase2A_A_review_"):-len("_sample.csv")]
        header, recs = read_csv_named(os.path.join(sdir, fn))
        xmlp = os.path.join(a.segments, sid, "reference_score.musicxml")
        if not os.path.exists(xmlp):
            print(f"{sid}: MISSING {xmlp} -- skipped (no sheet written)")
            continue
        all_no, ped_by_meas, skipped = xml_index(xmlp)
        csv_meas = sorted({parse_measure(r.get("onset_location", "")) for r in recs} - {None})
        hit = sorted(set(csv_meas) & set(all_no))
        direct_full = bool(csv_meas) and len(hit) == len(csv_meas)

        print("=" * 100)
        print(f"{sid} | rows={len(recs)} | cols={len(header)}")
        print(f"  xml measures: {min(all_no) if all_no else '-'}..{max(all_no) if all_no else '-'}"
              f" | n={len(all_no)} | non-int skipped={skipped}"
              f" | measures with pedal: {len(ped_by_meas)}")
        print(f"  csv onset measures from onset_location: n={len(csv_meas)} first20={csv_meas[:20]}")
        print(f"  direct intersection: {len(hit)}/{len(csv_meas)} -> direct_full={direct_full}")
        if not direct_full and all_no and csv_meas:
            guesses = {
                "csv_first_minus_xml_min": csv_meas[0] - min(all_no),
                "csv_last_minus_xml_max": csv_meas[-1] - max(all_no),
            }
            for name, off in guesses.items():
                mapped = {x - off for x in csv_meas}
                print(f"  probe {name}={off} -> hits {len(mapped & set(all_no))}/{len(csv_meas)}")
        meta = os.path.join(a.segments, sid, "segment_metadata.json")
        if os.path.exists(meta):
            try:
                md = json.load(open(meta, encoding="utf-8"))
                sel = {k: v for k, v in md.items()
                       if any(s in k.lower() for s in ("score", "measure", "window", "bar"))}
                if sel:
                    print(f"  segment_metadata window keys: {sel}")
            except Exception as e:
                print(f"  segment_metadata unreadable: {e}")

        if a.offset is not None:
            mode = f"offset:{a.offset}"
            mapping = {x: x - a.offset for x in csv_meas}
        elif direct_full:
            mode = "direct"
            mapping = {x: x for x in csv_meas}
        else:
            print("  >>> NOT WRITTEN: measure numbering not resolvable by direct match;"
                  " waiting for main-control confirmed --offset. No sheet produced.")
            continue

        out = os.path.join(sdir, f"annotatorA{a.out_suffix}_{sid}.txt")
        lines = [
            f"# segment={sid} mode={mode} rows={len(recs)} seed-sample=phase2A-S8",
            "# row_no | onset_location | hand pitch | published_score_pedal(3) |"
            " performance_pedal_action(2) | review_class | xml pedal directions in mapped measure (type@offset)",
        ]
        n_hit = 0
        for r in recs:
            mm = parse_measure(r.get("onset_location", ""))
            tgt = mapping.get(mm)
            peds = ped_by_meas.get(tgt, []) if tgt is not None else []
            if peds:
                n_hit += 1
            pstr = "; ".join((t + ("@" + o if o else "")) for t, o in peds) if peds else "(none)"
            note = (r.get("review_note", "") or "")[:60].replace("\n", " ")
            row = " | ".join([
                r.get("row_no", ""), r.get("onset_location", ""),
                (r.get("hand", "") + " " + r.get("pitch", "")),
                r.get("published_score_pedal", ""), r.get("performance_pedal_action", ""),
                r.get("review_class", ""), pstr])
            if note:
                row += " || auto: " + note
            lines.append(row)
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        written += 1
        print(f"  worksheet WRITTEN: {out} | rows={len(recs)} | rows_with_xml_pedal={n_hit}")
    print(f"TOTAL worksheets written: {written}/{len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
