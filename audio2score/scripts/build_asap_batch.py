#!/usr/bin/env python3
"""按 ASAP manifest 批量生成 P4 对齐和候选级自动监督数据。

每行 manifest 对应一个演奏。每条演奏的中间对齐/拒绝表保存在输出目录中，并写出一个
不会因单条失败而中断的汇总表；失败条目与其异常信息同样可审计。``max_events`` 可用于
小规模端到端试运行，不能作为正式模型评估数据。
"""
from __future__ import annotations

import argparse
import csv
import traceback
from collections import Counter
from pathlib import Path

from asap_alignment import build_asap_alignment
from auto_label_candidates import build_auto_labeled_dataset


SUMMARY_FIELDS = (
    "split", "piece_key", "composer", "title", "midi_performance", "status",
    "alignment_csv", "rejected_csv", "candidates_csv", "alignment_rows",
    "alignment_rejected", "candidate_rows", "candidate_events", "labeled_events",
    "unmatched_events", "duration_not_candidate_events", "ambiguous_candidate_events",
    "error",
)


def _safe_stem(performance: str) -> str:
    return performance.replace("/", "__").replace(".mid", "")


def _write_summary(rows, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_batch(asap_root: str | Path, manifest: str | Path, output_dir: str | Path,
                max_items: int | None = None, max_events: int | None = None,
                max_voices: int = 12) -> dict:
    """处理 manifest，返回汇总统计；个别条目失败写入 summary 而不静默跳过。"""
    root = Path(asap_root)
    with Path(manifest).open(encoding="utf-8", newline="") as handle:
        items = list(csv.DictReader(handle))
    if max_items is not None:
        if max_items <= 0:
            raise ValueError("max_items 必须为正整数")
        items = items[:max_items]
    out_root = Path(output_dir)
    alignment_dir, rejected_dir, candidates_dir = (
        out_root / "alignments", out_root / "rejected", out_root / "candidates"
    )
    summary = []
    for index, item in enumerate(items, start=1):
        stem = _safe_stem(item["midi_performance"])
        alignment = alignment_dir / f"{stem}.csv"
        rejected = rejected_dir / f"{stem}.csv"
        candidates = candidates_dir / f"{stem}.csv"
        row = {
            "split": item["split"], "piece_key": item["piece_key"],
            "composer": item["composer"], "title": item["title"],
            "midi_performance": item["midi_performance"], "status": "failed",
            "alignment_csv": str(alignment), "rejected_csv": str(rejected),
            "candidates_csv": str(candidates), "alignment_rows": 0, "alignment_rejected": 0,
            "candidate_rows": 0, "candidate_events": 0, "labeled_events": 0,
            "unmatched_events": 0, "duration_not_candidate_events": 0,
            "ambiguous_candidate_events": 0, "error": "",
        }
        try:
            align_stats = build_asap_alignment(
                root, item["midi_performance"], alignment, rejected,
                max_events=max_events,
            )
            candidate_stats = build_auto_labeled_dataset(
                str(root / item["midi_performance"]), str(root / item["xml_score"]),
                str(candidates), piece=f"asap:{item['piece_key']}:{index}",
                alignment_path=str(alignment), max_voices=max_voices,
            )
            row.update({
                "status": "ok", "alignment_rows": align_stats["rows"],
                "alignment_rejected": align_stats["rejected"],
                "candidate_rows": candidate_stats["rows"],
                "candidate_events": candidate_stats["events"],
                "labeled_events": candidate_stats.get("labeled", 0),
                "unmatched_events": candidate_stats.get("unmatched", 0),
                "duration_not_candidate_events": candidate_stats.get("reference-duration-not-candidate", 0),
                "ambiguous_candidate_events": candidate_stats.get("ambiguous-candidate", 0),
            })
        except Exception as exc:  # 批处理需要保留失败条目，以便修复后重跑。
            row["error"] = f"{type(exc).__name__}: {exc}"
        summary.append(row)
    _write_summary(summary, out_root / "batch_summary.csv")
    counts = Counter(row["status"] for row in summary)
    return {
        "requested": len(items), "ok": counts["ok"], "failed": counts["failed"],
        "alignment_rows": sum(int(row["alignment_rows"]) for row in summary),
        "candidate_rows": sum(int(row["candidate_rows"]) for row in summary),
        "labeled_events": sum(int(row["labeled_events"]) for row in summary),
        "summary": str(out_root / "batch_summary.csv"),
    }


def main():
    parser = argparse.ArgumentParser(description="按 ASAP 清单批量生成 P4 候选自动监督数据")
    parser.add_argument("--asap-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-items", type=int, help="仅处理 manifest 的前 N 行")
    parser.add_argument("--max-events", type=int, help="每条演奏仅处理前 N 个量化事件，用于受控试运行")
    parser.add_argument("--max-voices", type=int, default=12,
                        help="候选生成的最大显式 voice 数；默认 12，避免复调参考谱被静默丢弃")
    args = parser.parse_args()
    stats = build_batch(args.asap_root, args.manifest, args.out_dir, args.max_items,
                        args.max_events, args.max_voices)
    print("；".join(f"{key}={value}" for key, value in stats.items()))


if __name__ == "__main__":
    main()
