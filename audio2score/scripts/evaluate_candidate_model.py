#!/usr/bin/env python3
"""在作品隔离的候选 CSV 上训练并评估 P4 候选级模型。"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from train_candidate_model import DEFAULT_CHUNK_SIZE, LightGBMCandidateScorer, train_model


def _read_summary(path: str | Path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["status"] == "ok"]


def _project_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path


def _rows(path: str | Path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _roc_auc(y, scores) -> float | None:
    positives = sum(y)
    negatives = len(y) - positives
    if not positives or not negatives:
        return None
    ordered = sorted(zip(scores, y), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum += average_rank * sum(label for _score, label in ordered[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _average_precision(y, scores) -> float | None:
    positives = sum(y)
    if not positives:
        return None
    ordered = sorted(zip(scores, y), key=lambda item: item[0], reverse=True)
    hits, total = 0, 0.0
    for rank, (_score, label) in enumerate(ordered, start=1):
        if label:
            hits += 1
            total += hits / rank
    return total / positives


def _top1(rows, scores, column: str) -> float | None:
    groups = defaultdict(list)
    for row, score in zip(rows, scores):
        if row.get("label", "") in {"0", "1"}:
            groups[row["candidate_event_id"]].append((row, score))
    if not groups:
        return None
    correct = 0
    for candidates in groups.values():
        best = max(score for _row, score in candidates)
        winners = [(row, score) for row, score in candidates if score == best]
        if len(winners) == 1 and winners[0][0]["label"] == "1":
            correct += 1
    return correct / len(groups)


def _metrics(rows, probabilities) -> dict:
    labeled = [(row, p) for row, p in zip(rows, probabilities) if row.get("label", "") in {"0", "1"}]
    y = [int(row["label"]) for row, _p in labeled]
    scores = [p for _row, p in labeled]
    rule_scores = [float(row["rule_probability"]) for row, _p in labeled]
    return {
        "labeled_candidates": len(labeled), "positive_candidates": sum(y),
        "negative_candidates": len(y) - sum(y),
        "labeled_events": len({row["candidate_event_id"] for row, _p in labeled}),
        "model_roc_auc": _roc_auc(y, scores),
        "model_average_precision": _average_precision(y, scores),
        "model_top1_accuracy": _top1([row for row, _p in labeled], scores, "model_probability"),
        "rule_roc_auc": _roc_auc(y, rule_scores),
        "rule_average_precision": _average_precision(y, rule_scores),
        "rule_top1_accuracy": _top1([row for row, _p in labeled], rule_scores, "rule_probability"),
    }


class _MetricAccumulator:
    """只保存已标注候选的紧凑指标输入，并按文件完成 top-1 分组。"""

    def __init__(self):
        self.model_scores, self.rule_scores, self.labels = [], [], []
        self.candidate_rows = 0
        self._top1_correct = 0
        self._top1_events = 0
        self._events = {}

    def add(self, row, probability):
        self.candidate_rows += 1
        label = row.get("label", "")
        if label not in {"0", "1"}:
            return
        self.model_scores.append(probability)
        self.rule_scores.append(float(row["rule_probability"]))
        self.labels.append(int(label))
        event = row["candidate_event_id"]
        score = (probability, int(label))
        previous = self._events.get(event)
        if previous is None or score[0] > previous[0]:
            self._events[event] = (score[0], score[1], 1)
        elif score[0] == previous[0]:
            self._events[event] = (previous[0], previous[1], previous[2] + 1)

    def finish_file(self):
        for best, label, ties in self._events.values():
            self._top1_events += 1
            if ties == 1 and label == 1:
                self._top1_correct += 1
        self._events.clear()

    def metrics(self):
        labeled = len(self.labels)
        return {
            "labeled_candidates": labeled,
            "positive_candidates": sum(self.labels),
            "negative_candidates": labeled - sum(self.labels),
            "labeled_events": self._top1_events,
            "model_roc_auc": _roc_auc(self.labels, self.model_scores),
            "model_average_precision": _average_precision(self.labels, self.model_scores),
            "model_top1_accuracy": (self._top1_correct / self._top1_events
                                     if self._top1_events else None),
            "rule_roc_auc": _roc_auc(self.labels, self.rule_scores),
            "rule_average_precision": _average_precision(self.labels, self.rule_scores),
            "rule_top1_accuracy": _top1_from_arrays(self.labels, self.rule_scores),
        }


def _top1_from_arrays(labels, scores):
    # Rule top-1 needs event IDs; it is accumulated separately by the streamer.
    return None


def _score_split(paths, scorer, output_path=None, chunk_size=DEFAULT_CHUNK_SIZE):
    """逐文件、逐块评分；可选地输出 scored CSV，并返回精确累计指标。"""
    acc = _MetricAccumulator()
    rule_correct = rule_total = 0
    target = None
    writer = None
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target = output_path.open("w", encoding="utf-8", newline="")

    def consume(rows, rule_events):
        probabilities = scorer.score_rows(rows)
        for item, probability in zip(rows, probabilities):
            if writer is not None:
                item["model_probability"] = f"{probability:.9f}"
                writer.writerow(item)
            acc.add(item, probability)
            if item.get("label", "") in {"0", "1"}:
                event = item["candidate_event_id"]
                rule, label = float(item["rule_probability"]), int(item["label"])
                old = rule_events.get(event)
                if old is None or rule > old[0]:
                    rule_events[event] = (rule, label, 1)
                elif rule == old[0]:
                    rule_events[event] = (old[0], old[1], old[2] + 1)

    try:
        for path in paths:
            rule_events = {}
            with Path(path).open(encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                fields = list(reader.fieldnames or ())
                missing = set(scorer._columns) - set(fields)
                if missing:
                    raise ValueError(f"候选 CSV 缺少模型特征列：{sorted(missing)}：{path}")
                if target is not None:
                    if writer is None:
                        writer = csv.DictWriter(target, fieldnames=fields + ["model_probability"])
                        writer.writeheader()
                    elif fields != writer.fieldnames[:-1]:
                        raise ValueError(f"候选 CSV 表头不一致：{path}")
                rows = []
                for row in reader:
                    rows.append(row)
                    if len(rows) >= chunk_size:
                        consume(rows, rule_events)
                        rows = []
                if rows:
                    consume(rows, rule_events)
            acc.finish_file()
            for _best, label, ties in rule_events.values():
                rule_total += 1
                if ties == 1 and label == 1:
                    rule_correct += 1
    finally:
        if target is not None:
            target.close()
    metrics = acc.metrics()
    metrics["rule_top1_accuracy"] = rule_correct / rule_total if rule_total else None
    return metrics


def run_evaluation(summary_path: str | Path, output_dir: str | Path,
                   chunk_size: int = DEFAULT_CHUNK_SIZE, write_scored: bool = True) -> dict:
    """训练集训练、验证和测试集只评分；按块写出指标与打分 CSV。"""
    summary = _read_summary(summary_path)
    split_paths = defaultdict(list)
    for item in summary:
        split_paths[item["split"]].append(_project_path(item["candidates_csv"]))
    if not split_paths["train"] or not split_paths["validation"] or not split_paths["test"]:
        raise ValueError("汇总表必须含成功的 train、validation、test 候选 CSV")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_prefix = out / "candidate_model"
    training_count = train_model(split_paths["train"], model_prefix, chunk_size=chunk_size)
    scorer = LightGBMCandidateScorer(model_prefix)
    results = {"training_labeled_candidates": training_count, "splits": {}}
    for split in ("train", "validation", "test"):
        scored_path = out / f"{split}_scored_candidates.csv" if write_scored else None
        metrics = _score_split(split_paths[split], scorer, scored_path, chunk_size)
        metrics["candidate_rows"] = sum(int(item["candidate_rows"]) for item in summary if item["split"] == split)
        metrics["scored_csv"] = str(scored_path) if scored_path is not None else None
        results["splits"][split] = metrics
    (out / "evaluation_metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return results


def main():
    parser = argparse.ArgumentParser(description="按作品级划分评估 P4 候选级模型")
    parser.add_argument("--batch-summary", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--no-scored", action="store_true", help="不写出逐候选打分 CSV，节省磁盘")
    args = parser.parse_args()
    result = run_evaluation(args.batch_summary, args.out_dir, args.chunk_size, not args.no_scored)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
