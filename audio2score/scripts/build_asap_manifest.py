#!/usr/bin/env python3
"""构建 ASAP 的作品级训练/验证/测试清单。

划分键固定为 ``composer + title``，故同一作品的不同演奏绝不会跨集合。脚本只保留
ASAP 已声明与参考谱完整对齐、且核心 MIDI/MusicXML 文件存在的演奏记录；结果同时给出
全量清单和可在普通开发主机上快速验证的、每作品一条演奏的受控 pilot 清单。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


SPLITS = ("train", "validation", "test")


def _piece_key(row: dict) -> str:
    return f"{row['composer']}\x1f{row['title']}"


def _split_for(piece_key: str) -> str:
    """稳定散列划分：70% / 15% / 15%，不依赖 CSV 行序。"""
    bucket = int(hashlib.sha256(piece_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def build_manifest(asap_root: str | Path, output: str | Path,
                   pilot_output: str | Path | None = None,
                   pilot_per_split: int = 3) -> dict:
    """写出完整和小规模 pilot 清单，返回可审计统计。"""
    root = Path(asap_root)
    with (root / "metadata.csv").open(encoding="utf-8", newline="") as handle:
        metadata = list(csv.DictReader(handle))
    annotations = json.loads((root / "asap_annotations.json").read_text(encoding="utf-8"))

    eligible, rejected = [], Counter()
    for row in metadata:
        annotation = annotations.get(row["midi_performance"])
        if not annotation or not annotation.get("score_and_performance_aligned", False):
            rejected["not-aligned-or-no-annotation"] += 1
            continue
        beats = annotation.get("performance_beats", [])
        if len(beats) < 2 or len(beats) != len(annotation.get("midi_score_beats", [])):
            rejected["invalid-beat-map"] += 1
            continue
        if not all((root / row[column]).is_file()
                   for column in ("midi_performance", "midi_score", "xml_score")):
            rejected["missing-core-file"] += 1
            continue
        item = dict(row)
        item["piece_key"] = _piece_key(row)
        item["split"] = _split_for(item["piece_key"])
        eligible.append(item)

    groups = defaultdict(list)
    for row in eligible:
        groups[row["piece_key"]].append(row)
    ordered = []
    for piece_key in sorted(groups):
        rows = sorted(groups[piece_key], key=lambda row: row["midi_performance"])
        for performance_rank, row in enumerate(rows, start=1):
            row["performance_rank_in_piece"] = performance_rank
            row["performances_in_piece"] = len(rows)
            ordered.append(row)

    fields = [
        "split", "piece_key", "composer", "title", "performance_rank_in_piece",
        "performances_in_piece", "midi_performance", "midi_score", "xml_score",
    ]
    def write(rows, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    write(ordered, output)
    pilot = []
    for split in SPLITS:
        pieces = [key for key in groups if _split_for(key) == split]
        # 稳定散列而非字典序选择，避免试运行样本被目录中靠前的同一作曲家垄断。
        pieces.sort(key=lambda key: (hashlib.sha256(key.encode("utf-8")).hexdigest(), key))
        selected_composers = set()
        for piece_key in pieces:
            composer = groups[piece_key][0]["composer"]
            if composer in selected_composers:
                continue
            pilot.append(sorted(groups[piece_key], key=lambda row: row["midi_performance"])[0])
            selected_composers.add(composer)
            if len(selected_composers) == pilot_per_split:
                break
        if len(selected_composers) < pilot_per_split:
            selected_keys = {row["piece_key"] for row in pilot if row["split"] == split}
            for piece_key in pieces:
                if piece_key in selected_keys:
                    continue
                pilot.append(sorted(groups[piece_key], key=lambda row: row["midi_performance"])[0])
                selected_keys.add(piece_key)
                if len(selected_keys) == pilot_per_split:
                    break
    if pilot_output:
        write(pilot, pilot_output)

    counts = Counter(row["split"] for row in ordered)
    piece_counts = Counter(_split_for(key) for key in groups)
    return {
        "eligible_performances": len(ordered), "eligible_pieces": len(groups),
        **{f"{split}_performances": counts[split] for split in SPLITS},
        **{f"{split}_pieces": piece_counts[split] for split in SPLITS},
        **{f"rejected_{reason}": count for reason, count in sorted(rejected.items())},
        "pilot_performances": len(pilot),
    }


def main():
    parser = argparse.ArgumentParser(description="构建 ASAP 作品级划分清单")
    parser.add_argument("--asap-root", required=True)
    parser.add_argument("--out", required=True, help="全量 manifest CSV")
    parser.add_argument("--pilot-out", help="每个集合选取每作品首条演奏的 pilot manifest CSV")
    parser.add_argument("--pilot-per-split", type=int, default=3)
    args = parser.parse_args()
    if args.pilot_per_split <= 0:
        parser.error("--pilot-per-split 必须为正整数")
    stats = build_manifest(args.asap_root, args.out, args.pilot_out, args.pilot_per_split)
    print("；".join(f"{key}={value}" for key, value in stats.items()))


if __name__ == "__main__":
    main()
