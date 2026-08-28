#!/usr/bin/env python3
"""汇总 B 阶段单曲基线运行目录中的 ``metrics.json``。"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


PIPELINES = ("P3", "P4-R", "P4-L")


def load_rows(pieces_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(pieces_dir.glob("*/*/metrics.json")):
        metrics = json.loads(path.read_text(encoding="utf-8"))
        reconciliation = metrics.get("reconciliation", {})
        render_qa = metrics.get("render_qa", {})
        warnings = render_qa.get("warnings", {})
        rows.append({
            "piece_id": path.parent.parent.name,
            "pipeline": metrics.get("pipeline", path.parent.name),
            "status": metrics.get("status", "failed"),
            "acceptance_pass": metrics.get("acceptance_pass", False),
            "input_events": reconciliation.get("input_event_count"),
            "xml_events": reconciliation.get("xml_tie_merged_event_count"),
            "extra": reconciliation.get("extra_count"),
            "missing": reconciliation.get("missing_count"),
            "onset_drift": reconciliation.get("onset_drift_count"),
            "duration_drift": reconciliation.get("duration_drift_count"),
            "overfull_measures": render_qa.get("overfull_measure_count"),
            "tie_orphan_stop": render_qa.get("tie_orphan_stop_count"),
            "tie_unclosed_start": render_qa.get("tie_unclosed_start_count"),
            "tie_cross_voice": render_qa.get("tie_cross_voice_count"),
            "ties_left_open": warnings.get("ties_left_open"),
            "beam_or_layout_warnings": warnings.get("beam_or_layout"),
            "xml_parse_success": render_qa.get("xml_parse_success"),
            "render_success": render_qa.get("render_success"),
            "page_count": render_qa.get("page_count"),
            "metrics_path": str(path),
        })
    return rows


def sum_field(rows: list[dict], field: str) -> int:
    return sum(int(row.get(field) or 0) for row in rows)


def write_markdown(rows: list[dict], output: Path) -> None:
    by_pipeline: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_pipeline[row["pipeline"]].append(row)
    lines = [
        "# B 阶段三曲回归基线汇总",
        "",
        "> 该表评估的是导出忠实性、MusicXML 结构与渲染闭环；不是相对参考谱的音乐学质量主结果。",
        "",
        "## 汇总",
        "",
        "| 系统 | 曲目数 | 运行完成 | 验收通过 | 输入 / XML 事件 | 多写 | 漏写 | 起音漂移 | 时值偏差 | 超拍小节 | 未闭合 tie（Verovio） | 布局告警 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for pipeline in PIPELINES:
        group = by_pipeline.get(pipeline, [])
        total_input = sum_field(group, "input_events")
        total_xml = sum_field(group, "xml_events")
        completed = sum(row["status"] == "completed" for row in group)
        accepted = sum(bool(row["acceptance_pass"]) for row in group)
        lines.append(
            f"| {pipeline} | {len(group)} | {completed}/{len(group)} | {accepted}/{len(group)} | {total_input} / {total_xml} | "
            f"{sum_field(group, 'extra')} | {sum_field(group, 'missing')} | "
            f"{sum_field(group, 'onset_drift')} | {sum_field(group, 'duration_drift')} | "
            f"{sum_field(group, 'overfull_measures')} | {sum_field(group, 'ties_left_open')} | "
            f"{sum_field(group, 'beam_or_layout_warnings')} |"
        )
    lines.extend([
        "",
        "## 逐曲明细",
        "",
        "| 曲目 | 系统 | 运行状态 | 验收 | 输入 / XML | 多写 / 漏写 | 起音 / 时值漂移 | 超拍 | XML tie QA（孤立 stop / 未闭合 start / 跨 voice） | Verovio 未闭合 tie | 布局告警 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in rows:
        lines.append(
            f"| {row['piece_id']} | {row['pipeline']} | {row['status']} | "
            f"{'通过' if row['acceptance_pass'] else '未通过'} | "
            f"{row['input_events']} / {row['xml_events']} | {row['extra']} / {row['missing']} | "
            f"{row['onset_drift']} / {row['duration_drift']} | {row['overfull_measures']} | "
            f"{row['tie_orphan_stop']} / {row['tie_unclosed_start']} / {row['tie_cross_voice']} | "
            f"{row['ties_left_open']} | {row['beam_or_layout_warnings']} |"
        )
    lines.extend([
        "",
        "## 判读边界",
        "",
        "- `P3` 的时值偏差、未闭合 tie 警告若出现，应作为稳定对照的结构局限记录，不得据此掩盖 P4 的参考谱质量评测需求。",
        "- `P4-R` 与 `P4-L` 的 `0 多写 / 0 漏写 / 0 超拍` 只说明本次导出忠实实现了各自解码结果；候选模型的可读性或参考谱一致性仍须在后续系统级实验独立检验。",
        "- 布局警告单列保留，不与 XML 解析或逐音导出失败混为一谈。",
        "",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 B 阶段单曲基线结果")
    parser.add_argument("--pieces-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    rows = load_rows(Path(args.pieces_dir))
    if not rows:
        parser.error("未找到 metrics.json")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with (out_dir / "piece_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"run_count": len(rows), "pipelines": {}}
    for pipeline in PIPELINES:
        group = [row for row in rows if row["pipeline"] == pipeline]
        summary["pipelines"][pipeline] = {
            "runs": len(group),
            "completed": sum(row["status"] == "completed" for row in group),
            "acceptance_passed": sum(bool(row["acceptance_pass"]) for row in group),
            "input_events": sum_field(group, "input_events"), "xml_events": sum_field(group, "xml_events"),
            "extra": sum_field(group, "extra"), "missing": sum_field(group, "missing"),
            "onset_drift": sum_field(group, "onset_drift"), "duration_drift": sum_field(group, "duration_drift"),
            "overfull_measures": sum_field(group, "overfull_measures"),
            "ties_left_open": sum_field(group, "ties_left_open"),
            "beam_or_layout_warnings": sum_field(group, "beam_or_layout_warnings"),
        }
    (out_dir / "metrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(rows, out_dir / "baseline_comparison.md")
    print(f"已汇总 {len(rows)} 个运行：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
