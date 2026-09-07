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
4) 事件量软目标 ~100-500（仅评分, 不硬过滤; 超 800 轻微惩罚）。

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
    mcount = 0
    for part in root:
        if localname(part.tag) != "part":
            continue
        for measure in part:
            if localname(measure.tag) != "measure":
                continue
            mcount += 1
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
    return marks, {"first_measure_no": first_no, "measures_count": mcount}


def pair_score_marks(marks: list[tuple[int, str]]) -> list[tuple[int, int]]:
    """谱面 pedal 标记配对: start/change 开启, stop/change 关闭(栈式: 最近未配 start 优先)。
    返回 [(start_idx, end_idx)] 0-based measure 索引。change 拆为闭+开。
    注: 同 measure 可出现多个记号(如 6/8 半小节踏板), 顺序配对会覆盖丢失——必须用栈。"""
    pairs: list[tuple[int, int]] = []
    opens: list[int] = []
    for idx, kind in marks:
        if kind == "start":
            opens.append(idx)
        elif kind == "change":
            if opens:
                pairs.append((opens.pop(), idx))
            opens.append(idx)
        elif kind == "stop":
            if opens:
                pairs.append((opens.pop(), idx))
    # 谱面末尾悬空的 start(无对应 stop, 如 Barcarolle 37 处) 不入对
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

SCORE_MARGIN_QL = 16.0  # 窗口映射 margin 档扩展量(与 rebuild_segment_reference 同口径)


def read_alignment_rows(align_csv: Path) -> list[tuple[float, float]]:
    """对齐行 [(perf_ql, score_ql)]，按 perf 排序（perf=onset_ql, score=reference_onset_ql）。"""
    rows = []
    with align_csv.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                rows.append((float(row["onset_ql"]), float(row["reference_onset_ql"])))
            except (KeyError, ValueError):
                continue
    return sorted(rows, key=lambda item: item[0])


def map_perf_to_score(rows, w0: float, w1: float) -> tuple[float, float, str] | None:
    """perf 窗口 [w0,w1] -> score QL 区间 [s0,s1]（三档 strict/margin/interp）。

    与 rebuild_segment_reference.map_score_window 同逻辑(GS coordinate_fix):
    perf 轴(演奏)与 score 轴(谱面)是两条不可直接互算的时间轴, 必须经 alignment。"""
    strict = [r for (_p, r) in rows if w0 - EPS <= _p <= w1 + EPS]
    if strict:
        return min(strict), max(strict), "strict"
    margin = [r for (_p, r) in rows
              if w0 - SCORE_MARGIN_QL - EPS <= _p <= w1 + SCORE_MARGIN_QL + EPS]
    if margin:
        return min(margin), max(margin), "margin"
    if not rows:
        return None

    def _ps(q):
        if q <= rows[0][0] + EPS:
            return rows[0][1]
        if q >= rows[-1][0] - EPS:
            return rows[-1][1]
        lo, hi = 0, len(rows) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if rows[mid][0] <= q:
                lo = mid
            else:
                hi = mid
        p1, r1 = rows[lo]
        p2, r2 = rows[hi]
        if p2 - p1 <= EPS:
            return r1
        return r1 + (q - p1) * (r2 - r1) / (p2 - p1)

    s0, s1 = _ps(w0), _ps(w1)
    if s1 <= s0 + EPS:
        return None
    return s0, s1, "interp"


def score_measure_starts_local(xml_path: Path) -> list[float]:
    """谱面每小节起点(score QL, 真实拍号累计)。localname 兼容命名空间; 取第一个 part。"""
    root = ET.parse(str(xml_path)).getroot()
    starts: list[float] = []
    ms = 0.0
    bar = 4.0
    for part in root:
        if localname(part.tag) != "part":
            continue
        for measure in part:
            if localname(measure.tag) != "measure":
                continue
            starts.append(ms)
            attrs = measure.find("attributes")
            if attrs is not None:
                beats = attrs.findtext("time/beats")
                bt = attrs.findtext("time/beat-type")
                if beats and bt:
                    bar = 4.0 * float(beats) / float(bt)
            ms += bar
        break
    return starts


def measure_index_range_local(starts: list[float], s0: float, s1: float) -> tuple[int, int]:
    """score QL [s0,s1] 覆盖的小节 0-based 索引 [first, last]（与 rebuild 同语义）。"""
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
    return first, max(last, first)


