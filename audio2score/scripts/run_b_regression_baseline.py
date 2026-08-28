#!/usr/bin/env python3
"""执行 B 阶段三曲 × 三系统冻结回归，并写入完整运行元数据。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PIECES = ("mozart_k4", "scarlatti_k79", "schubert_d979")
PIPELINES = ("P3", "P4-R", "P4-L")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(command: list[str], log: Path) -> None:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(command, ensure_ascii=False) + f"\texit={result.returncode}\n")
        if result.stdout:
            handle.write("STDOUT\n" + result.stdout)
        if result.stderr:
            handle.write("STDERR\n" + result.stderr)
    if result.returncode:
        raise RuntimeError(f"命令失败（exit={result.returncode}）：{' '.join(command)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 B 阶段三曲回归基线证据包")
    parser.add_argument("--inputs-dir", required=True, help="冻结 MIDI 所在目录")
    parser.add_argument("--candidate-model", required=True, help="P4-L 模型前缀（不带 .txt/.json）")
    parser.add_argument("--run-dir", required=True, help="独立运行目录；不得覆盖历史实验")
    parser.add_argument("--max-voices", type=int, default=12)
    parser.add_argument("--divisors", default="8,4,3")
    parser.add_argument("--onset-tol", type=float, default=0.125)
    parser.add_argument("--dur-tol", type=float, default=0.25)
    args = parser.parse_args()

    inputs_dir = Path(args.inputs_dir).resolve()
    model_prefix = Path(args.candidate_model).resolve()
    model_files = (model_prefix.with_suffix(".txt"), model_prefix.with_suffix(".json"))
    run_dir = Path(args.run_dir).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        parser.error(f"运行目录已存在且非空，拒绝覆盖历史证据：{run_dir}")
    if not all(path.is_file() for path in model_files):
        parser.error("P4-L 模型 .txt/.json 文件不完整")

    scripts_dir = Path(__file__).resolve().parent
    runner = scripts_dir / "run_piece_baseline.py"
    summarizer = scripts_dir / "summarize_baselines.py"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir = run_dir / "manifest"
    manifest_dir.mkdir()
    models_dir = run_dir / "models"
    models_dir.mkdir()
    commands_log = run_dir / "commands.log"

    rows = []
    for piece_id in PIECES:
        midi_path = inputs_dir / f"{piece_id}_source.mid"
        if not midi_path.is_file():
            parser.error(f"缺少冻结回归 MIDI：{midi_path}")
        rows.append({"piece_id": piece_id, "midi_path": str(midi_path), "midi_sha256": sha256(midi_path)})
    with (manifest_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (manifest_dir / "manifest.sha256").write_text(
        sha256(manifest_dir / "manifest.csv") + "  manifest.csv\n", encoding="utf-8"
    )
    checksums = []
    for source in model_files:
        target = models_dir / source.name
        shutil.copy2(source, target)
        checksums.append(f"{sha256(target)}  {target.name}")
    (models_dir / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    config = {
        "schema_version": "B-regression-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipelines": list(PIPELINES),
        "inputs_manifest": "manifest/manifest.csv",
        "inputs_manifest_sha256": sha256(manifest_dir / "manifest.csv"),
        "divisors": args.divisors,
        "onset_tolerance_ql": args.onset_tol,
        "duration_tolerance_ql": args.dur_tol,
        "max_voices": args.max_voices,
        "candidate_model_prefix": str(model_prefix),
        "candidate_model_files": {path.name: sha256(path) for path in model_files},
    }
    write_json(run_dir / "config.json", config)
    (run_dir / "environment.txt").write_text(
        f"python={sys.version}\nplatform={platform.platform()}\n", encoding="utf-8"
    )

    for row in rows:
        for pipeline in PIPELINES:
            command = [
                sys.executable, str(runner), "--pipeline", pipeline,
                "--midi", row["midi_path"],
                "--out-dir", str(run_dir / "pieces" / row["piece_id"] / pipeline),
                "--max-voices", str(args.max_voices), "--divisors", args.divisors,
                "--onset-tol", str(args.onset_tol), "--dur-tol", str(args.dur_tol),
            ]
            if pipeline == "P4-L":
                command.extend(["--candidate-model", str(model_prefix)])
            run_command(command, commands_log)
    run_command(
        [sys.executable, str(summarizer), "--pieces-dir", str(run_dir / "pieces"),
         "--out-dir", str(run_dir / "summary")],
        commands_log,
    )
    print(f"B 阶段三曲回归完成：{run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
