#!/usr/bin/env python3
"""Phase 2A: independent audit of column 3 (published_score_pedal).

WHY
---
The Phase 2A gate rests on column 3 being a faithful reading of the published
score AND on every row being located in the right score measure.  Both are
produced inside the pipeline (build_pedal_gold_standard ->
rebuild_segment_reference).  A bug of exactly that class already happened once:
worksheet v1/v2 located rows with the PERFORMANCE-domain ``onset_location`` and
produced plausible but wrong measures.

This tool re-derives everything from the ORIGINAL ASAP score
(``data/ASAP/**/xml_score.musicxml``) with code that shares nothing with the
prefill/rebuild path, then reconciles against the on-disk review sheet:

  measure grid         cumulative score bar_ql per measure of the first <part>,
                       taking each measure's own <time>; identical convention to
                       tools/rebuild_segment_reference.score_measure_starts,
                       which is the base of every score QL number on disk
  pedal mark position  grid start + position inside the measure (note / forward
                       / backup aware) + <offset>
  mark normalisation   marks sharing one instant: only start -> start, only stop
                       -> stop, stop+start (re-pedal) -> change
  row position         events.csv ``reference_onset_ql``, joined by row_no
                       (1-based events.csv row index -- the same join the
                       annotator worksheet uses)

Gates / checks per segment
--------------------------
  1 rowno_join          review row_no -> events.csv row agrees on
                        onset_location / hand / pitch
  2 col3_consistency    review column 3 == events.csv column 3
  3 slice_window        the measure numbers of the sliced reference_score.xml
                        equal measures [score_start_measure-1 .. score_end_measure-1]
                        of the full score
  4 window_containment  every row onset lies in [score_start_ql, score_end_ql]
  5 mark_reconciliation F rows (column 3 in start/change/stop): a pedal mark
                        exists AT the row onset and its normalised type equals
                        column 3; other rows: no mark at the onset.  Marks
                        within --near QL but not at the onset are reported as
                        near_miss (the barline-crossing rows).
  6 f_group_split       rows with groups containing "F" vs column 3 in
                        start/change/stop must be the same set

Writes a JSON report (committed as part of the Phase 2A pre-annotator snapshot,
see docs/trial8_phase2A_snapshot_exec.md) and prints a summary.
Exit code 0 = report written; mismatch counts are data, not an error.

Usage
-----
    python tools/phase2a_audit_score_pedal.py \
        --segments outputs/pedal_expansion/segments_v1 \
        --review   outputs/pedal_expansion/review \
        --out      outputs/pedal_expansion/evaluation/phase2a_score_pedal_audit.json \
        [--tol 1e-3] [--near 0.5] [--max-examples 3]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EPS = 1e-9
ROOT = Path(__file__).resolve().parents[1]
F_TYPES = ("start", "change", "stop")
JOIN_FIELDS = ("onset_location", "hand", "pitch")


def ln(tag: str) -> str:
    return tag.split("}")[-1]


def read_csv_named(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], []
    header = rows[0]
    idx = {c: i for i, c in enumerate(header)}
    recs = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        recs.append({c: (row[idx[c]] if idx[c] < len(row) else "") for c in header})
    return header, recs


def first_part(root):
    for child in root:
        if ln(child.tag) == "part":
            return child
    return None


def parse_score(path: Path) -> dict:
    """Measure grid + pedal marks of the first <part>, score QL domain."""
    root = ET.parse(str(path)).getroot()
    part = first_part(root)
    if part is None:
        raise ValueError(f"no <part> in {path}")
    numbers, starts, bars, sounded, marks = [], [], [], [], []
    div = 1.0
    bar = 4.0
    cur = 0.0
    for m in part.findall("measure"):
        numbers.append(m.get("number"))
        starts.append(cur)
        attrs = m.find("attributes")
        if attrs is not None:
            d = attrs.findtext("divisions")
            if d:
                div = float(d)
            beats = attrs.findtext("time/beats")
            btype = attrs.findtext("time/beat-type")
            if beats and btype:
                bar = 4.0 * float(beats) / float(btype)
        bars.append(bar)
        pos = 0.0
        top = 0.0
        for ch in m:
            tag = ln(ch.tag)
            if tag == "note":
                if ch.find("grace") is not None or ch.find("chord") is not None:
                    continue
                dur = ch.findtext("duration")
                if dur is None:
                    continue
                pos += float(dur) / div
                top = max(top, pos)
            elif tag == "forward":
                pos += float(ch.findtext("duration") or 0) / div
                top = max(top, pos)
            elif tag == "backup":
                pos -= float(ch.findtext("duration") or 0) / div
            elif tag == "direction":
                off = ch.findtext("offset")
                off_ql = float(off) / div if off else 0.0
                for dt in ch.findall("direction-type"):
                    p = dt.find("pedal")
                    if p is None:
                        continue
                    marks.append((cur + pos + off_ql, (p.get("type") or "?").strip()))
        sounded.append(top)
        cur += bar
    return dict(numbers=numbers, starts=starts, bars=bars,
                sounded=sounded, marks=sorted(marks, key=lambda x: x[0]))


def cluster_marks(marks, eps: float):
    """[[ql, [types...]], ...] with marks closer than eps merged."""
    out = []
    for ql, typ in marks:
        if out and abs(ql - out[-1][0]) <= eps:
            out[-1][1].append(typ)
        else:
            out.append([ql, [typ]])
    return out


def normalise(types):
    t = [x for x in types if x in ("start", "stop", "change")]
    if "change" in t:
        return "change", "explicit-change"
    has_s, has_t = "start" in t, "stop" in t
    if has_s and has_t:
        return "change", "re-pedal"
    if has_s:
        return "start", "press"
    if has_t:
        return "stop", "release"
    return None, "continue-only"


def cluster_at(clusters, ql: float, tol: float):
    best = None
    for c in clusters:
        d = abs(c[0] - ql)
        if d <= tol + EPS and (best is None or d < best[0]):
            best = (d, c)
    return best


def audit_segment(sid: str, seg_dir: Path, review_path: Path, asap_root: Path,
                  entry: dict, tol: float, near: float, max_examples: int) -> dict:
    res = dict(segment_id=sid, gates=dict(rowno_join=None, col3_consistency=None,
                                         slice_window=None),
               n_rows=0, n_f=0, agree=0, mismatch=0, near_miss=0,
               no_mark_at_all=0, spurious_none=0, outside_window=0,
               no_reference_onset_ql=0, max_match_distance=None,
               f_group_split=0, examples=[], errors=[])
    meta = json.loads((seg_dir / "segment_metadata.json").read_text(encoding="utf-8"))
    first = int(meta.get("score_start_measure", 0)) - 1
    last = int(meta.get("score_end_measure", 0)) - 1
    q0 = meta.get("score_start_ql")
    q1 = meta.get("score_end_ql")
    xml_rel = (entry.get("manifest") or {}).get("xml_score", "")
    full_xml = asap_root / xml_rel
    if not full_xml.exists():
        res["errors"].append(f"missing full score {full_xml}")
        return res
    full = parse_score(full_xml)
    clusters = cluster_marks(full["marks"], 1e-6)

    # gate 3: slice measures == full measures of the declared window
    sliced = parse_score(seg_dir / "reference_score.musicxml")
    want = full["numbers"][first:last + 1]
    res["gates"]["slice_window"] = (sliced["numbers"] == want)
    res["slice_numbers"] = [sliced["numbers"][0], sliced["numbers"][-1]]
    res["window_numbers"] = [want[0], want[-1]] if want else None

    _, ev = read_csv_named(seg_dir / "events.csv")
    by_row = {i: r for i, r in enumerate(ev, start=1)}
    _, rev = read_csv_named(review_path)
    res["n_rows"] = len(rev)

    dmax = None
    for row in rev:
        try:
            rno = int(row.get("row_no", ""))
        except ValueError:
            res["errors"].append(f"bad row_no {row.get('row_no')!r}")
            continue
        src = by_row.get(rno)
        if src is None:
            res["errors"].append(f"row_no {rno} not present in events.csv")
            continue
        for field in JOIN_FIELDS:
            if field in row and field in src:
                a, b = (row[field] or "").strip(), (src[field] or "").strip()
                if a != b:
                    res["gates"].setdefault("rowno_join_field_mismatches", {})
                    res["gates"]["rowno_join_field_mismatches"][field] = \
                        res["gates"]["rowno_join_field_mismatches"].get(field, 0) + 1
        c3_rev = (row.get("published_score_pedal") or "").strip()
        c3_ev = (src.get("published_score_pedal") or "").strip()
        if c3_rev != c3_ev:
            res["gates"]["col3_consistency"] = False
        elif res["gates"]["col3_consistency"] is None:
            res["gates"]["col3_consistency"] = True
        groups = (row.get("groups") or "").split("|")
        in_f_groups = "F" in [g.strip() for g in groups]
        in_f_col = c3_rev in F_TYPES
        if in_f_groups != in_f_col:
            res["f_group_split"] += 1
        if in_f_col:
            res["n_f"] += 1

        ref_txt = (src.get("reference_onset_ql") or "").strip()
        if not ref_txt:
            res["no_reference_onset_ql"] += 1
            res["examples"].append(dict(row_no=rno, kind="no_reference_onset_ql"))
            continue
        try:
            ql = float(ref_txt)
        except ValueError:
            res["errors"].append(f"row {rno}: bad reference_onset_ql {ref_txt!r}")
            continue
        if q0 is not None and q1 is not None and not (float(q0) - EPS <= ql <= float(q1) + EPS):
            res["outside_window"] += 1

        hit = cluster_at(clusters, ql, tol)
        expect, why = (None, "no-mark")
        if hit is not None:
            d, c = hit
            expect, why = normalise(c[1])
            if dmax is None or d > dmax:
                dmax = d
        if in_f_col:
            if expect is None:
                nearhit = None
                for c in clusters:
                    d = abs(c[0] - ql)
                    if d <= near + EPS and (nearhit is None or d < nearhit[0]):
                        nearhit = (d, c)
                if nearhit is not None:
                    res["near_miss"] += 1
                    kind = "near_miss"
                else:
                    res["no_mark_at_all"] += 1
                    kind = "no_mark_at_all"
            elif expect == c3_rev:
                res["agree"] += 1
                kind = None
            else:
                res["mismatch"] += 1
                kind = "type_mismatch"
            if kind and len(res["examples"]) < max_examples:
                res["examples"].append(dict(row_no=rno, kind=kind, onset_ql=ql,
                                            col3=c3_rev, score_expects=expect,
                                            rule=why,
                                            marks_in_cluster=(hit[1][1] if hit else None)))
        else:
            if expect is not None:
                res["spurious_none"] += 1
                if len(res["examples"]) < max_examples:
                    res["examples"].append(dict(row_no=rno, kind="spurious_none",
                                                onset_ql=ql, col3=c3_rev,
                                                score_expects=expect, rule=why))
    res["max_match_distance"] = dmax
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default=str(ROOT / "outputs/pedal_expansion/segments_v1"))
    ap.add_argument("--review", default=str(ROOT / "outputs/pedal_expansion/review"))
    ap.add_argument("--asap", default=str(ROOT / "data/ASAP"))
    ap.add_argument("--out", default=str(ROOT / "outputs/pedal_expansion/evaluation/phase2a_score_pedal_audit.json"))
    ap.add_argument("--tol", type=float, default=1e-3)
    ap.add_argument("--near", type=float, default=0.5)
    ap.add_argument("--max-examples", type=int, default=3)
    a = ap.parse_args()

    seg_root = Path(a.segments)
    review_dir = Path(a.review)
    log_path = seg_root / "build_log.json"
    if not log_path.exists():
        raise SystemExit(f"missing {log_path}")
    entries = {e["segment_id"]: e for e in json.loads(log_path.read_text(encoding="utf-8"))}

    reports = []
    for sid in sorted(entries):
        seg_dir = seg_root / sid
        review_path = review_dir / f"phase2A_A_review_{sid}.csv"
        if not seg_dir.exists() or not review_path.exists():
            print(f"{sid}: skipped (missing segment dir or review sheet)")
            continue
        reports.append(audit_segment(sid, seg_dir, review_path, Path(a.asap),
                                     entries[sid], a.tol, a.near, a.max_examples))

    tot = dict(rows=0, f=0, agree=0, mismatch=0, near_miss=0, no_mark_at_all=0,
               spurious_none=0, outside_window=0, f_group_split=0)
    for r in reports:
        tot["rows"] += r["n_rows"]
        tot["f"] += r["n_f"]
        tot["agree"] += r["agree"]
        tot["mismatch"] += r["mismatch"]
        tot["near_miss"] += r["near_miss"]
        tot["no_mark_at_all"] += r["no_mark_at_all"]
        tot["spurious_none"] += r["spurious_none"]
        tot["outside_window"] += r["outside_window"]
        tot["f_group_split"] += r["f_group_split"]

    print("=" * 108)
    print(f"{'segment':<34}{'rows':>5}{'F':>5}{'agree':>7}{'mismatch':>9}{'near':>5}"
          f"{'nomark':>7}{'spurious':>9}{'outwin':>7}  gates")
    for r in reports:
        ok = (r["gates"]["slice_window"] and r["gates"]["col3_consistency"] is not False
              and not r["gates"].get("rowno_join_field_mismatches") and not r["errors"])
        print(f"{r['segment_id']:<34}{r['n_rows']:>5}{r['n_f']:>5}{r['agree']:>7}"
              f"{r['mismatch']:>9}{r['near_miss']:>5}{r['no_mark_at_all']:>7}"
              f"{r['spurious_none']:>9}{r['outside_window']:>7}  {'OK' if ok else 'CHECK'}")
        print(f"{'':<34}slice numbers {r.get('slice_numbers')} vs window {r.get('window_numbers')}"
              f" | max match distance {r['max_match_distance']}")
        for e in r["examples"]:
            print(f"{'':<34}  example {e}")
        for err in r["errors"]:
            print(f"{'':<34}  ERROR {err}")
    print("-" * 108)
    print(f"TOTAL rows={tot['rows']} F={tot['f']} agree={tot['agree']} mismatch={tot['mismatch']} "
          f"near_miss={tot['near_miss']} no_mark_at_all={tot['no_mark_at_all']} "
          f"spurious_none={tot['spurious_none']} outside_window={tot['outside_window']} "
          f"f_group_split={tot['f_group_split']}")
    report = dict(tool="phase2a_audit_score_pedal", tol=a.tol, near=a.near,
                  segments=reports, totals=tot)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    verdict = ("AUDIT RESULT: CLEAN" if (tot["mismatch"] == 0 and tot["no_mark_at_all"] == 0
                                         and tot["spurious_none"] == 0 and tot["outside_window"] == 0
                                         and tot["f_group_split"] == 0)
               else "AUDIT RESULT: FINDINGS - see report")
    print(f"{verdict} | report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
