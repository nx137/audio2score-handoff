#!/usr/bin/env python3
"""P4d：候选级概率模型训练与推断。

默认不要求 LightGBM。未安装或没有已标注行时，使用结构化解码器的规则概率；
一旦 CSV 中填写 ``label``（1=正确候选，0=非正确候选），即可训练二分类模型。

训练与 CSV 打分都按固定大小块读取，避免全量 ASAP 候选表在 Python dict 中展开。
模型仅使用可靠的 ``0/1`` 标签；空标签绝不会被当成负例。
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Mapping

from structured_duration_decoder import candidate_probability

FEATURES = (
    "pitch", "velocity", "voice", "onset_ql", "beat_position",
    "key_duration_ql", "acoustic_duration_ql", "pedal_extension_ql",
    "next_voice_gap_ql", "candidate_duration_ql", "candidate_key_gap_ql",
    "candidate_acoustic_gap_ql", "candidate_crosses_barline",
    "candidate_has_barline", "candidate_has_next_onset", "rule_probability",
)

_EPS = 1e-9
_NEARLY_ONE = 0.999999
DEFAULT_CHUNK_SIZE = 16_384


def _rows(paths):
    for path in paths:
        with Path(path).open(encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)


def _matrix(rows):
    """兼容小数据/单元测试的 dict 行矩阵构造器。"""
    x, y = [], []
    for row in rows:
        label = row.get("label", "").strip()
        if label not in {"0", "1"}:
            continue
        x.append([float(row[name]) for name in FEATURES])
        y.append(int(label))
    return x, y


def load_labeled_matrix(inputs, chunk_size: int = DEFAULT_CHUNK_SIZE):
    """流式读取 CSV，仅保留可靠标签的数值特征矩阵。"""
    import numpy as np

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正整数")
    feature_chunks, label_chunks = [], []
    x_chunk, y_chunk = [], []
    required = set(FEATURES) | {"label"}
    for path in inputs:
        with Path(path).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = required - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"输入 CSV 缺少训练列：{sorted(missing)}：{path}")
            for row in reader:
                label = row.get("label", "").strip()
                if label not in {"0", "1"}:
                    continue
                x_chunk.append([float(row[name]) for name in FEATURES])
                y_chunk.append(int(label))
                if len(x_chunk) >= chunk_size:
                    feature_chunks.append(np.asarray(x_chunk, dtype=np.float32))
                    label_chunks.append(np.asarray(y_chunk, dtype=np.int8))
                    x_chunk, y_chunk = [], []
    if x_chunk:
        feature_chunks.append(np.asarray(x_chunk, dtype=np.float32))
        label_chunks.append(np.asarray(y_chunk, dtype=np.int8))
    if not feature_chunks:
        return np.empty((0, len(FEATURES)), dtype=np.float32), np.empty(0, dtype=np.int8)
    return np.concatenate(feature_chunks), np.concatenate(label_chunks)


def train_model(inputs, output, chunk_size: int = DEFAULT_CHUNK_SIZE):
    x, y = load_labeled_matrix(inputs, chunk_size=chunk_size)
    if len(x) < 2 or len(set(y.tolist())) < 2:
        raise ValueError("至少需要各含一个 0 和 1 标签的两条候选记录")
    try:
        from lightgbm import LGBMClassifier
    except ImportError as exc:
        raise RuntimeError("未安装 LightGBM；请保留规则模型，或安装后重新训练") from exc
    model = LGBMClassifier(
        objective="binary", n_estimators=120, learning_rate=0.05,
        num_leaves=15, max_depth=5, random_state=7, verbosity=-1,
    )
    model.fit(x, y)
    payload = {"features": list(FEATURES), "backend": "lightgbm"}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(output.with_suffix(".txt")))
    output.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(x)


def _load_payload(model_path) -> dict:
    """读取训练时写下的元信息（特征顺序）；兼容旧布局。"""
    for candidate in (Path(model_path), Path(model_path).with_suffix(".json")):
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


class LightGBMCandidateScorer:
    """把已训练的 LightGBM Booster 包装为候选特征到概率的适配器。"""

    def __init__(self, model_path, features=FEATURES, payload=None):
        import lightgbm as lgb
        self.booster = lgb.Booster(model_file=str(Path(model_path).with_suffix(".txt")))
        meta = dict(payload or _load_payload(model_path))
        self.features = tuple(meta.get("features") or features)
        if self.booster.num_feature() != len(self.features):
            raise ValueError(
                f"Booster 特征数 {self.booster.num_feature()} 与特征表 "
                f"{len(self.features)} 不一致；请核对模型与 FEATURES"
            )
        self._columns = self._resolve_columns()

    def _resolve_columns(self) -> list[str]:
        names = list(self.booster.feature_name())
        auto = [f"Column_{i}" for i in range(len(names))]
        if names and names != auto:
            missing = [name for name in names if name not in set(self.features)]
            if missing:
                raise ValueError(f"Booster 特征名与特征表不匹配，缺失：{missing}；请核对模型与 FEATURES")
            return names
        return list(self.features)

    def score_matrix(self, matrix) -> list[float]:
        """对已按模型列序构造的有限批矩阵打分。"""
        probabilities = self.booster.predict(matrix, raw_score=False)
        return [_EPS if p <= 0.0 else min(float(p), _NEARLY_ONE) for p in probabilities]

    def score_features(self, features: Mapping) -> float:
        return self.score_rows([features])[0]

    def score_rows(self, rows: Iterable[Mapping]) -> list[float]:
        """兼容旧接口：对小批 dict 行打分。"""
        matrix = [[float(row[name]) for name in self._columns] for row in rows]
        return self.score_matrix(matrix) if matrix else []

    def predict(self, duration, key_duration, acoustic_duration, source):
        return candidate_probability(duration, key_duration, acoustic_duration, source)

    def __call__(self, first, *rest):
        if rest or not isinstance(first, Mapping):
            return self.predict(first, *rest)
        return self.score_features(first)


def probability_from_model(model_path, features=None):
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        return candidate_probability
    booster_path = Path(model_path).with_suffix(".txt")
    if not booster_path.exists():
        return candidate_probability
    return LightGBMCandidateScorer(model_path, features=features or FEATURES)


def score_csv(model_path, inputs, output, chunk_size: int = DEFAULT_CHUNK_SIZE):
    """分块给候选 CSV 打分，追加 ``model_probability`` 列。"""
    scorer = probability_from_model(model_path)
    if scorer is candidate_probability:
        raise RuntimeError(f"LightGBM 不可用或模型不存在：{model_path}")
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正整数")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count, wrote_header = 0, False
    with output.open("w", newline="", encoding="utf-8") as target:
        writer = None
        for path in inputs:
            with Path(path).open(encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                fields = list(reader.fieldnames or ())
                missing = set(scorer._columns) - set(fields)
                if missing:
                    raise ValueError(f"输入 CSV 缺少模型特征列：{sorted(missing)}：{path}")
                if not wrote_header:
                    writer = csv.DictWriter(target, fieldnames=fields + ["model_probability"])
                    writer.writeheader()
                    wrote_header = True
                elif fields != writer.fieldnames[:-1]:
                    raise ValueError(f"输入 CSV 表头不一致：{path}")
                rows = []
                for row in reader:
                    rows.append(row)
                    if len(rows) >= chunk_size:
                        probabilities = scorer.score_rows(rows)
                        for item, probability in zip(rows, probabilities):
                            item["model_probability"] = f"{probability:.6f}"
                            writer.writerow(item)
                        count += len(rows)
                        rows = []
                if rows:
                    probabilities = scorer.score_rows(rows)
                    for item, probability in zip(rows, probabilities):
                        item["model_probability"] = f"{probability:.6f}"
                        writer.writerow(item)
                    count += len(rows)
    if not wrote_header:
        raise ValueError("输入 CSV 没有数据行")
    return count


def main():
    parser = argparse.ArgumentParser(description="P4 候选级概率模型：训练与打分")
    parser.add_argument("--inputs", nargs="+", required=False, help="候选特征 CSV")
    parser.add_argument("--out", required=False)
    parser.add_argument("--model", default=None, help="打分模式使用的已训练模型")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    args = parser.parse_args()
    if args.model:
        if not args.inputs or not args.out:
            parser.error("打分模式需要 --inputs 与 --out")
        count = score_csv(args.model, args.inputs, args.out, args.chunk_size)
        print(f"对 {count} 个候选打分：{args.out}")
    else:
        if not args.inputs or not args.out:
            parser.error("训练模式需要 --inputs 与 --out")
        count = train_model(args.inputs, args.out, args.chunk_size)
        print(f"使用 {count} 条已标注候选训练模型：{args.out}")


if __name__ == "__main__":
    main()
