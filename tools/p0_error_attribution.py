#!/usr/bin/env python3
"""P0-2/P0-3/P0-4 归因工具：无匹配输出归因 + learned/rule 误差分解 + oracle 三层归因。

对正式金标准 40 片段：
  1) 无匹配输出归因（P0-2）：gold 事件（notation_decision 标注）在对应管线
     MusicXML 输出中找不到 (hand, pitch, onset±0.125) 匹配时，按原因分类：
       hand_mismatch : 输出存在同 pitch+onset 但不同 hand 的音符（LH/RH 错位）
       pitch_missing : 输出无同 hand 同 onset 的音符（转录/量化/生成丢失）
       onset_shift   : 其余（onset 偏差 > 容差，窗口/对齐偏移）
  2) learned vs rule 误差分解（P0-3）：按 review_class 统计 @0.25 时值一致率，
     暴露 learned 模型的错误模式（非训练，仅评估暴露问题）。
  3) oracle 三层归因（P0-4）：候选精确可达率 / oracle@0.25（可达∨有候选距参考
     ≤0.25）/ 实际@0.25，分解 生成层 / 排序DP层 / 结构层 三类误差责任。

用法：
    python tools/p0_error_attribution.py \\
        --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/p0_error_attribution.json
"""
from __future__ import annotations
import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_gold_standard import BASE, ONSET_TOL, parse_notes, match_gold_dur

PIPES = ("p4_rule", "p4_learned", "p4_fused", "p4_exact", "p4_no_pedal")


def load_gold(rows, start_ql):
    return [{"hand": r["hand"], "pitch": int(r["pitch"]),
             "onset": float(r["onset_ql"]) - start_ql,
             "notation": float(r["notation_decision"]),
             "review_class": (r["review_class"] or "none")}
            for r in rows if r["notation_decision"]]


def classify_unmatched(gold, notes):
    """gold 中未匹配事件的根因分类（基于输出音符集合）。"""
    reasons = Counter()
    for g in gold:
        ok = any(abs(n["onset"] - g["onset"]) <= ONSET_TOL
                 for n in notes if n["hand"] == g["hand"] and n["pitch"] == g["pitch"])
        if ok:
            continue
        other = "LH" if g["hand"] == "RH" else "RH"
        if any(abs(n["onset"] - g["onset"]) <= ONSET_TOL
               for n in notes if n["hand"] == other and n["pitch"] == g["pitch"]):
            reasons["hand_mismatch"] += 1
        elif any(abs(n["onset"] - g["onset"]) <= ONSET_TOL
                 for n in notes if n["hand"] == g["hand"]):
            reasons["pitch_missing"] += 1
        else:
            reasons["onset_shift"] += 1
    return reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "evaluation" / "p0_error_attribution.json"))
    args = ap.parse_args()

    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    segs = [b["segment_id"] for b in bl]

    results = []
    agg = defaultdict(Counter)                      # reason -> pipe -> n
    cls_diffs = defaultdict(lambda: defaultdict(list))  # review_class -> pipe -> [|diff|]
    total_gold = 0

    for sid in segs:
        sd = BASE / sid
        meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
        start_ql = float(meta["start_ql"])
        with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        gold = load_gold(rows, start_ql)
        total_gold += len(gold)
        seg_row = {"segment": sid, "n_gold": len(gold)}
        for pipe in sorted({p.stem for p in sd.glob("p4_*.musicxml")}):
            notes = parse_notes(sd / f"{pipe}.musicxml")
            matched, _diffs = match_gold_dur(gold, notes)
            reasons = classify_unmatched(gold, notes)
            # 逐 gold 事件：找最近输出音符的 |时值差|（含全部事件，不依赖贪心顺序）
            for g in gold:
                best = min((abs(n["dur"] - g["notation"]) for n in notes
                            if n["hand"] == g["hand"] and n["pitch"] == g["pitch"]
                            and abs(n["onset"] - g["onset"]) <= ONSET_TOL), default=None)
                if best is not None:
                    cls_diffs[g["review_class"]][pipe].append(best)
            seg_row[pipe] = {"matched": matched, "unmatched": len(gold) - matched,
                             "reasons": dict(reasons)}
            for reason, n in reasons.items():
                agg[reason][pipe] += n
        results.append(seg_row)

    # ---- oracle 三层归因（候选列口径，与评测 feas 一致） ----
    oracle = {"reachable": 0, "oracle_025": 0, "n": 0}
    unreachable_by_class = Counter()
    for b in bl:
        sd = BASE / b["segment_id"]
        meta = json.loads((sd / "segment_metadata.json").read_text(encoding="utf-8"))
        start_ql = float(meta["start_ql"])
        with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if not r["notation_decision"]:
                    continue
                d = float(r["notation_decision"])
                cands = {float(x) for x in r["candidate_durations"].split(";") if x.strip()}
                reachable = any(abs(c - d) <= 1e-9 for c in cands)
                near = any(abs(c - d) <= 0.25 for c in cands)
                oracle["n"] += 1
                if reachable:
                    oracle["reachable"] += 1
                if reachable or near:
                    oracle["oracle_025"] += 1
                if not (reachable or near):
                    unreachable_by_class[r["review_class"] or "none"] += 1

    # ---- 按 review_class 的 @0.25 时值一致率 ----
    cls_table = {}
    for cls, pipes in sorted(cls_diffs.items()):
        cls_table[cls] = {
            pipe: (round(sum(1 for d in ds if d <= 0.25) / len(ds), 4) if ds else None)
            for pipe, ds in sorted(pipes.items())
        }

    summary = {
        "n_segments": len(segs),
        "n_gold": total_gold,
        "unmatched_by_reason": {reason: dict(pipes) for reason, pipes in agg.items()},
        "oracle": {k: round(v / oracle["n"], 4) for k, v in oracle.items() if k != "n"},
        "oracle_n": oracle["n"],
        "unreachable_by_class": dict(unreachable_by_class),
        "class_duration_rate_025": cls_table,
    }
    out = {"segments": results, "summary": summary}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- MD 摘要 ----
    pipes_all = sorted({p for d in agg.values() for p in d})
    lines = ["# P0 误差归因（unmatched / learned / oracle）", "",
             f"- 片段 {len(segs)}，gold 事件 {total_gold}", "",
             "## 1. 无匹配输出归因（按原因 × 管线）", "",
             "| 原因 | " + " | ".join(pipes_all) + " |",
             "|" + "---|" * (len(pipes_all) + 1)]
    for reason in ("hand_mismatch", "pitch_missing", "onset_shift"):
        row = agg.get(reason, Counter())
        lines.append(f"| {reason} | " + " | ".join(str(row.get(p, 0)) for p in pipes_all) + " |")
    lines += ["", "## 2. oracle 三层归因", "",
              f"- 精确可达率: {summary['oracle'].get('reachable', 0)}",
              f"- oracle@0.25: {summary['oracle'].get('oracle_025', 0)}",
              f"- 不可达缺口按 review_class: {dict(unreachable_by_class)}", "",
              "## 3. 各 review_class 的 @0.25 时值一致率", "",
              "| review_class | " + " | ".join(pipes_all) + " |",
              "|" + "---|" * (len(pipes_all) + 1)]
    for cls, row in sorted(cls_table.items()):
        lines.append(f"| {cls} | " + " | ".join(
            ("-" if row.get(p) is None else f"{row[p]:.3f}") for p in pipes_all) + " |")
    md_path = Path(args.out).with_suffix(".md")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {args.out}\nwritten: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
