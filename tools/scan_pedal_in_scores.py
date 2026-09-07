#!/usr/bin/env python3
"""扫描 ASAP 全部乐谱的 <pedal> 标记 —— Phase 2 扩样候选池（pedal 富集采样）。

背景
----
trial8 ③ 列（published_score_pedal 判读）的证据必须依赖谱面含 <pedal> 的段。
但 40 段金标准是按“作曲家均衡 + 质量分”抽样选出的，谱面含 <pedal> 的只有
3 段（Chopin Scherzos 20 / Ravel Une Barque / Liszt TE9），其中 Liszt TE9 又
因对齐数据缺陷退出 F 组，导致 F 组可判证据一度只剩 Chopin 单段。

在投入“整个数据集重新标注”之前，先用 pedal 富集采样扩展验证样本：扫描
data/ASAP 全部 xml_score.musicxml，输出每首乐谱的 <pedal> 标签统计与所在
小节，作为 Phase 2 扩样选段的候选池。

用法
----
    python tools/scan_pedal_in_scores.py \
        --asap-root data/ASAP \
        --out outputs/pedal_expansion/score_pedal_scan.csv

输出列
------
folder, composer, title, pedal_starts, pedal_stops, pedal_changes,
measures_with_pedal, sample_measures, pedal_ratio_per_measure
"""
from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def scan_score(path: Path) -> dict:
    """统计一首 MusicXML 乐谱的 <pedal> 事件。

    返回: {starts, stops, changes, measures: {measure_no: Counter}}
    pedal 位于 <measure><direction><direction-type><pedal .../>。
    """
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return {"error": f"parse error: {exc}"}

    starts = stops = changes = 0
    measures: dict[str, Counter] = {}
    for part in root:
        if localname(part.tag) != "part":
            continue
        for measure in part:
            if localname(measure.tag) != "measure":
                continue
            mnum = measure.get("number", "?")
            cnt = Counter()
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
                        cnt[ptype] += 1
                        if ptype == "start":
                            starts += 1
                        elif ptype == "stop":
                            stops += 1
                        elif ptype == "change":
                            changes += 1
            if cnt:
                measures[mnum] = cnt
    return {"starts": starts, "stops": stops, "changes": changes,
            "measures": measures}


def collect_scores(asap_root: Path) -> list[Path]:
    """递归找所有名为 xml_score.musicxml 的文件。"""
    out = []
    for p in sorted(asap_root.rglob("xml_score.musicxml")):
        out.append(p)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--asap-root", default="data/ASAP",
                        help="ASAP 数据根目录（含 Composer/.../xml_score.musicxml）")
    parser.add_argument("--out", default="outputs/pedal_expansion/score_pedal_scan.csv")
    args = parser.parse_args()

    asap_root = Path(args.asap_root)
    if not asap_root.is_dir():
        print(f"error: {asap_root} 不是目录", file=sys.stderr)
        return 2
    scores = collect_scores(asap_root)
    if not scores:
        print(f"error: {asap_root} 下未找到任何 xml_score.musicxml", file=sys.stderr)
        return 2

    rows = []
    for score in scores:
        folder = score.parent
        rel = folder.relative_to(asap_root)
        parts = rel.parts
        composer = parts[0] if parts else "?"
        title = parts[-1] if parts else "?"
        stat = scan_score(score)
        if "error" in stat:
            rows.append({"folder": str(rel), "composer": composer, "title": title,
                         "pedal_starts": "ERR", "pedal_stops": "ERR",
                         "pedal_changes": "ERR", "measures_with_pedal": 0,
                         "sample_measures": stat["error"], "notes": "parse_error"})
            continue
        ms = stat["measures"]
        # sample: 最多 12 个小节号
        sample = ",".join(f"{m}({dict(c)})" for m, c in sorted(ms.items(),
                         key=lambda kv: (len(kv[1]) > 0, int(kv[0]) if kv[0].isdigit() else 0))[:12])
        n_measure = len(ms)
        rows.append({"folder": str(rel), "composer": composer, "title": title,
                     "pedal_starts": stat["starts"], "pedal_stops": stat["stops"],
                     "pedal_changes": stat["changes"], "measures_with_pedal": n_measure,
                     "sample_measures": sample, "notes": ""})

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["folder", "composer", "title",
                                          "pedal_starts", "pedal_stops",
                                          "pedal_changes", "measures_with_pedal",
                                          "sample_measures", "notes"])
        w.writeheader()
        w.writerows(rows)

    with_pedal = [r for r in rows if str(r["pedal_starts"]).isdigit()
                  and (int(r["pedal_starts"]) + int(r["pedal_stops"])
                       + int(r["pedal_changes"])) > 0]
    print(f"scanned {len(rows)} scores -> {out_path}")
    print(f"scores with <pedal>: {len(with_pedal)}")
    for r in with_pedal:
        print(f"  {r['composer']} / {r['title']}: "
              f"start={r['pedal_starts']} stop={r['pedal_stops']} "
              f"change={r['pedal_changes']} measures={r['measures_with_pedal']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
