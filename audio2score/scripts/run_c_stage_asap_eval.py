#!/usr/bin/env python3
"""C 阶段：冻结 ASAP test 集上 P3/P4-R/P4-L 相对参考谱的系统级评测。

严格边界（不得违反）：
  - 只读取 ``asap_piece_manifest.csv`` 中 ``split == "test"`` 的 120 条演奏；
  - 外部对齐 CSV 全部复用自 ``full_run/batch_summary.csv`` 已生成的资产，不重新生成、
    不用系统输出反推对齐；
  - test 集只用于本次锁定报告，任何参数调整都必须先在 train/valid 上完成；
  - P4-L 候选模型文件的 SHA-256 必须与 B 阶段记录的冻结值一致，否则拒绝运行；
  - 汇总报告须显式区分候选级排序指标、导出忠实性（B 阶段）与相对参考谱质量（本阶段）。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from score_metrics import evaluate_score

PIPELINES = ("P3", "P4-R", "P4-L")

# B 阶段记录的冻结候选模型哈希；C 阶段必须复用同一模型，不得用 test 结果重新训练。
EXPECTED_MODEL_SHA256 = {
    "p4_asap_cross_piece_v1.txt": "31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666",
    "p4_asap_cross_piece_v1.json": "7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6",
}

F1_METRICS = ("pitch", "onset", "note")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(command: list[str], log: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(command, ensure_ascii=False) + f"\texit={result.returncode}\n")
        if result.stdout:
            handle.write("STDOUT\n" + result.stdout)
        if result.stderr:
            handle.write("STDERR\n" + result.stderr)
    return result


def load_test_rows(manifest_path: Path) -> list[dict]:
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row["split"] == "test"]


def load_alignment_index(batch_summary_path: Path) -> dict[str, dict]:
    with batch_summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["midi_performance"]: row for row in rows if row["split"] == "test"}


def safe_id(midi_performance: str) -> str:
    """与既有对齐资产同一命名规则：``Composer/Title/opus/Perf.mid`` → 下划线拼接。"""
    stem = midi_performance
    if stem.endswith(".mid"):
        stem = stem[: -len(".mid")]
    return stem.replace("/", "__")


def export_command(pipeline: str, midi_path: Path, xml_path: Path, title: str,
                   divisors: str, max_voices: int, candidate_model: str | None,
                   scripts_dir: Path) -> list[str]:
    if pipeline == "P3":
        return [sys.executable, str(scripts_dir / "midi_to_score.py"),
               "--midi", str(midi_path), "--out", str(xml_path),
               "--title", title, "--divisors", divisors]
    command = [sys.executable, str(scripts_dir / "p4_multivoice_score.py"),
              "--midi", str(midi_path), "--out", str(xml_path),
              "--title", title, "--divisors", divisors, "--max-voices", str(max_voices)]
    if pipeline == "P4-L":
        command.extend(["--candidate-model", str(candidate_model)])
    return command


def flatten_metrics(metrics: dict) -> dict:
    """把 evaluate_score() 的嵌套结果压平成汇总 CSV 需要的标量列。"""
    out = {}
    for name in F1_METRICS:
        block = metrics[name]
        out[f"{name}_tp"] = block["tp"]
        out[f"{name}_predicted"] = block["predicted"]
        out[f"{name}_reference"] = block["reference"]
        out[f"{name}_precision"] = block["precision"]
        out[f"{name}_recall"] = block["recall"]
        out[f"{name}_f1"] = block["f1"]
    duration = metrics["duration"]
    out["duration_matched_events"] = duration["matched_events"]
    out["duration_correct_events"] = (
        round(duration["accuracy"] * duration["matched_events"]) if duration["accuracy"] is not None else 0
    )
    out["duration_accuracy"] = duration["accuracy"]
    out["duration_mae_ql"] = duration["mae_ql"]
    tie = metrics["tie_chain"]
    out["tie_available"] = tie["available"]
    out["tie_matched_events"] = tie["reliably_mapped_reference_tied_events"]
    out["tie_correct_events"] = tie["correct_chain_role_events"]
    out["tie_accuracy"] = tie["accuracy"]
    voice = metrics["voice_consistency"]
    out["voice_available"] = voice["available"]
    out["voice_matched_events"] = voice["matched_note_events"]
    out["voice_correct_events"] = voice["majority_consistent_events"]
    out["voice_accuracy"] = voice["accuracy"]
    pedal = metrics["pedal"]
    out["pedal_available"] = pedal["available"]
    if pedal["available"]:
        out["pedal_tp"] = pedal["all"]["tp"]
        out["pedal_predicted"] = pedal["all"]["predicted"]
        out["pedal_reference"] = pedal["all"]["reference"]
        out["pedal_f1"] = pedal["all"]["f1"]
    else:
        out["pedal_tp"] = out["pedal_predicted"] = out["pedal_reference"] = 0
        out["pedal_f1"] = None
    out["coverage_reference_events_total"] = metrics["coverage"]["reference_events_total"]
    out["coverage_reference_events_reliably_aligned"] = metrics["coverage"]["reference_events_reliably_aligned"]
    out["coverage_system_events_total"] = metrics["coverage"]["system_events_total"]
    out["coverage_system_events_outside_alignment_span"] = metrics["coverage"]["system_events_outside_alignment_span"]
    return out


# 报告的标量指标；("f1" 类由 tp/predicted/reference 微平均重算，"rate" 类由
# correct/matched 微平均重算，两者的宏平均都直接取逐行标量的算术平均)。
F1_LIKE = {
    "pitch_f1": ("pitch_tp", "pitch_predicted", "pitch_reference"),
    "onset_f1": ("onset_tp", "onset_predicted", "onset_reference"),
    "note_f1": ("note_tp", "note_predicted", "note_reference"),
    "pedal_f1": ("pedal_tp", "pedal_predicted", "pedal_reference"),
}
RATE_LIKE = {
    "duration_accuracy": ("duration_correct_events", "duration_matched_events"),
    "tie_accuracy": ("tie_correct_events", "tie_matched_events"),
    "voice_accuracy": ("voice_correct_events", "voice_matched_events"),
}
MACRO_SCALAR_FIELDS = tuple(F1_LIKE) + tuple(RATE_LIKE) + ("duration_mae_ql",)


def piece_level_rows(rows: list[dict]) -> list[dict]:
    """先按曲目对同曲多演奏取平均，再暴露给宏平均/分布/bootstrap；避免演奏数不均的曲目
    在演奏级平均中获得不成比例的权重。"""
    by_piece_pipeline: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_piece_pipeline[(row["piece_key"], row["pipeline"])].append(row)
    piece_rows = []
    for (piece_key, pipeline), group in by_piece_pipeline.items():
        piece_row = {"piece_key": piece_key, "pipeline": pipeline, "performance_count": len(group)}
        for field in MACRO_SCALAR_FIELDS:
            values = [item[field] for item in group if item.get(field) is not None]
            piece_row[field] = statistics.fmean(values) if values else None
        piece_rows.append(piece_row)
    return piece_rows


def macro_average(piece_rows: list[dict], pipeline: str) -> dict:
    group = [row for row in piece_rows if row["pipeline"] == pipeline]
    out = {"pipeline": pipeline, "piece_count": len(group)}
    for field in MACRO_SCALAR_FIELDS:
        values = [row[field] for row in group if row.get(field) is not None]
        out[field] = statistics.fmean(values) if values else None
    return out


def micro_average(rows: list[dict], pipeline: str) -> dict:
    """事件级微平均：跨所有演奏累加 tp/predicted/reference 或 correct/matched 后重算。"""
    group = [row for row in rows if row["pipeline"] == pipeline]
    out = {"pipeline": pipeline, "performance_count": len(group)}
    for name, (tp_field, predicted_field, reference_field) in F1_LIKE.items():
        tp = sum(row[tp_field] for row in group)
        predicted = sum(row[predicted_field] for row in group)
        reference = sum(row[reference_field] for row in group)
        precision = tp / predicted if predicted else None
        recall = tp / reference if reference else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0 if (predicted or reference) else None
        out[name] = {"tp": tp, "predicted": predicted, "reference": reference, "precision": precision,
                     "recall": recall, "f1": f1}
    for name, (correct_field, matched_field) in RATE_LIKE.items():
        correct = sum(row[correct_field] for row in group)
        matched = sum(row[matched_field] for row in group)
        out[name] = {"correct": correct, "matched": matched, "accuracy": correct / matched if matched else None}
    return out


def distribution(piece_rows: list[dict], pipeline: str, field: str) -> dict:
    values = sorted(row[field] for row in piece_rows if row["pipeline"] == pipeline and row.get(field) is not None)
    if not values:
        return {"n": 0, "median": None, "q1": None, "q3": None, "min": None, "max": None}
    quantiles = statistics.quantiles(values, n=4, method="inclusive") if len(values) >= 2 else [values[0], values[0], values[0]]
    return {
        "n": len(values),
        "median": statistics.median(values),
        "q1": quantiles[0],
        "q3": quantiles[2],
        "min": values[0],
        "max": values[-1],
    }


def metric_row(metrics_record: dict) -> dict:
    """从已完成的逐项证据恢复一行汇总输入，避免重新评分或重写历史指标。"""
    return {
        "piece_key": metrics_record["piece_key"],
        "midi_performance": metrics_record["midi_performance"],
        "pipeline": metrics_record["pipeline"],
        **flatten_metrics(metrics_record["score"]),
    }


def p4l_load_is_logged(commands_log_text: str, xml_path: Path) -> bool:
    """确认该 P4-L 导出在审计日志中明确报告加载了冻结 LightGBM 模型。"""
    path_text = str(xml_path)
    command_index = commands_log_text.rfind(path_text)
    if command_index < 0:
        return False
    next_command = commands_log_text.find('\n[', command_index + len(path_text))
    evidence = commands_log_text[command_index: next_command if next_command >= 0 else None]
    return "评分=LightGBM：" in evidence and "候选模型不可用，回退规则评分" not in evidence


def bootstrap_pair_ci(piece_rows: list[dict], field: str, pipeline_a: str, pipeline_b: str,
                      n_boot: int, rng: random.Random) -> dict | None:
    """对 pipeline_a - pipeline_b 的曲目级均值差做逐曲目配对 bootstrap，报告 95% 分位 CI。"""
    by_piece: dict[str, dict[str, float]] = defaultdict(dict)
    for row in piece_rows:
        if row["pipeline"] in (pipeline_a, pipeline_b) and row.get(field) is not None:
            by_piece[row["piece_key"]][row["pipeline"]] = row[field]
    paired = [(values[pipeline_a], values[pipeline_b]) for values in by_piece.values()
             if pipeline_a in values and pipeline_b in values]
    if not paired:
        return None
    observed_diff = statistics.fmean(a - b for a, b in paired)
    diffs = []
    n = len(paired)
    for _ in range(n_boot):
        sample = [paired[rng.randrange(n)] for _ in range(n)]
        diffs.append(statistics.fmean(a - b for a, b in sample))
    diffs.sort()
    lower = diffs[int(0.025 * n_boot)]
    upper = diffs[min(int(0.975 * n_boot), n_boot - 1)]
    return {
        "field": field, "pipeline_a": pipeline_a, "pipeline_b": pipeline_b,
        "paired_piece_count": n, "observed_mean_diff": observed_diff,
        "bootstrap_iterations": n_boot, "ci95_lower": lower, "ci95_upper": upper,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="C 阶段：冻结 ASAP test 集相对参考谱系统级评测")
    parser.add_argument("--asap-root", required=True, help="ASAP 数据集根目录（含 metadata.csv）")
    parser.add_argument("--manifest", required=True, help="asap_piece_manifest.csv 路径")
    parser.add_argument("--batch-summary", required=True,
                        help="含已生成对齐 CSV 路径的 batch_summary.csv（复用，不重新生成）")
    parser.add_argument("--candidate-model", required=True, help="P4-L 模型前缀（不带 .txt/.json）")
    parser.add_argument("--run-dir", required=True, help="独立运行目录；不得覆盖历史实验")
    parser.add_argument("--max-voices", type=int, default=12)
    parser.add_argument("--divisors", default="8,4,3")
    parser.add_argument("--onset-tol", type=float, default=0.125)
    parser.add_argument("--dur-tol", type=float, default=0.25)
    parser.add_argument("--pedal-tol", type=float, default=0.25)
    parser.add_argument("--bootstrap-iterations", type=int, default=1000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260817)
    parser.add_argument("--limit", type=int, default=None,
                        help="仅调试用：限制处理的演奏行数；正式锁定报告必须省略此参数")
    parser.add_argument("--resume", action="store_true",
                        help="只恢复经配置与冻结资产核验的中止运行目录；不得改变任何实验参数")
    parser.add_argument("--only", action="append", default=None,
                        help="仅运行指定的 midi_performance（可重复传入）；用于隔离大曲目并非正式统计参数")
    args = parser.parse_args()

    asap_root = Path(args.asap_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    batch_summary_path = Path(args.batch_summary).resolve()
    model_prefix = Path(args.candidate_model).resolve()
    model_files = {model_prefix.with_suffix(".txt"): "p4_asap_cross_piece_v1.txt",
                  model_prefix.with_suffix(".json"): "p4_asap_cross_piece_v1.json"}
    run_dir = Path(args.run_dir).resolve()

    if run_dir.exists() and any(run_dir.iterdir()) and not args.resume:
        parser.error(f"运行目录已存在且非空，拒绝覆盖历史证据：{run_dir}；如需恢复必须显式传入 --resume")
    if args.resume and args.limit is not None:
        parser.error("--resume 不允许与 --limit 同用，避免把调试子集误写入冻结证据包")
    if args.only and not args.resume:
        parser.error("--only 只允许与 --resume 同用，避免在新目录中生成非完整冻结证据包")
    if not manifest_path.is_file():
        parser.error(f"manifest 不存在：{manifest_path}")
    if not batch_summary_path.is_file():
        parser.error(f"batch_summary 不存在：{batch_summary_path}")
    for path, canonical_name in model_files.items():
        if not path.is_file():
            parser.error(f"P4-L 模型文件缺失：{path}")
        actual = sha256(path)
        expected = EXPECTED_MODEL_SHA256[canonical_name]
        if actual != expected:
            parser.error(
                f"P4-L 模型哈希与 B 阶段冻结记录不一致（{path.name}）："
                f"expected={expected} actual={actual}；拒绝在 test 集上使用可能被重新训练或调参污染的模型"
            )

    test_rows = load_test_rows(manifest_path)
    full_test_rows = list(test_rows)
    if not test_rows:
        parser.error("manifest 中未找到 split == test 的行")
    if len(test_rows) != 120:
        parser.error(f"冻结 test 集应为 120 条演奏，实际读取到 {len(test_rows)} 条；拒绝在非冻结集合上运行")
    alignment_index = load_alignment_index(batch_summary_path)
    missing_alignment = [row["midi_performance"] for row in test_rows if row["midi_performance"] not in alignment_index]
    if missing_alignment:
        parser.error(f"以下 test 演奏在 batch_summary 中找不到已生成的对齐 CSV：{missing_alignment[:5]}")
    for row in test_rows:
        entry = alignment_index[row["midi_performance"]]
        if entry["status"] != "ok" or not Path(entry["alignment_csv"]).is_file():
            parser.error(f"演奏 {row['midi_performance']} 的对齐资产状态异常：{entry.get('status')}")

    if args.limit is not None:
        test_rows = test_rows[: args.limit]
    if args.only:
        requested = set(args.only)
        test_rows = [row for row in test_rows if row["midi_performance"] in requested]
        missing_only = requested - {row["midi_performance"] for row in test_rows}
        if missing_only:
            parser.error(f"--only 中的演奏不在冻结 test 集：{sorted(missing_only)}")

    scripts_dir = Path(__file__).resolve().parent
    resume_completed: dict[tuple[str, str], dict] = {}
    if args.resume:
        config_path = run_dir / "config.json"
        frozen_manifest_path = run_dir / "manifest" / "frozen_test_manifest.csv"
        model_checksums_path = run_dir / "models" / "checksums.sha256"
        commands_log = run_dir / "commands.log"
        required = (config_path, frozen_manifest_path, model_checksums_path, commands_log)
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            parser.error(f"--resume 缺少可核验的既有证据文件：{missing}")
        try:
            prior_config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"--resume 无法读取既有 config.json：{exc}")
        expected_config = {
            "schema_version": "C-stage-eval-v1",
            "frozen_test_performance_count": len(full_test_rows),
            "frozen_test_piece_count": len(set(row["piece_key"] for row in full_test_rows)),
            "frozen_test_manifest_sha256": sha256(frozen_manifest_path),
            "divisors": args.divisors,
            "max_voices": args.max_voices,
            "onset_tolerance_ql": args.onset_tol,
            "duration_tolerance_ql": args.dur_tol,
            "pedal_tolerance_ql": args.pedal_tol,
            "bootstrap_iterations": args.bootstrap_iterations,
            "bootstrap_seed": args.bootstrap_seed,
            "candidate_model_files": {name: sha256(path) for path, name in model_files.items()},
        }
        mismatches = {
            key: {"prior": prior_config.get(key), "expected": value}
            for key, value in expected_config.items() if prior_config.get(key) != value
        }
        if mismatches:
            parser.error(f"--resume 的冻结配置不匹配，拒绝混合证据：{json.dumps(mismatches, ensure_ascii=False)}")
        frozen_rows = load_test_rows(frozen_manifest_path)
        expected_frozen_rows = [
            {**row, "alignment_csv": alignment_index[row["midi_performance"]]["alignment_csv"]}
            for row in full_test_rows
        ]
        if frozen_rows != expected_frozen_rows:
            parser.error("--resume 的冻结 manifest 行与当前输入 manifest/对齐资产不一致，拒绝继续")
        expected_model_checksums = "\n".join(
            f"{sha256(model_prefix.with_suffix('.' + name.rsplit('.', 1)[1]))}  {name}"
            for name in model_files.values()
        ) + "\n"
        if model_checksums_path.read_text(encoding="utf-8") != expected_model_checksums:
            parser.error("--resume 的模型副本校验和与当前冻结模型不一致，拒绝继续")
        expected_pairs = {(row["midi_performance"], pipeline) for row in full_test_rows for pipeline in PIPELINES}
        commands_log_text = commands_log.read_text(encoding="utf-8")
        for metrics_path in sorted((run_dir / "pieces").glob("*/*/metrics.json")):
            try:
                record = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                parser.error(f"--resume 发现不可读取的 metrics.json：{metrics_path}: {exc}")
            key = (record.get("midi_performance"), record.get("pipeline"))
            if key not in expected_pairs:
                parser.error(f"--resume 发现不属于当前冻结 test 集的指标：{metrics_path}")
            if record.get("status") == "completed":
                if key in resume_completed or not isinstance(record.get("score"), dict):
                    parser.error(f"--resume 发现重复或不完整的 completed 指标：{metrics_path}")
                xml_path = metrics_path.parent / "output.musicxml"
                if not xml_path.is_file():
                    parser.error(f"--resume completed 指标缺少 MusicXML：{metrics_path}")
                if record.get("pipeline") == "P4-L" and not p4l_load_is_logged(
                        commands_log_text, xml_path):
                    parser.error(f"--resume 无法在 commands.log 中确认 P4-L 已加载 LightGBM：{metrics_path}")
                resume_completed[key] = record
            else:
                metrics_path.unlink()
                output_path = metrics_path.parent / "output.musicxml"
                if output_path.is_file():
                    output_path.unlink()
        prior_config["resume_count"] = int(prior_config.get("resume_count", 0)) + 1
        prior_config["last_resumed_at_utc"] = datetime.now(timezone.utc).isoformat()
        prior_config["resumed_completed_pipeline_runs"] = len(resume_completed)
        write_json(config_path, prior_config)

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir = run_dir / "manifest"
    models_dir = run_dir / "models"
    pieces_dir = run_dir / "pieces"
    summary_dir = run_dir / "summary"
    commands_log = run_dir / "commands.log"
    if args.resume:
        print(f"已核验中止证据包；将复用 {len(resume_completed)} 个已完成 (演奏, 系统) 指标")
    else:
        manifest_dir.mkdir()
        models_dir.mkdir()
    if not args.resume:
        frozen_manifest_rows = [
            {**row, "alignment_csv": alignment_index[row["midi_performance"]]["alignment_csv"]}
            for row in test_rows
        ]
        with (manifest_dir / "frozen_test_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(frozen_manifest_rows[0]))
            writer.writeheader()
            writer.writerows(frozen_manifest_rows)
        (manifest_dir / "frozen_test_manifest.sha256").write_text(
            sha256(manifest_dir / "frozen_test_manifest.csv") + "  frozen_test_manifest.csv\n", encoding="utf-8"
        )
        for source, canonical_name in model_files.items():
            (models_dir / canonical_name).write_bytes(source.read_bytes())
        (models_dir / "checksums.sha256").write_text(
            "\n".join(f"{sha256(models_dir / name)}  {name}" for name in model_files.values()) + "\n",
            encoding="utf-8",
        )
        config = {
            "schema_version": "C-stage-eval-v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "pipelines": list(PIPELINES),
            "frozen_test_performance_count": len(full_test_rows),
            "frozen_test_piece_count": len(set(row["piece_key"] for row in full_test_rows)),
            "asap_root": str(asap_root),
            "manifest_source": str(manifest_path),
            "batch_summary_source": str(batch_summary_path),
            "frozen_test_manifest_sha256": sha256(manifest_dir / "frozen_test_manifest.csv"),
            "divisors": args.divisors,
            "max_voices": args.max_voices,
            "onset_tolerance_ql": args.onset_tol,
            "duration_tolerance_ql": args.dur_tol,
            "pedal_tolerance_ql": args.pedal_tol,
            "bootstrap_iterations": args.bootstrap_iterations,
            "bootstrap_seed": args.bootstrap_seed,
            "candidate_model_prefix": str(model_prefix),
            "candidate_model_files": {name: sha256(models_dir / name) for name in model_files.values()},
            "note": (
                "本运行只评估相对参考谱的符号一致性（pitch/onset/duration/note/tie-chain/"
                "voice-consistency/pedal），不涉及 B 阶段导出忠实性，也不能替代候选级排序指标"
                "（历史 LightGBM ROC-AUC/AP/Top-1）关于整谱可读性的结论。"
            ),
        }
        write_json(run_dir / "config.json", config)
        (run_dir / "environment.txt").write_text(
            f"python={sys.version}\nplatform={platform.platform()}\n", encoding="utf-8"
        )

    rows: list[dict] = []
    failures: list[dict] = []
    for row in test_rows:
        piece_key = row["piece_key"]
        performance_id = safe_id(row["midi_performance"])
        midi_path = asap_root / row["midi_performance"]
        xml_reference_path = asap_root / row["xml_score"]
        alignment_csv = Path(alignment_index[row["midi_performance"]]["alignment_csv"])
        if not midi_path.is_file():
            failures.append({"piece_key": piece_key, "midi_performance": row["midi_performance"],
                             "pipeline": None, "reason": f"MIDI 不存在：{midi_path}"})
            continue
        if not xml_reference_path.is_file():
            failures.append({"piece_key": piece_key, "midi_performance": row["midi_performance"],
                             "pipeline": None, "reason": f"参考 MusicXML 不存在：{xml_reference_path}"})
            continue

        for pipeline in PIPELINES:
            resumed = resume_completed.get((row["midi_performance"], pipeline))
            if resumed is not None:
                rows.append(metric_row(resumed))
                continue
            out_dir = pieces_dir / piece_key.replace("\x1f", "__") / performance_id / pipeline
            out_dir.mkdir(parents=True, exist_ok=True)
            xml_path = out_dir / "output.musicxml"
            title = f"{pipeline} C-stage: {performance_id}"
            command = export_command(pipeline, midi_path, xml_path, title, args.divisors,
                                     args.max_voices, model_prefix if pipeline == "P4-L" else None, scripts_dir)
            export_result = run_command(command, commands_log)
            metrics_record = {
                "schema_version": "C-stage-piece-v1",
                "piece_key": piece_key,
                "midi_performance": row["midi_performance"],
                "pipeline": pipeline,
                "midi_sha256": sha256(midi_path),
                "alignment_csv": str(alignment_csv),
                "export_command": command,
                "export_returncode": export_result.returncode,
            }
            if pipeline == "P4-L" and (
                    "评分=LightGBM：" not in export_result.stdout
                    or "候选模型不可用，回退规则评分" in export_result.stdout + export_result.stderr):
                metrics_record["status"] = "candidate_model_not_loaded"
                metrics_record["export_stdout"] = export_result.stdout
                metrics_record["export_stderr"] = export_result.stderr
                write_json(out_dir / "metrics.json", metrics_record)
                failures.append({"piece_key": piece_key, "midi_performance": row["midi_performance"],
                                 "pipeline": pipeline, "reason": "P4-L 未确认加载冻结 LightGBM 模型"})
                continue
            if export_result.returncode != 0 or not xml_path.is_file():
                metrics_record["status"] = "export_failed"
                metrics_record["export_stderr"] = export_result.stderr
                write_json(out_dir / "metrics.json", metrics_record)
                failures.append({"piece_key": piece_key, "midi_performance": row["midi_performance"],
                                 "pipeline": pipeline, "reason": "MusicXML 导出失败"})
                continue
            try:
                score = evaluate_score(xml_path, xml_reference_path, alignment_csv,
                                       onset_tolerance=args.onset_tol, duration_tolerance=args.dur_tol,
                                       pedal_tolerance=args.pedal_tol)
            except Exception as exc:  # 结构化记录失败，批处理不静默丢项。
                metrics_record["status"] = "scoring_failed"
                metrics_record["scoring_error"] = str(exc)
                write_json(out_dir / "metrics.json", metrics_record)
                failures.append({"piece_key": piece_key, "midi_performance": row["midi_performance"],
                                 "pipeline": pipeline, "reason": f"评分失败：{exc}"})
                continue
            metrics_record["status"] = "completed"
            metrics_record["score"] = score
            write_json(out_dir / "metrics.json", metrics_record)
            rows.append({"piece_key": piece_key, "midi_performance": row["midi_performance"],
                        "pipeline": pipeline, **flatten_metrics(score)})
        print(f"完成 {performance_id}（{piece_key}）× {len(PIPELINES)} 系统")

    if not rows:
        parser.error("没有任何 (演奏, 系统) 组合成功产出评分结果")

    summary_dir.mkdir(parents=True, exist_ok=True)
    performance_fields = list(rows[0])
    with (summary_dir / "performance_level.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=performance_fields)
        writer.writeheader()
        writer.writerows(rows)

    piece_rows = piece_level_rows(rows)
    piece_fields = list(piece_rows[0])
    with (summary_dir / "piece_level.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=piece_fields)
        writer.writeheader()
        writer.writerows(piece_rows)

    macro = {pipeline: macro_average(piece_rows, pipeline) for pipeline in PIPELINES}
    micro = {pipeline: micro_average(rows, pipeline) for pipeline in PIPELINES}
    dist_fields = ("note_f1", "onset_f1", "pitch_f1", "duration_accuracy", "tie_accuracy",
                  "voice_accuracy", "pedal_f1")
    distributions = {
        pipeline: {field: distribution(piece_rows, pipeline, field) for field in dist_fields}
        for pipeline in PIPELINES
    }

    rng = random.Random(args.bootstrap_seed)
    bootstrap_ci = []
    pipeline_pairs = (("P4-L", "P4-R"), ("P4-L", "P3"), ("P4-R", "P3"))
    for field in dist_fields:
        for pipeline_a, pipeline_b in pipeline_pairs:
            result = bootstrap_pair_ci(piece_rows, field, pipeline_a, pipeline_b,
                                       args.bootstrap_iterations, rng)
            if result is not None:
                bootstrap_ci.append(result)

    failed_performance_ids = {item["midi_performance"] for item in failures}
    aggregate_summary = {
        "schema_version": "C-stage-summary-v1",
        "frozen_test_performance_count": len(test_rows),
        "frozen_test_piece_count": len(set(row["piece_key"] for row in test_rows)),
        "performances_with_at_least_one_pipeline_failure": len(failed_performance_ids),
        "total_pipeline_run_failures": len(failures),
        "macro_average_by_piece": macro,
        "micro_average_by_event": micro,
        "piece_level_distribution": distributions,
        "bootstrap_pairwise_mean_diff_ci95": bootstrap_ci,
        "interpretation_boundaries": [
            "本表报告的是 P3/P4-R/P4-L 导出的 MusicXML 相对冻结 ASAP test 参考谱的符号一致性，"
            "不是导出忠实性（该结论属于 B 阶段 evals/B/regression_gate_20260816*，评估对象是"
            "MIDI 量化输入到 XML 输出的对账，不涉及参考谱）。",
            "本表的 P4-L 与 P4-R 差异反映的是候选评分函数在改变整谱声部/时值决策后对参考谱的"
            "接近程度，不能与历史候选级 ROC-AUC=0.868960/AP=0.857762/Top-1=0.738746（vs 规则 "
            "Top-1=0.625078）直接换算或相加；候选级指标衡量的是排序质量，本表衡量的是最终整谱"
            "输出与参考谱的符号一致性，两者不是同一统计量。",
            "B 阶段三曲（mozart_k4/scarlatti_k79/schubert_d979）生产回归集的结果不能替代本表；"
            "本表使用的是 31 首作品、120 条演奏的冻结 ASAP test 集，是唯一可用于泛化性结论的样本。",
            "test 集在本次运行中只使用一次；任何指标不理想都不应引发针对 test 集的再次调参，"
            "调参必须回到 train/valid 集合后再重新走完整个 B/C 阶段协议。",
        ],
    }
    write_json(summary_dir / "aggregate_summary.json", aggregate_summary)
    if failures:
        with (summary_dir / "failures.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(failures[0]))
            writer.writeheader()
            writer.writerows(failures)

    print(
        f"C 阶段冻结评测完成：{len(rows)} 个 (演奏,系统) 评分成功，{len(failures)} 个失败；"
        f"运行目录：{run_dir}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