def scan_one(cfg: dict) -> dict:
    """坐标系（GS 双轨, 与 rebuild_segment_reference 一致）:
    - 窗口在 perf uniform 域枚举（GS Segment 语义, slice_midi 用）;
    - 谱面 pedal/空隙/边缘约束全部在 score 域判断: perf 窗口 -> alignment 映射
      -> score QL 区间 -> score measure 范围（map_perf_to_score 三档）。
    谱面(记谱/未展开反复)与 perf(演奏序)小节数不同(如 S145/2 168 vs 78),
    直接按 measure 号硬绑会系统失真, 必须经 alignment 映射。"""
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
    score_starts = score_measure_starts_local(xml_path)
    gaps = load_alignment_gaps(align_path)          # score 域空隙(reference_onset_ql)
    align_rows = read_alignment_rows(align_path)    # [(perf_ql, score_ql)]

    out.update({
        "time_sig": list(time_sig), "bar_ql": bar_ql, "tempo_bpm": tempo,
        "measure_count": measure_count,
        "events_total": len(records), "cc64_pairs_total": len(pedals),
        "score_pedal_marks": dict(Counter(k for _, k in marks)),
        "score_pedal_pairs_total": len(pairs),
        "first_measure_no": minfo["first_measure_no"],
        "score_measures": minfo["measures_count"],
        "score_total_ql": round(score_starts[-1] + 4.0, 2) if score_starts else None,
        "gap_intervals_score_ql": [[round(a, 2), round(b, 2)] for a, b in gaps],
        "constraints": {
            "min_score_pairs": cfg["min_score_pairs"],
            "edge_mode": cfg["edge"],
            "gap_avoid": cfg.get("gap_avoid", False),
            "end_ql_max": cfg.get("end_ql_max"),
        },
    })

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
            mapped = map_perf_to_score(align_rows, w0, w1)
            if mapped is None:
                rejected["unmapped"] += 1
                continue
            s0, s1, method = mapped
            if s1 <= s0 + EPS or s1 - s0 > (w1 - w0) * 6.0 + 40.0:
                rejected["unmapped"] += 1
                continue
            i0, i1 = measure_index_range_local(score_starts, s0, s1)
            cand.update({"score_ql0": round(s0, 2), "score_ql1": round(s1, 2),
                         "map_method": method, "score_m0": i0, "score_m1": i1})
            n_score_pairs = sum(1 for a, b in pairs if a >= i0 and b <= i1)
            gap_overlap = any(not (s1 <= ga + EPS or gb <= s0 + EPS) for ga, gb in gaps)
            if cfg.get("end_ql_max") is not None and s1 >= cfg["end_ql_max"]:
                gap_overlap = True
            cc_inside = sum(1 for s, e in pedals if s >= w0 - EPS and e <= w1 + EPS)
            cc_cross = sum(1 for s, e in pedals
                           if (s < w0 - EPS < e) or (s < w1 - EPS < e))
            n_events = sum(1 for rec in records if w0 - EPS <= rec.onset_ql < w1)
            if cfg["edge"] == "strict":
                edge_ok = not any(
                    (i0 - 2 <= idx <= i0 - 1) or (i1 + 1 <= idx <= i1 + 2)
                    for idx, _ in marks)
            else:  # relaxed: perf 边界不截断 CC64 (#P2A-3)
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

    for cand in feasible:
        ev = cand["n_events"]
        ev_pen = 0.0
        if ev < 100:
            ev_pen = (100 - ev) / 100.0 * 10
        elif ev > 800:
            ev_pen = (ev - 800) / 100.0 * 10
        cand["score"] = round(
            cand["n_score_pairs"] * 100.0
            + min(cand["n_cc64_inside"], 60) * 2.0
            - ev_pen - cand["cc64_cross"] * 5.0, 2)

    feasible.sort(key=lambda cc: (-cc["score"], cc["start_measure"]))
    out["n_feasible"] = len(feasible)
    out["top_candidates"] = feasible[:TOP_N]

    if not feasible:
        diag = {"rejected_by": {k: v for k, v in rejected.items()},
                "note": "rejected_by = 每窗口首次命中该约束次数(可能多命中, 先记先验序)"}
        near = []
        for length in (12, 16, 20, 24, 28):
            if length > measure_count:
                continue
            for start in range(0, measure_count - length + 1):
                end = start + length - 1
                w0, w1 = start * bar_ql, (end + 1) * bar_ql
                mapped = map_perf_to_score(align_rows, w0, w1)
                if mapped is None:
                    continue
                s0, s1, _m = mapped
                if s1 - s0 > (w1 - w0) * 6.0 + 40.0:
                    continue
                i0, i1 = measure_index_range_local(score_starts, s0, s1)
                if any(not (s1 <= ga + EPS or gb <= s0 + EPS) for ga, gb in gaps):
                    continue
                if cfg.get("end_ql_max") is not None and s1 >= cfg["end_ql_max"]:
                    continue
                np_ = sum(1 for a, b in pairs if a >= i0 and b <= i1)
                ccx = sum(1 for s, e in pedals
                          if (s < w0 - EPS < e) or (s < w1 - EPS < e))
                near.append({"start_measure": start, "end_measure": end,
                             "score_m0": i0, "score_m1": i1,
                             "n_score_pairs": np_,
                             "minus_pairs": cfg["min_score_pairs"] - np_,
                             "cc64_cross": ccx,
                             "n_events": sum(1 for rec in records if w0 - EPS <= rec.onset_ql < w1)})
        near.sort(key=lambda x: (max(0, x["minus_pairs"]), x["cc64_cross"]))
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
        if res.get("domain_warning"):
            print("DOMAIN WARN:", res["domain_warning"])
        print("constraints %s" % res["constraints"])
        print("n_feasible = %d" % res["n_feasible"])
        fn = res.get("first_measure_no", 1)
        for cand in res["top_candidates"][:8]:
            print("  m%4d-%4d (score no %4d-%4d)  ql %8.2f-%8.2f  score_pairs %3d  cc64_inside %3d"
                  "  cross %d  events %4d  score %8.2f"
                  % (cand["start_measure"] + 1, cand["end_measure"] + 1,
                     cand["score_m0"] + fn, cand["score_m1"] + fn,
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
