"""扫描 40 片段：演奏 QL 窗口与乐谱/切片小节的一致性（P0 坐标修复的第一步）。

背景（2026-09-01 调查结论）：
- segment_metadata.json 的 start_ql/end_ql 是"演奏 QL"（演奏 MIDI 时间轴，秒 x tempo/60）
- reference_score.musicxml 切片用 start_measure（由 bar_ql 换算；bar_ql 来自演奏 MIDI
  的拍号检测，可能与乐谱真实拍号不一致）
- reference_events.csv / reference_pedals.csv 用演奏 QL 窗口直接过滤"乐谱 QL 坐标系"
  （xml bar_ql 累计 / midi_score tick），三者坐标系混用导致金标准参考产物错位。
本脚本用 _alignments/<sid>.csv（基于 ASAP beat 标注的对齐）确定每个片段演奏窗口
对应的真实乐谱 QL 范围，并用乐谱（xml_score.musicxml）真实拍号换算成小节，
与 metadata 记录的切片小节对比，输出受影响清单。

用法：
  python tools/scan_segment_coordinate_mismatch.py       --asap data/ASAP       --formal outputs/pedal_gold_standard/formal_20260828_v1       --align-dir outputs/pedal_gold_standard/formal_20260828_v1/_alignments       --out evaluation/segment_coordinate_mismatch.json
"""
import argparse
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read_alignment(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def xml_measure_ql_map(xml_path: Path):
    """逐小节累计乐谱 QL（处理拍号变化），返回 [(measure_number, start_ql, bar_ql)]。"""
    root = ET.parse(str(xml_path)).getroot()
    out = []
    for part in root.findall("part"):
        bar_ql = 4.0
        measure_start = 0.0
        for measure in part.findall("measure"):
            beats = measure.findtext("attributes/time/beats")
            beat_type = measure.findtext("attributes/time/beat-type")
            if beats and beat_type:
                bar_ql = 4.0 * float(beats) / float(beat_type)
            out.append((int(measure.get("number")), measure_start, bar_ql))
            measure_start += bar_ql
        break
    return out


def ql_to_measure_range(ql0: float, ql1: float, ql_map) -> tuple[int, int] | None:
    """乐谱 QL 区间 [ql0, ql1) 覆盖的小节号（1-based）。"""
    nums = []
    for mnum, m_start, m_bar in ql_map:
        if m_start + m_bar > ql0 and m_start < ql1:
            nums.append(mnum)
    return (min(nums), max(nums)) if nums else None


def main():
    parser = argparse.ArgumentParser(description="坐标一致性扫描")
    parser.add_argument("--asap", type=Path, default=Path("data/ASAP"))
    parser.add_argument("--formal", type=Path, default=Path("outputs/pedal_gold_standard/formal_20260828_v1"))
    parser.add_argument("--align-dir", type=Path, default=Path("outputs/pedal_gold_standard/formal_20260828_v1/_alignments"))
    parser.add_argument("--out", type=Path, default=Path("evaluation/segment_coordinate_mismatch.json"))
    args = parser.parse_args()

    results = []
    for meta_path in sorted(args.formal.glob("*/segment_metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        sid = meta["segment_id"]
        entry = {
            "segment_id": sid,
            "meta_bar_ql": meta["bar_ql"],
            "meta_time_sig": meta.get("time_signature"),
            "meta_sliced_measures": [meta["start_measure"] + 1, meta["end_measure"] + 1],
            "start_ql": meta["start_ql"],
            "end_ql": meta["end_ql"],
        }
        align_path = args.align_dir / (sid + ".csv")
        if not align_path.exists():
            entry["error"] = "alignment missing"
            results.append(entry)
            continue
        arows = read_alignment(align_path)
        win = [r for r in arows
               if meta["start_ql"] - 1e-6 <= float(r["onset_ql"]) < meta["end_ql"]]
        if not win:
            entry["error"] = "no alignment rows in window"
            results.append(entry)
            continue
        refs = [float(r["reference_onset_ql"]) for r in win]
        entry["score_window_ql"] = [round(min(refs), 3), round(max(refs), 3)]

        xml_rel = meta["manifest"].get("xml_score")
        xml_path = args.asap / xml_rel
        if xml_path.exists():
            ql_map = xml_measure_ql_map(xml_path)
            entry["score_first_bar_ql"] = ql_map[0][2] if ql_map else None
            entry["score_window_measures"] = ql_to_measure_range(min(refs), max(refs), ql_map)
            entry["true_sliced_measures"] = ql_to_measure_range(
                meta["start_ql"], meta["end_ql"], ql_map)
        else:
            entry["score_window_measures"] = None
            entry["true_sliced_measures"] = None

        # 受影响判定：演奏 QL 窗口按乐谱拍号换算的小节，与 metadata 切片小节不一致
        entry["affected"] = (
            entry["score_window_measures"] is not None
            and entry["score_window_measures"] != tuple(entry["meta_sliced_measures"])
        )
        results.append(entry)

    for r in results:
        if "error" in r:
            print("ERR ", r["segment_id"], r["error"])
        else:
            flag = "AFFECTED" if r["affected"] else "ok"
            print(flag, r["segment_id"],
                  "| meta_slice:", r["meta_sliced_measures"],
                  "| true_slice:", r["true_sliced_measures"],
                  "| score_win_measures:", r["score_window_measures"],
                  "| score_win_ql:", r["score_window_ql"])

    affected = [r for r in results if r.get("affected")]
    print()
    print("total:", len(results), "| affected:", len(affected))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written:", args.out)


if __name__ == "__main__":
    main()
