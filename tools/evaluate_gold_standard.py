#!/usr/bin/env python3
"""Evaluate the pedal gold standard against the P4 system outputs.

For every frozen segment, compares the gold-standard annotation
(events.csv, notation_decision + semantic columns) with the three P4
renderings (p4_rule / p4_learned / p4_no_pedal MusicXML):

  M1 duration match rate  : gold notation_decision vs rendered note
                            duration (pitch+onset aligned, tol 0.05 QL)
  M2 candidate feasibility: share of gold decisions that exist in the
                            candidate set
  M3 pedal event F1       : rendered <pedal> events vs performance
                            pedal_intervals.csv (start/stop alignment)
  M4 semantic mismatch    : acoustic-sustain vs score-none, perf-change
                            vs score-none (paper evidence tables)

Outputs JSON + prints MD-style summary.

Usage:
    python tools/evaluate_gold_standard.py [--out results/pedal_gold_standard_eval_v1.json] [--segments 0-39]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"
ONSET_TOL = 0.125
DUR_TOL = 0.05
PEDAL_TOL = 0.25


def parse_notes(xml_path: Path) -> list[dict]:
    root = ET.parse(str(xml_path)).getroot()
    out = []
    for part_index, part in enumerate(root.findall("part")):
        hand = "RH" if part_index == 0 else "LH"
        divisions = None
        cursor = 0.0
        for measure in part.findall("measure"):
            for child in measure:
                if child.tag == "attributes":
                    d = child.findtext("divisions")
                    if d:
                        divisions = int(d)
                elif child.tag == "backup" and divisions:
                    cursor -= int(child.findtext("duration") or 0) / divisions
                elif child.tag == "forward" and divisions:
                    cursor += int(child.findtext("duration") or 0) / divisions
                elif child.tag == "note" and divisions and child.find("chord") is None:
                    pitch_el = child.find("pitch")
                    if pitch_el is not None:
                        step = pitch_el.findtext("step")
                        octave = pitch_el.findtext("octave")
                        alter = pitch_el.findtext("alter") or "0"
                        pitch = ({"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[step]
                                 + (int(octave) + 1) * 12 + int(alter))
                        dur = int(child.findtext("duration") or 0) / divisions
                        out.append({"hand": hand, "pitch": pitch,
                                    "onset": cursor, "dur": dur})
                    cursor += int(child.findtext("duration") or 0) / divisions
    return out


def parse_pedals(xml_path: Path) -> list[tuple[str, float]]:
    root = ET.parse(str(xml_path)).getroot()
    out = []
    for part in root.findall("part"):
        divisions = None
        cursor = 0.0
        measure_start = 0.0
        for measure in part.findall("measure"):
            measure_start = cursor
            for child in measure:
                if child.tag == "attributes":
                    d = child.findtext("divisions")
                    if d:
                        divisions = int(d)
                elif child.tag == "backup" and divisions:
                    cursor -= int(child.findtext("duration") or 0) / divisions
                elif child.tag == "forward" and divisions:
                    cursor += int(child.findtext("duration") or 0) / divisions
                elif child.tag == "direction":
                    pedal = child.find("direction-type/pedal")
                    if pedal is not None and pedal.get("type") in ("start", "change", "stop"):
                        offset = child.findtext("offset")
                        if offset and divisions:
                            pos = measure_start + int(offset) / divisions
                        else:
                            pos = cursor
                        out.append((pedal.get("type"), round(pos, 9)))
                elif child.tag == "note" and divisions:
                    cursor += int(child.findtext("duration") or 0) / divisions
    return out


def match_gold(gold: list[dict], notes: list[dict]) -> tuple[int, int]:
    matched = 0
    dur_ok = 0
    for g in gold:
        for n in notes:
            if (n["hand"] == g["hand"] and n["pitch"] == g["pitch"]
                    and abs(n["onset"] - g["onset"]) <= ONSET_TOL):
                matched += 1
                if abs(n["dur"] - g["notation"]) <= DUR_TOL:
                    dur_ok += 1
                break
    return matched, dur_ok


def eval_segment(sid: str) -> dict:
    sd = BASE / sid
    meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
    start_ql = float(meta["start_ql"])
    with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    gold = [{"hand": r["hand"], "pitch": int(r["pitch"]),
             "onset": float(r["onset_ql"]) - start_ql,  # absolute -> segment-local
             "notation": float(r["notation_decision"])}
            for r in rows if r["notation_decision"]]
    feas = sum(1 for r in rows
               if float(r["notation_decision"]) in
               {float(x) for x in r["candidate_durations"].split(";") if x.strip()})
    ivs = []
    with (sd / "pedal_intervals.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("start_ql", "").strip():
                ivs.append((float(r["start_ql"]), float(r["end_ql"])))
    perf_starts = sorted({s for s, _ in ivs})
    perf_stops = sorted({e for _, e in ivs})
    res = {"segment": sid, "n_events": len(rows), "gold_notation": len(gold),
           "candidate_feasible": feas}
    pipes = sorted({p.stem for p in sd.glob("p4_*.musicxml")})
    for pipe in pipes:
        notes = parse_notes(sd / f"{pipe}.musicxml")
        matched, dur_ok = match_gold(gold, notes)
        ped = parse_pedals(sd / f"{pipe}.musicxml")
        starts = [o + start_ql for t, o in ped if t == "start"]
        stops = [o + start_ql for t, o in ped if t == "stop"]
        tp_s = sum(1 for s in starts if any(abs(s - x) <= PEDAL_TOL for x in perf_starts))
        tp_p = sum(1 for s in stops if any(abs(s - x) <= PEDAL_TOL for x in perf_stops))
        pr_s = tp_s / len(starts) if starts else 1.0
        rc_s = tp_s / len(perf_starts) if perf_starts else 1.0
        f1_s = 2 * pr_s * rc_s / (pr_s + rc_s) if pr_s + rc_s else 0.0
        pr_p = tp_p / len(stops) if stops else 1.0
        rc_p = tp_p / len(perf_stops) if perf_stops else 1.0
        f1_p = 2 * pr_p * rc_p / (pr_p + rc_p) if pr_p + rc_p else 0.0
        res[pipe] = {"notes": len(notes), "gold_matched": matched,
                     "duration_ok": dur_ok,
                     "duration_rate": round(dur_ok / len(gold), 4) if gold else 0.0,
                     "pedal_start_f1": round(f1_s, 4), "pedal_stop_f1": round(f1_p, 4),
                     "pedal_events": len(ped)}
    res["mismatch_acoustic_yes_score_none"] = sum(
        1 for r in rows if r["acoustic_sustain"] == "yes" and r["published_score_pedal"] == "none")
    res["mismatch_perf_change_score_none"] = sum(
        1 for r in rows if r["performance_pedal_action"] == "change" and r["published_score_pedal"] == "none")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "evaluation" / "gold_standard_eval_v1.json"))
    ap.add_argument("--segments", default=None)
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    if args.segments:
        lo, _, hi = args.segments.partition("-")
        lo, hi = int(lo), int(hi or lo)
        bl = [b for b in bl if lo <= b["index"] <= hi]

    results = [eval_segment(b["segment_id"]) for b in bl]
    out = {"n_segments": len(results), "segments": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    n = sum(r["n_events"] for r in results)
    feas = sum(r["candidate_feasible"] for r in results) / n
    print(f"segments={len(results)} events={n} candidate_feasible={feas:.1%}")
    pipes = sorted({p for r in results for p in r if p in ("p4_rule", "p4_learned", "p4_no_pedal", "p4_fused")})
    for pipe in pipes:
        dr = sum(r[pipe]["duration_rate"] for r in results) / len(results)
        fs = sum(r[pipe]["pedal_start_f1"] for r in results) / len(results)
        fp = sum(r[pipe]["pedal_stop_f1"] for r in results) / len(results)
        pe = sum(r[pipe]["pedal_events"] for r in results)
        print(f"{pipe}: duration_rate={dr:.3f} pedal_start_F1={fs:.3f} pedal_stop_F1={fp:.3f} pedal_events={pe}")
    m1 = sum(r["mismatch_acoustic_yes_score_none"] for r in results)
    m2 = sum(r["mismatch_perf_change_score_none"] for r in results)
    print(f"mismatch: acoustic-yes&score-none={m1}  perf-change&score-none={m2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
