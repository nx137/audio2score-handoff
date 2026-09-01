#!/usr/bin/env python3
"""Evaluate the pedal gold standard against the P4 system outputs.

For every frozen segment, compares the gold-standard annotation
(events.csv, notation_decision + semantic columns) with the P4
renderings (p4_rule / p4_learned / p4_fused / p4_exact / p4_no_pedal
MusicXML):

  M1 duration match rate  : gold notation_decision vs rendered note
                            duration (pitch+onset aligned), graded at
                            0.05 / 0.25 / 1.0 QL + median abs error
  M2 candidate feasibility: share of gold decisions that exist in the
                            candidate set
  M3 pedal event F1       : rendered <pedal> events vs performance
                            pedal_intervals.csv (start/stop alignment),
                            with selectable reference protocol:
                              unclipped - raw start_ql/end_ql (v1-v3)
                              inwindow  - only events visible inside the
                                          segment window (default, fair)
                              visible   - window events + cross-window start
                                          at window start; no phantom stops
                                          (recommended for full-piece view)
                              clipped   - clipped_start_ql/clipped_end_ql
                            Reports macro & micro averages and a bootstrap
                            95% CI on the macro average. `change` events
                            count as both a start and a stop.
  M4 semantic mismatch    : acoustic-sustain vs score-none, perf-change
                            vs score-none (paper evidence tables)

Outputs JSON + prints MD-style summary.

Usage:
    python tools/evaluate_gold_standard.py --pedal-ref inwindow \
        --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v4.json
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
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
                elif child.tag == "note" and divisions:
                    is_chord = child.find("chord") is not None
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
                    if not is_chord:
                        cursor += int(child.findtext("duration") or 0) / divisions
    return out


def parse_pedals(xml_path: Path) -> list[tuple[str, float]]:
    root = ET.parse(str(xml_path)).getroot()
    out = []
    for part in root.findall("part"):
        divisions = None
        cursor = 0.0
        bar_ql = 4.0
        for measure in part.findall("measure"):
            ts = measure.find("attributes/time")
            if ts is not None:
                beats = ts.findtext("beats")
                beat_type = ts.findtext("beat-type")
                if beats and beat_type:
                    bar_ql = 4.0 * int(beats) / int(beat_type)
            measure_num = int(measure.get("number") or 1)
            measure_start = (measure_num - 1) * bar_ql
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


def match_gold_dur(gold: list[dict], notes: list[dict]) -> tuple[int, list[float]]:
    """Greedy pitch+onset match (onset tol ONSET_TOL); returns (matched, |dur-gold| diffs)."""
    matched = 0
    diffs: list[float] = []
    for g in gold:
        for n in notes:
            if (n["hand"] == g["hand"] and n["pitch"] == g["pitch"]
                    and abs(n["onset"] - g["onset"]) <= ONSET_TOL):
                matched += 1
                diffs.append(abs(n["dur"] - g["notation"]))
                break
    return matched, diffs


def match_events(ref: list[float], out: list[float]) -> tuple[int, int, int]:
    """Greedy 1:1 matching with PEDAL_TOL. Returns (tp, fn, fp)."""
    used: set[int] = set()
    tp = 0
    for o in out:
        for i, x in enumerate(ref):
            if i not in used and abs(x - o) <= PEDAL_TOL:
                used.add(i)
                tp += 1
                break
    return tp, len(ref) - len(used), len(out) - tp


def _f1(tp: int, fn: int, fp: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return (2 * p * r / (p + r) if p + r else 0.0), p, r


def _visible(pos: float, seg_start: float, seg_end: float) -> bool:
    return seg_start - 1e-9 <= pos <= seg_end + 1e-9


def parse_segment(sid: str) -> dict:
    """Parse a segment once: gold rows, candidates, intervals, and all p4 pipes. Cheap to score repeatedly."""
    sd = BASE / sid
    meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
    start_ql = float(meta["start_ql"])
    end_ql = float(meta["end_ql"])
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
                ivs.append((float(r["start_ql"]), float(r["end_ql"]),
                            float(r["clipped_start_ql"]), float(r["clipped_end_ql"])))
    pipes = sorted({p.stem for p in sd.glob("p4_*.musicxml")})
    notes_by_pipe = {pipe: parse_notes(sd / f"{pipe}.musicxml") for pipe in pipes}
    pedals_by_pipe = {pipe: parse_pedals(sd / f"{pipe}.musicxml") for pipe in pipes}
    return {"sid": sid, "start_ql": start_ql, "end_ql": end_ql,
            "rows": rows, "gold": gold, "feas": feas, "ivs": ivs,
            "pipes": pipes, "notes_by_pipe": notes_by_pipe, "pedals_by_pipe": pedals_by_pipe}


def _ref_events(parsed: dict, pedal_ref: str) -> tuple[list[float], list[float]]:
    start_ql, end_ql = parsed["start_ql"], parsed["end_ql"]
    ivs = parsed["ivs"]
    if pedal_ref == "unclipped":
        starts = sorted({s for s, e, cs, ce in ivs})
        stops = sorted({e for s, e, cs, ce in ivs})
    elif pedal_ref == "inwindow":
        starts = sorted({s for s, e, cs, ce in ivs if _visible(s, start_ql, end_ql)})
        stops = sorted({e for s, e, cs, ce in ivs if _visible(e, start_ql, end_ql)})
    elif pedal_ref == "visible":
        # 只评系统在窗口内"可见且应标记"的事件：
        #   start = 窗口内踩下的事件 + 跨窗区间（窗口前已踩下）在窗口起点的 start；
        #   stop  = 仅窗口内释放的事件（窗口后释放不可见，不给伪参考）。
        starts = {s for s, e, cs, ce in ivs if _visible(s, start_ql, end_ql)}
        starts |= {start_ql for s, e, cs, ce in ivs
                   if s < start_ql - 1e-9 and e > start_ql + 1e-9}
        stops = {e for s, e, cs, ce in ivs if _visible(e, start_ql, end_ql)}
        starts, stops = sorted(starts), sorted(stops)
    else:  # clipped
        starts = sorted({cs for s, e, cs, ce in ivs})
        stops = sorted({ce for s, e, cs, ce in ivs})
    return starts, stops


def score_segment(parsed: dict, pedal_ref: str) -> dict:
    sid, start_ql = parsed["sid"], parsed["start_ql"]
    rows, gold = parsed["rows"], parsed["gold"]
    perf_starts, perf_stops = _ref_events(parsed, pedal_ref)
    res = {"segment": sid, "n_events": len(rows), "gold_notation": len(gold),
           "candidate_feasible": parsed["feas"]}
    for pipe in parsed["pipes"]:
        notes = parsed["notes_by_pipe"][pipe]
        matched, diffs = match_gold_dur(gold, notes)
        n_gold = len(gold)
        d005 = sum(1 for d in diffs if d <= 0.05)
        d025 = sum(1 for d in diffs if d <= 0.25)
        d100 = sum(1 for d in diffs if d <= 1.0)
        med_err = statistics.median(diffs) if diffs else None
        ped = parsed["pedals_by_pipe"][pipe]
        starts = [o + start_ql for t, o in ped if t in ("start", "change")]
        stops = [o + start_ql for t, o in ped if t in ("stop", "change")]
        tp_s, fn_s, fp_s = match_events(perf_starts, starts)
        tp_p, fn_p, fp_p = match_events(perf_stops, stops)
        f1_s, pr_s, rc_s = _f1(tp_s, fn_s, fp_s)
        f1_p, pr_p, rc_p = _f1(tp_p, fn_p, fp_p)
        res[pipe] = {"notes": len(notes), "gold_matched": matched,
                     "duration_ok": d005,
                     "duration_rate": round(d005 / n_gold, 4) if n_gold else 0.0,
                     "duration_rate_025": round(d025 / n_gold, 4) if n_gold else 0.0,
                     "duration_rate_100": round(d100 / n_gold, 4) if n_gold else 0.0,
                     "duration_med_abs_err_ql": round(med_err, 4) if med_err is not None else None,
                     "pedal_start_f1": round(f1_s, 4), "pedal_stop_f1": round(f1_p, 4),
                     "pedal_events": len(ped),
                     "pedal_start_tp": tp_s, "pedal_start_fn": fn_s, "pedal_start_fp": fp_s,
                     "pedal_stop_tp": tp_p, "pedal_stop_fn": fn_p, "pedal_stop_fp": fp_p}
    res["mismatch_acoustic_yes_score_none"] = sum(
        1 for r in rows if r["acoustic_sustain"] == "yes" and r["published_score_pedal"] == "none")
    res["mismatch_perf_change_score_none"] = sum(
        1 for r in rows if r["performance_pedal_action"] == "change" and r["published_score_pedal"] == "none")
    return res


def macro_f1(results: list[dict], pipe: str, field: str) -> float:
    return sum(r[pipe][field] for r in results) / len(results) if results else 0.0


def micro_f1(results: list[dict], pipe: str, kind: str) -> float:
    tp = sum(r[pipe][f"pedal_{kind}_tp"] for r in results)
    fn = sum(r[pipe][f"pedal_{kind}_fn"] for r in results)
    fp = sum(r[pipe][f"pedal_{kind}_fp"] for r in results)
    f1, _, _ = _f1(tp, fn, fp)
    return round(f1, 4)


def bootstrap_ci(results: list[dict], pipe: str, field: str,
                 n_iter: int, seed: int) -> tuple[float, float]:
    vals = [r[pipe][field] for r in results]
    if len(vals) < 2:
        return round(sum(vals), 4), round(sum(vals), 4)
    rng = random.Random(seed)
    means = []
    for _ in range(n_iter):
        sample = [vals[rng.randrange(len(vals))] for _ in range(len(vals))]
        means.append(sum(sample) / len(sample))
    means.sort()
    return round(means[int(0.025 * n_iter)], 4), round(means[int(0.975 * n_iter)], 4)


def _pipe_names(results: list[dict]) -> list[str]:
    return sorted({p for r in results for p in r
                   if p not in ("segment", "n_events", "gold_notation", "candidate_feasible")
                   and not p.startswith("mismatch_")})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",
                    default=str(BASE / "evaluation" / "gold_standard_eval_v4.json"))
    ap.add_argument("--segments", default=None)
    ap.add_argument("--pedal-ref", choices=("unclipped", "inwindow", "visible", "clipped"),
                    default="inwindow",
                    help="pedal reference protocol (default: inwindow)")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    if args.segments:
        lo, _, hi = args.segments.partition("-")
        lo, hi = int(lo), int(hi or lo)
        bl = [b for b in bl if lo <= b["index"] <= hi]

    parsed = [parse_segment(b["segment_id"]) for b in bl]
    results = [score_segment(p, args.pedal_ref) for p in parsed]
    pipes = _pipe_names(results)

    # per-pipe summary for the selected protocol
    summary = {"n_segments": len(results),
               "n_events": sum(r["n_events"] for r in results),
               "candidate_feasible": round(
                   sum(r["candidate_feasible"] for r in results) / sum(r["n_events"] for r in results), 4),
               "pedal_ref": args.pedal_ref,
               "pedal_tol_ql": PEDAL_TOL,
               "pipes": {}}
    for pipe in pipes:
        summary["pipes"][pipe] = {
            "duration_rate": round(sum(r[pipe]["duration_rate"] for r in results) / len(results), 4),
            "duration_rate_025": round(sum(r[pipe]["duration_rate_025"] for r in results) / len(results), 4),
            "duration_rate_100": round(sum(r[pipe]["duration_rate_100"] for r in results) / len(results), 4),
            "duration_med_abs_err_ql": round(
                statistics.median([r[pipe]["duration_med_abs_err_ql"]
                                   for r in results if r[pipe]["duration_med_abs_err_ql"] is not None]), 4),
            "pedal_start_macro_f1": round(macro_f1(results, pipe, "pedal_start_f1"), 4),
            "pedal_start_micro_f1": micro_f1(results, pipe, "start"),
            "pedal_start_ci95": list(bootstrap_ci(results, pipe, "pedal_start_f1",
                                                  args.bootstrap, args.seed)),
            "pedal_stop_macro_f1": round(macro_f1(results, pipe, "pedal_stop_f1"), 4),
            "pedal_stop_micro_f1": micro_f1(results, pipe, "stop"),
            "pedal_stop_ci95": list(bootstrap_ci(results, pipe, "pedal_stop_f1",
                                                 args.bootstrap, args.seed)),
            "pedal_events": sum(r[pipe]["pedal_events"] for r in results),
        }

    # protocol sensitivity (macro + micro for every protocol, every pipe)
    sensitivity = {}
    for ref_mode in ("unclipped", "inwindow", "visible", "clipped"):
        res2 = [score_segment(p, ref_mode) for p in parsed]
        sensitivity[ref_mode] = {}
        for pipe in pipes:
            sensitivity[ref_mode][pipe] = {
                "start_macro": round(macro_f1(res2, pipe, "pedal_start_f1"), 4),
                "start_micro": micro_f1(res2, pipe, "start"),
                "stop_macro": round(macro_f1(res2, pipe, "pedal_stop_f1"), 4),
                "stop_micro": micro_f1(res2, pipe, "stop"),
            }

    out = {"n_segments": len(results), "pedal_ref": args.pedal_ref,
           "segments": results, "summary": summary,
           "protocol_sensitivity": sensitivity}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- MD-style summary ----
    n = summary["n_events"]
    print(f"# 踏板金标准评测 v4（pedal_ref={args.pedal_ref}）segments={len(results)} events={n} "
          f"candidate_feasible={summary['candidate_feasible']:.1%}")
    print()
    print("## 时值指标（宏平均，容差 @0.05/0.25/1.0 QL + 中位|误差|）")
    print(f"{'管线':<12} {'@0.05':>7} {'@0.25':>7} {'@1.0':>7} {'med|err|':>8}")
    for pipe in pipes:
        s = summary["pipes"][pipe]
        print(f"{pipe:<12} {s['duration_rate']:>7.3f} {s['duration_rate_025']:>7.3f} "
              f"{s['duration_rate_100']:>7.3f} {s['duration_med_abs_err_ql']:>8.3f}")
    print()
    print("## 踏板 F1（推荐口径：inwindow，容差 0.25 QL）")
    print(f"{'管线':<12} {'start宏':>7} {'start微':>7} {'start CI95':>14} {'stop宏':>7} {'stop微':>7} {'stop CI95':>14}")
    for pipe in pipes:
        s = summary["pipes"][pipe]
        print(f"{pipe:<12} {s['pedal_start_macro_f1']:>7.3f} {s['pedal_start_micro_f1']:>7.3f} "
              f"[{s['pedal_start_ci95'][0]:.3f},{s['pedal_start_ci95'][1]:.3f}] "
              f"{s['pedal_stop_macro_f1']:>7.3f} {s['pedal_stop_micro_f1']:>7.3f} "
              f"[{s['pedal_stop_ci95'][0]:.3f},{s['pedal_stop_ci95'][1]:.3f}]")
    print()
    print("## 口径敏感性（宏/微平均，p4_exact）")
    for ref_mode, d in sensitivity.items():
        ex = d.get("p4_exact", {})
        print(f"  {ref_mode:<10} start {ex.get('start_macro')}/{ex.get('start_micro')}  "
              f"stop {ex.get('stop_macro')}/{ex.get('stop_micro')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
