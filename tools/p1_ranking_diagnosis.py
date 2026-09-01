#!/usr/bin/env python3
"""P1 ranking/DP layer error-pattern diagnosis.

For each gold event (notation_decision present), compare:
  reference (notation_decision) / oracle (nearest candidate in candidate_durations)
  / rule actual (matched note duration in the p4_rule MusicXML),
and classify:
  gen_gap         candidate set has nothing within 0.25 of reference (generation gap)
  ok              rule output within 0.25 of reference
  ranking_error   candidate reachable (oracle can fix) but rule chose wrong
  no_output_match no note matched in output (pitch loss)

ranking_error cases are bucketed by reference side (key/acoustic), rule choice
side, review_class, pedal-extension evidence, chord membership, candidate count,
plus typical case listing.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_gold_standard import BASE, ONSET_TOL, parse_notes

NL = chr(10)


def side_of(value: float, key: float, acoustic: float) -> str:
    kg = abs(value - key)
    ag = abs(value - acoustic)
    if kg <= 0.125:
        return "near_key"
    if ag <= 0.125:
        return "near_acoustic"
    if min(key, acoustic) < value < max(key, acoustic):
        return "between"
    return "beyond"


def find_output_dur(g: dict, notes: list[dict]):
    best = None
    best_d = ONSET_TOL + 1.0
    for n in notes:
        if n["hand"] == g["hand"] and n["pitch"] == g["pitch"]:
            d = abs(n["onset"] - g["onset"])
            if d <= ONSET_TOL and d < best_d:
                best_d = d
                best = n["dur"]
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "evaluation" / "p1_ranking_diagnosis.json"))
    ap.add_argument("--pipe", default="p4_rule")
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))

    counts = Counter()
    err_side = Counter()
    err_class = Counter()
    err_pedal = Counter()
    err_chord = Counter()
    err_ncand = Counter()
    err_ref_in = Counter()
    cases = []
    total = 0

    for b in bl:
        sid = b["segment_id"]
        sd = BASE / sid
        meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
        start_ql = float(meta["start_ql"])
        notes = parse_notes(sd / (args.pipe + ".musicxml"))
        with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        chord_counts = Counter()
        for r in rows:
            if r["notation_decision"]:
                chord_counts[(r["hand"], round(float(r["onset_ql"]) - start_ql, 9))] += 1

        for r in rows:
            if not r["notation_decision"]:
                continue
            total += 1
            ref = float(r["notation_decision"])
            key = float(r["key_duration_ql"])
            acoustic = float(r["acoustic_duration_ql"])
            cands = {float(x) for x in r["candidate_durations"].split(";") if x.strip()}
            g = {"hand": r["hand"], "pitch": int(r["pitch"]),
                 "onset": float(r["onset_ql"]) - start_ql}
            rule_dur = find_output_dur(g, notes)
            cls = r["review_class"] or "none"

            if rule_dur is None:
                counts["no_output_match"] += 1
                continue
            near = any(abs(c - ref) <= 0.25 for c in cands)
            correct = abs(rule_dur - ref) <= 0.25
            if not near:
                counts["gen_gap"] += 1
                continue
            if correct:
                counts["ok"] += 1
                continue
            counts["ranking_error"] += 1
            ref_side = side_of(ref, key, acoustic)
            rule_side = side_of(rule_dur, key, acoustic)
            err_side[(ref_side, rule_side)] += 1
            err_class[cls] += 1
            pedal_ext = acoustic - key
            err_pedal["has_extension" if pedal_ext > 0.15 else "no_extension"] += 1
            is_chord = chord_counts[(g["hand"], round(g["onset"], 9))] > 1
            err_chord["chord" if is_chord else "solo"] += 1
            n_c = len(cands)
            err_ncand["1-2" if n_c <= 2 else ("3-4" if n_c <= 4 else "5+")] += 1
            ref_in = any(abs(c - ref) <= 1e-9 for c in cands)
            err_ref_in["ref_exact" if ref_in else "ref_near_only"] += 1
            if len(cases) < 40:
                cases.append({
                    "segment": sid, "event_id": r["event_id"], "hand": r["hand"],
                    "pitch": r["pitch"], "onset": round(g["onset"], 4),
                    "ref": ref, "key": key, "acoustic": round(acoustic, 4),
                    "rule_dur": rule_dur, "review_class": cls,
                    "ref_side": ref_side, "rule_side": rule_side,
                    "cands": sorted(cands)[:8], "n_candidates": n_c,
                    "candidate_sources_raw": (r.get("candidate_sources") or "")[:150],
                })

    summary = {
        "total_gold": total,
        "counts": dict(counts),
        "counts_ratio": {k: round(v / total, 4) for k, v in counts.items()},
        "ranking_error_by_side": {a + "|" + b: v for (a, b), v in sorted(err_side.items())},
        "ranking_error_by_class": dict(err_class),
        "ranking_error_by_pedal": dict(err_pedal),
        "ranking_error_by_chord": dict(err_chord),
        "ranking_error_by_ncand": dict(err_ncand),
        "ranking_error_ref_in": dict(err_ref_in),
        "n_cases": len(cases),
    }
    out = {"summary": summary, "cases": cases}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# P1 排序/DP 层错误模式诊断（pipe=" + args.pipe + "）", "",
             "- gold 事件（有 notation_decision）: %d" % total, "",
             "## 1. 事件分类", "", "| bucket | n | ratio |", "|---|---|---|"]
    for k in ("ok", "ranking_error", "gen_gap", "no_output_match"):
        lines.append("| %s | %d | %.4f |" % (k, counts[k], counts[k] / total if total else 0))
    lines += ["", "## 2. ranking_error：ref_side x rule_side", "",
              "| ref | rule near_key | rule near_aco | rule between | rule beyond |",
              "|---|---|---|---|---|"]
    for rs in ("near_key", "near_acoustic", "between", "beyond"):
        cells = [str(err_side.get((rs, cs), 0))
                 for cs in ("near_key", "near_acoustic", "between", "beyond")]
        lines.append("| " + rs + " | " + " | ".join(cells) + " |")
    lines += ["", "## 3. ranking_error 按 review_class", ""]
    for k, v in sorted(err_class.items()):
        lines.append("- %s: %d" % (k, v))
    lines += ["", "## 4. ranking_error 其他分桶", "",
              "- 延音证据: " + str(dict(err_pedal)),
              "- chord: " + str(dict(err_chord)),
              "- 候选数: " + str(dict(err_ncand)),
              "- 参考时值在候选集: " + str(dict(err_ref_in)),
              "", "## 5. 典型案例（前 %d）" % len(cases), ""]
    for c in cases:
        lines.append("- %s %s %s p=%s o=%.3f ref=%s key=%s aco=%s rule=%s cls=%s %s|%s nc=%d src=%s" % (
            c["segment"], c["event_id"], c["hand"], c["pitch"], c["onset"],
            c["ref"], c["key"], c["acoustic"], c["rule_dur"], c["review_class"],
            c["ref_side"], c["rule_side"], c["n_candidates"], c["candidate_sources_raw"]))
    md_path = Path(args.out).with_suffix(".md")
    md_path.write_text(NL.join(lines) + NL, encoding="utf-8")
    print("written: " + str(args.out))
    print("written: " + str(md_path))
    print("counts:", dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
