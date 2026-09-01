#!/usr/bin/env python3
"""交接包只读完整性检查：不重跑冻结实验，不修改任何证据。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MODELS = {
    "audio2score/models/p4_asap_cross_piece_v1.txt": "31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666",
    "audio2score/models/p4_asap_cross_piece_v1.json": "7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6",
}
REQUIRED = [
    "README_HANDOFF_CN.md", "NEXT_AI_CONTEXT.md", "MANIFEST.md", "CHECKSUMS.sha256",
    "environment/INSTALL.md", "environment/requirements-backend.txt",
    "audio2score/scripts/p4_multivoice_score.py", "audio2score/scripts/run_c_pedal_ablation.py",
    "audio2score/scripts/score_metrics.py", "audio2score/samples/test_performance.mid",
    "data/ASAP/README.md", "data/ASAP/LICENSE.md", "data/asap_piece_manifest.csv",
    "data/batch_summary.csv", "data/alignments", "evals/B", "evals/C/frozen_test_20260817",
    "evals/C/pedal_ablation_frozen_20260818", "results/reports/C阶段_冻结踏板消融实验报告_20260818.pdf",
]


TEXT_EXTS = {
    ".txt", ".csv", ".py", ".md", ".json", ".sha256", ".sh", ".tex",
    ".musicxml", ".xml", ".yml", ".yaml", ".toml", ".rst", ".log",
    ".cfg", ".ini", ".gitignore", ".gitattributes", ".html", ".css",
}


def digest(path: Path) -> str:
    """Hash text files after universal newline normalization."""
    if path.suffix.lower() in TEXT_EXTS:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        data = text.encode("utf-8")
    else:
        data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()



def fail(message: str) -> None:
    print(f"[失败] {message}")
    raise SystemExit(1)


def check_required() -> None:
    missing = [item for item in REQUIRED if not (ROOT / item).exists()]
    if missing:
        fail("缺少必需资产：\n  " + "\n  ".join(missing))
    print(f"[通过] 必需资产存在：{len(REQUIRED)} 项")


def check_models() -> None:
    for rel, expected in EXPECTED_MODELS.items():
        actual = digest(ROOT / rel)
        if actual != expected:
            fail(f"冻结模型哈希不匹配：{rel}\n  期望 {expected}\n  实际 {actual}")
    print("[通过] 冻结 LightGBM 文本/元数据哈希匹配")


def check_manifest() -> None:
    path = ROOT / "data/asap_piece_manifest.csv"
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    test = [r for r in rows if r.get("split") == "test"]
    pieces = {r.get("piece_key") for r in test}
    if len(test) != 120 or len(pieces) != 31:
        fail(f"冻结 test manifest 不符：test={len(test)}，pieces={len(pieces)}；期望 120 / 31")
    print("[通过] 冻结 test manifest：120 演奏 / 31 作品")


def check_ablation() -> None:
    root = ROOT / "evals/C/pedal_ablation_frozen_20260818"
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if config.get("frozen_test_performance_count") != 120 or config.get("frozen_test_piece_count") != 31:
        fail("消融 config 的冻结集合计数不符")
    metric_paths = list(root.glob("pieces/**/metrics.json"))
    if len(metric_paths) != 480:
        fail(f"消融 metrics.json 数量为 {len(metric_paths)}，期望 480")
    status = Counter()
    pipeline = Counter()
    for path in metric_paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        status[row.get("status")] += 1
        pipeline[row.get("pipeline")] += 1
    expected = {"P4-R": 120, "P4-R-NP": 120, "P4-L": 120, "P4-L-NP": 120}
    if status != Counter({"completed": 480}) or dict(pipeline) != expected:
        fail(f"消融运行记录不符：status={dict(status)}，pipeline={dict(pipeline)}")
    summary = json.loads((root / "summary/aggregate_summary.json").read_text(encoding="utf-8"))
    serialized = json.dumps(summary, ensure_ascii=False)
    if "P4-R-NP" not in serialized or "P4-L-NP" not in serialized:
        fail("消融汇总中缺少无踏板管线")
    print("[通过] 严格 CC64 消融证据：480 completed，四管线各 120")


def check_checksums() -> None:
    checksum_file = ROOT / "CHECKSUMS.sha256"
    bad = []
    total = 0
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        expected, rel = line.split("  ", 1)
        path = ROOT / rel
        total += 1
        if not path.is_file() or digest(path) != expected:
            bad.append(rel)
    if bad:
        fail("CHECKSUMS.sha256 不匹配或缺失：\n  " + "\n  ".join(bad[:20]))
    print(f"[通过] CHECKSUMS.sha256：{total} 个关键文件全部匹配")


def main() -> None:
    parser = argparse.ArgumentParser(description="检查钢琴转谱项目交接包")
    parser.add_argument("--skip-checksums", action="store_true", help="跳过关键文件 SHA-256 校验")
    args = parser.parse_args()
    print(f"交接包根目录：{ROOT}")
    check_required()
    check_models()
    check_manifest()
    check_ablation()
    if not args.skip_checksums:
        check_checksums()
    print("[完成] 交接包结构、冻结模型与核心证据已通过只读核验。")


if __name__ == "__main__":
    main()
