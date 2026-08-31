#!/usr/bin/env python3
"""P1.5：候选生成增强的片段级重生成（幂等、可续传）。

对指定片段：
1. 更新 events.csv 的 candidate_durations/candidate_sources（保留全部人工标注列）：
   候选 = 原候选 ∪ {key_duration x {2,3,4,1.5,0.5}} ∪ {0.25,0.5,0.375,1/6,1/3,1.0}，
   并按 next_voice_gap_ql 做同 voice 不重叠合法性过滤（与 _candidate_sets 一致）。
2. 重生成 p4_rule / p4_learned / p4_fused(a=0.75) / p4_exact / p4_no_pedal 五个 MusicXML
   （A2S_EXTEND_CANDIDATES=1 扩展候选模式）。

用法：
    A2S_EXTEND_CANDIDATES=1 python tools/p1_5_extend.py --index 0
    A2S_EXTEND_CANDIDATES=1 python tools/p1_5_extend.py --range 0-39
"""
from __future__ import annotations
import argparse, csv, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"
SELECTION = OUT / "selection.json"
MODEL = ROOT / "audio2score" / "models" / "p4_asap_cross_piece_v1"
EPS = 1e-7
KEY_MULTS = (2.0, 3.0, 4.0, 1.5, 0.5)
GRID = (0.25, 0.5, 0.375, 1.0 / 6.0, 1.0 / 3.0, 1.0)


def extend_candidates(orig: str, key_duration: float, next_gap: float) -> list[float]:
    cands = {float(x) for x in orig.split(";") if x.strip()}
    for mult in KEY_MULTS:
        cands.add(key_duration * mult)
    for d in GRID:
        cands.add(d)
    # 同 voice 不重叠硬约束（next_gap < 0 表示该 voice 无后续 onset）
    legal = sorted(c for c in cands
                   if c > EPS and (next_gap < 0 or c <= next_gap + EPS))
    return legal


def update_events(segment_dir: Path) -> None:
    path = segment_dir / "events.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    fields = list(rows[0].keys())
    changed = 0
    for row in rows:
        orig = row.get("candidate_durations", "")
        key = float(row["key_duration_ql"])
        next_gap = float(row["next_voice_gap_ql"])
        new = extend_candidates(orig, key, next_gap)
        row["candidate_durations"] = ";".join(f"{v:.6f}" for v in new)
        if "P1.5-extended" not in row.get("candidate_sources", ""):
            row["candidate_sources"] = (row.get("candidate_sources", "").strip(";")
                                        + ";P1.5-extended").strip(";")
        changed += 1
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  events.csv 更新 {changed} 行候选列")


def rebuild_musicxml(segment_dir: Path, seg_id: str, midi_path: Path) -> None:
    pipes = [
        ("p4_rule", ["--max-voices", "12", "--divisors", "8,4,3"]),
        ("p4_learned", ["--max-voices", "12", "--divisors", "8,4,3",
                        "--candidate-model", str(MODEL)]),
        ("p4_fused", ["--max-voices", "12", "--divisors", "8,4,3",
                      "--candidate-model", str(MODEL), "--fuse-alpha", "0.75"]),
        ("p4_exact", ["--max-voices", "12", "--divisors", "8,4,3",
                      "--pedal-placement", "exact"]),
        ("p4_no_pedal", ["--max-voices", "12", "--divisors", "8,4,3",
                         "--no-pedal"]),
    ]
    for name, extra in pipes:
        out = segment_dir / f"{name}.musicxml"
        cmd = [sys.executable, "audio2score/scripts/p4_multivoice_score.py",
               "--midi", str(midi_path), "--out", str(out)] + extra
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           env={**os.environ, "A2S_EXTEND_CANDIDATES": "1"})
        if r.returncode != 0:
            raise RuntimeError(f"{seg_id} {name} failed: {r.stderr[-800:]}")
        print(f"  {name} ok ({time.time()-t0:.1f}s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--range", default=None, help="a-b 闭区间")
    ap.add_argument("--skip-xml", action="store_true", help="只更新 events.csv")
    args = ap.parse_args()
    payload = json.loads(SELECTION.read_text(encoding="utf-8"))
    segments = payload["segments"]
    if args.index is not None:
        indices = [args.index]
    elif args.range:
        a, b = (int(x) for x in args.range.split("-"))
        indices = list(range(a, b + 1))
    else:
        indices = list(range(len(segments)))
    for i in indices:
        seg = segments[i]
        row = seg["row"]
        seg_id = f"{row['composer']}_{row['title']}_{seg['start_measure'] + 1}"
        segment_dir = OUT / seg_id
        print(f"[{i}] {seg_id}")
        update_events(segment_dir)
        if not args.skip_xml:
            midi_path = segment_dir / "performance_segment.mid"
            rebuild_musicxml(segment_dir, seg_id, midi_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
