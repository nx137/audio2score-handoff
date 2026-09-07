#!/usr/bin/env python3
"""Phase 2A 选窗扫描器 —— 约束已编码（裁定 #P2A-1 / #P2A-2 / #P2A-3）。

角色分工（用户拍板, 见 trial8_phase2A_build_exec.md）:
- 主控: 本脚本全部逻辑、约束、段配置（下方 SEGMENTS / 硬约束）;
- 本地 AI: 仅运行本脚本并把输出贴回主控, 不做任何自行裁决。

坐标系（GS 既定 uniform 近似, 与 Segment 一致）:
- 窗口/小节统一用 0-based measure 索引 × bar_ql（uniform QL）;
- 谱面 <pedal> mark 定位到其所在 measure 起点 QL = measure_index * bar_ql;
- 空隙 = 对齐 CSV reference_onset_ql（score 坐标）排序后相邻 gap > 20 QL 的区间。

硬约束（已裁定, 勿改）:
1) 窗口内完整谱面 pedal 对（配对 start->stop/change）:
   Miroirs/4 >= 3 (#P2A-1); 其余四段 >= 8;
2) 空隙规避: Miroirs/4 与 Barcarolle 窗口不得与空隙区间重叠;
   Barcarolle 附加 end_ql < 600（曲尾空隙 @635.7-675.2, exec §2）;
3) 窗口边缘（两档）:
   - strict (#P2A-2): Ballades/3, op32/10, Miroirs/4 —— 窗口首尾各 >=2 小节内
     不得含任何谱面 pedal mark;
   - relaxed (#P2A-3, 用户拍板豁免): S145/2, Barcarolle —— 窗口边界不截断任何
     CC64 区间（无 cross_start / cross_end）。
4) 事件量 ~100-300 为软目标（仅评分, 不硬过滤）。

用法:  python tools/phase2a_window_scan.py [--out outputs/pedal_expansion/window_scan_phase2A.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# 同目录 import（build_pedal_gold_standard 会自行挂载 audio2score/scripts）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pedal_gold_standard import ROOT, analyze_performance  # noqa: E402

EPS = 1e-7
GAP_QL = 20.0          # 空隙阈值（对齐行 reference_onset_ql 相邻差）
WINDOW_LENS = (8, 12, 16, 20, 24, 28, 32, 36, 40)   # 候选窗口长度（小节）
TOP_N = 20             # 每段输出候选数


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def scan_score_pedal_marks(xml_path: Path) -> tuple[list, dict]:
    """返回 (marks, info): marks = [(measure_index0, kind)], kind in start/stop/change;
    info = {first_measure_no, measure_numbers}。measure_index0 按谱面 number 从 first 起算。"""
    root = ET.parse(xml_path).getroot()
    marks: list[tuple[int, str]] = []
    first_no = None
    for part in root:
        if localname(part.tag) != "part":
            continue
        for measure in part:
            if localname(measure.tag) != "measure":
                continue
            try:
                mno = int(measure.get("number", "0"))
            except ValueError:
                continue
            if first_no is None:
                first_no = mno
            for direction in measure:
                if localname(direction.tag) != "direction":
                    continue
                for dt in direction:
                    if localname(dt.tag) != "direction-type":
                        continue
                    for el in dt:
                        if localname(el.tag) != "pedal":
                            continue
                        ptype = el.get("type", "?")
                        if ptype in ("start", "stop", "change"):
                            marks.append((mno - (first_no or 1), ptype))
    marks.sort()
    return marks, {"first_measure_no": first_no}


def pair_score_marks(marks: list[tuple[int, str]]) -> list[tuple[int, int]]:
    """谱面 pedal 标记配对: start/change 开启, stop/change 关闭。
    返回 [(start_idx, end_idx)] 0-based measure 索引。change 拆为闭+开。"""
    pairs: list[tuple[int, int]] = []
    open_idx: int | None = None
    for idx, kind in marks:
        if kind == "stop":
            if open_idx is not None:
                pairs.append((open_idx, idx))
                open_idx = None
        elif kind == "change":
            if open_idx is not None:
                pairs.append((open_idx, idx))
            open_idx = idx
        elif kind == "start":
            open_idx = idx
    # 谱面最后若以 start 悬空(谱面惯例停踏板记号缺失), 不入对
    return pairs


def load_alignment_gaps(align_csv: Path) -> list[tuple[float, float]]:
    """空隙区间(score 坐标 reference_onset_ql): 排序后相邻差 > GAP_QL 处切开。"""
    qls = []
    with align_csv.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                q = float(r["reference_onset_ql"])
            except (KeyError, ValueError):
                continue
            qls.append(q)
    qls.sort()
    gaps: list[tuple[float, float]] = []
    for a, b in zip(qls, qls[1:]):
        if b - a > GAP_QL:
            gaps.append((a, b))
    return gaps


def build_segment_config() -> list[dict]:
    # manifest 精确行 + 对齐 CSV（exec §2）; midi/xml 根 = ROOT/data/ASAP
    def row(composer, title, perf, midi_dir):
        return {
            "split": "train", "piece_key": composer + "\x1f" + title,
            "composer": composer, "title": title,
            "midi_performance": midi_dir + "/" + perf + ".mid",
            "midi_score": midi_dir + "/midi_score.mid",
            "xml_score": midi_dir + "/xml_score.musicxml",
        }

    return [
        {"key": "Ballades_3_Ko11M", "perf": "Ko11M",
         "row": row("Chopin", "Ballades_3", "Ko11M", "Chopin/Ballades/3"),
         "align_csv": "data/alignments/Chopin__Ballades__3__Ko11M.csv",
         "min_score_pairs": 8, "edge": "strict", "gap_avoid": False},
        {"key": "Concert_Etude_S145_2_Lu03M", "perf": "Lu03M",
         "row": row("Liszt", "Concert_Etude_S145_2", "Lu03M", "Liszt/Concert_Etude_S145/2"),
         "align_csv": "data/alignments/Liszt__Concert_Etude_S145__2__Lu03M.csv",
         "min_score_pairs": 8, "edge": "relaxed", "gap_avoid": False},
        {"key": "Preludes_op_32_10_Floril03", "perf": "Floril03",
         "row": row("Rachmaninoff", "Preludes_op_32_10", "Floril03", "Rachmaninoff/Preludes_op_32/10"),
         "align_csv": "data/alignments/Rachmaninoff__Preludes_op_32__10__Floril03.csv",
         "min_score_pairs": 8, "edge": "strict", "gap_avoid": False},
        {"key": "Barcarolle_Rozanski07M", "perf": "Rozanski07M",
         "row": row("Chopin", "Barcarolle", "Rozanski07M", "Chopin/Barcarolle"),
         "align_csv": "data/alignments/Chopin__Barcarolle__Rozanski07M.csv",
         "min_score_pairs": 8, "edge": "relaxed", "gap_avoid": True,
         "end_ql_max": 600.0},
        {"key": "Miroirs_4_Alborada_del_gracioso_Chan02", "perf": "Chan02",
         "row": row("Ravel", "Miroirs_4_Alborada_del_gracioso", "Chan02",
                    "Ravel/Miroirs/4_Alborada_del_gracioso"),
         "align_csv": "data/alignments/Ravel__Miroirs__4_Alborada_del_gracioso__Chan02.csv",
         "min_score_pairs": 3, "edge": "strict", "gap_avoid": True},
    ]


def scan_one(cfg: dict) -> dict:
    r = cfg["row"]
    out: dict = {"key": cfg["key"], "error": None}

    midi_path = ROOT / "data" / "ASAP" / r["midi_performance"]
    xml_path = ROOT / "data" / "ASAP" / r["xml_score"]
    align_path = ROOT / cfg["align_csv"]
    for p, tag in ((midi_path, "midi"), (xml_path, "xml"), (align_path, "align")):
        if not p.exists():
            out["error"] = "missing %s: %s" % (tag, p)
            return out

    try:
        records, pedals, time_sig, bar_ql, measure_count, tempo = analyze_performance(r)
    except Exception as exc:  # noqa: BLE001
        out["error"] = "analyze_performance failed: %r" % exc
        return out

    marks, minfo = scan_score_pedal_marks(xml_path)
    pairs = pair_score_marks(marks)
    gaps = load_alignment_gaps(align_path)

    out.update({
        "time_sig": list(time_sig), "bar_ql": bar_ql, "tempo_bpm": tempo,
        "measure_count": measure_count,
        "events_total": len(records), "cc64_pairs_total": len(pedals),
        "score_pedal_marks": dict(Counter(k for _, k in marks)),
        "score_pedal_pairs_total": len(pairs),
        "first_measure_no": minfo["first_measure_no"],
        "gap_intervals_score_ql": [[round(a, 2), round(b, 2)] for a, b in gaps],
        "constraints": {
            "min_score_pairs": cfg["min_score_pairs"],
            "edge_mode": cfg["edge"],
            "gap_avoid": cfg.get("gap_avoid", False),
            "end_ql_max": cfg.get("end_ql_max"),
        },
    })

    def mark_ql(idx0: int) -> float:
        return idx0 * bar_ql

    feasible = []
    rejected = Counter()

    for length in WINDOW_LENS:
        if length > measure_count:
            continue
        for start in range(0, measure_count - length + 1):
            end = start + length - 1
            w0, w1 = start * bar_ql, (end + 1) * bar_ql
            cand = {"start_measure": start, "end_measure": end,
                    "start_ql": round(w0, 3), "end_ql": round(w1, 3)}
            # --- 谱面完整对 ---
            inside = [p for p in pairs if p[0] >= start and p[1] <= end]
            n_score_pairs = len(inside)
            # --- CC64 ---
            cc_inside = sum(1 for s, e in pedals if s >= w0 - EPS and e <= w1 + EPS)
            cc_cross = sum(1 for s, e in pedals
                           if (s < w0 - EPS < e) or (s < w1 - EPS < e))
            # --- 事件量 ---
            n_events = sum(1 for rec in records if w0 - EPS <= rec.onset_ql < w1)
            # --- 空隙 ---
            gap_overlap = any(not (w1 <= ga + EPS or gb <= w0 + EPS) for ga, gb in gaps)
            if cfg.get("end_ql_max") is not None and w1 >= cfg["end_ql_max"]:
                gap_overlap = True  # 曲尾空隙余量约束并入 gap_overlap
            # --- 边缘 ---
            if cfg["edge"] == "strict":
                edge_ok = not any(
                    (start - 2 <= idx <= start - 1) or (end + 1 <= idx <= end + 2)
                    for idx, _ in marks)
            else:  # relaxed: 边界不截断 CC64
                edge_ok = cc_cross == 0
            cand.update({
                "n_score_pairs": n_score_pairs, "n_cc64_inside": cc_inside,
                "cc64_cross": cc_cross, "n_events": n_events,
                "gap_overlap": gap_overlap, "edge_ok": edge_ok,
            })
            if n_score_pairs < cfg["min_score_pairs"]:
                rejected["min_score_pairs"] += 1
                continue
            if gap_overlap:
                rejected["gap"] += 1
                continue
            if not edge_ok:
                rejected["edge"] += 1
                continue
            feasible.append(cand)

    # 评分: pedal 对为主, 事件量贴近 100-300 的区间为佳, 边界截断越少越好
    for cand in feasible:
        ev = cand["n_events"]
        ev_pen = 0.0
        if ev < 100:
            ev_pen = (100 - ev) / 100.0 * 10
        elif ev > 300:
            ev_pen = (ev - 300) / 100.0 * 10
        cand["score"] = round(
            cand["n_score_pairs"] * 100.0
            + min(cand["n_cc64_inside"], 60) * 2.0
            - ev_pen - cand["cc64_cross"] * 5.0, 2)

    feasible.sort(key=lambda c: (-c["score"], c["start_measure"]))
    out["n_feasible"] = len(feasible)
    out["top_candidates"] = feasible[:TOP_N]

    if not feasible:
        diag = {
            "rejected_by": {k: v for k, v in rejected.items()},
            "note": ("rejected_by 计每个被拒窗口首次命中该约束的次数"
                     "（窗口可能命中多个, 先记先验顺序）"),
        }
        # 最近似窗口: 只差边缘 或 只差 1 对（宽松评估, 供主控裁决降级）
        near = []
        for length in (12, 16, 20, 24, 28):
            if length > measure_count:
                continue
            for start in range(0, measure_count - length + 1):
                end = start + length - 1
                w0, w1 = start * bar_ql, (end + 1) * bar_ql
                inside = [p for p in pairs if p[0] >= start and p[1] <= end]
                cc_cross = sum(1 for s, e in pedals
                               if (s < w0 - EPS < e) or (s < w1 - EPS < e))
                gap_ov = any(not (w1 <= ga + EPS or gb <= w0 + EPS) for ga, gb in gaps)
                if cfg.get("end_ql_max") is not None and w1 >= cfg["end_ql_max"]:
                    gap_ov = True
                n_score_pairs = len(inside)
                if gap_ov:
                    continue
                near.append({
                    "start_measure": start, "end_measure": end,
                    "n_score_pairs": n_score_pairs,
                    "minus_pairs": cfg["min_score_pairs"] - n_score_pairs,
                    "cc64_cross": cc_cross,
                    "n_events": sum(1 for rec in records if w0 - EPS <= rec.onset_ql < w1),
                })
        near.sort(key=lambda c: (max(0, c["minus_pairs"]), c["cc64_cross"]))
        diag["near_miss_top"] = near[:10]
        out["diagnosis"] = diag
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",
                    default=str(ROOT / "outputs" / "pedal_expansion" / "window_scan_phase2A.json"))
    args = ap.parse_args()

    results = []
    for cfg in build_segment_config():
        print("=" * 40, cfg["key"], "=" * 40, flush=True)
        res = scan_one(cfg)
        results.append(res)
        if res.get("error"):
            print("ERROR:", res["error"])
            continue
        print("time_sig %s | bar_ql %s | tempo %.1f | measures %d | events %d"
              % (res["time_sig"], res["bar_ql"], res["tempo_bpm"],
                 res["measure_count"], res["events_total"]))
        print("score pedal marks %s | pairs %d | cc64 pairs %d | gaps %s"
              % (res["score_pedal_marks"], res["score_pedal_pairs_total"],
                 res["cc64_pairs_total"], res["gap_intervals_score_ql"]))
        print("constraints %s" % res["constraints"])
        print("n_feasible = %d" % res["n_feasible"])
        for cand in res["top_candidates"][:8]:
            print("  m%4d-%4d  ql %8.2f-%8.2f  score_pairs %3d  cc64_inside %3d"
                  "  cross %d  events %4d  score %8.2f"
                  % (cand["start_measure"] + 1, cand["end_measure"] + 1,
                     cand["start_ql"], cand["end_ql"], cand["n_score_pairs"],
                     cand["n_cc64_inside"], cand["cc64_cross"],
                     cand["n_events"], cand["score"]))
        if "diagnosis" in res:
            d = res["diagnosis"]
            print("ZERO FEASIBLE -> rejected_by %s" % d["rejected_by"])
            for nm in d["near_miss_top"][:6]:
                print("  near miss m%4d-%4d  minus_pairs %d  cc64_cross %d  events %d"
                      % (nm["start_measure"] + 1, nm["end_measure"] + 1,
                         nm["minus_pairs"], nm["cc64_cross"], nm["n_events"]))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"generated_by": "tools/phase2a_window_scan.py",
                    "constraint_rulings": ["#P2A-1", "#P2A-2", "#P2A-3"],
                    "segments": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("\nwritten:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
