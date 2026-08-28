#!/usr/bin/env python3
"""B 阶段单曲 MIDI→MusicXML 基线运行器。

将既有 P3 / P4-R / P4-L 导出器编排为同一份可追溯的单曲证据包：
导出、同配置 MIDI↔MusicXML 对账、Verovio 渲染、XML/延音线/小节结构 QA，
以及机器可读的 ``metrics.json``。本脚本不实现或修改任何记谱决策。

示例：
    python3 run_piece_baseline.py --pipeline P4-L --midi input.mid \
      --out-dir evals/B/demo/pieces/example/P4-L \
      --candidate-model ../models/p4_asap_cross_piece_v1 --max-voices 12
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from reconcile_midi_xml import (
    notation_input_notes,
    p4_notation_input_notes,
    reconcile,
    xml_real_events,
)

STEP_SEMIS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_result(command: list[str], stderr_path: Path) -> dict:
    """执行一条子命令，并将 stderr 原样固定到实验目录。"""
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _pitch_midi(pitch_el: ET.Element | None) -> int | None:
    if pitch_el is None:
        return None
    step = pitch_el.findtext("step")
    octave = pitch_el.findtext("octave")
    if step not in STEP_SEMIS or octave is None:
        return None
    return (int(octave) + 1) * 12 + STEP_SEMIS[step] + int(pitch_el.findtext("alter") or 0)


def inspect_musicxml(xml_path: Path) -> dict:
    """结构化检查 XML 解析、小节游标和按 voice 隔离的 tie 链。"""
    qa = {
        "xml_parse_success": False,
        "part_count": 0,
        "measure_count": 0,
        "overfull_measure_count": 0,
        "overfull_measures": [],
        "tie_orphan_stop_count": 0,
        "tie_unclosed_start_count": 0,
        "tie_cross_voice_count": 0,
        "tie_complete": False,
    }
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError) as exc:
        qa["parse_error"] = str(exc)
        return qa

    qa["xml_parse_success"] = True
    parts = list(root.findall("part"))
    qa["part_count"] = len(parts)
    open_ties: dict[tuple[str, str, int], bool] = {}
    open_by_part_pitch: dict[tuple[str, int], set[str]] = {}

    for part_index, part in enumerate(parts):
        part_id = part.get("id") or str(part_index)
        divisions = None
        bar_ql = 4.0
        for measure in part.findall("measure"):
            qa["measure_count"] += 1
            measure_no = measure.get("number") or "?"
            cursor = 0.0
            max_cursor = 0.0
            for child in measure:
                if child.tag == "attributes":
                    divisions_text = child.findtext("divisions")
                    if divisions_text:
                        divisions = int(divisions_text)
                    beats = child.findtext("time/beats")
                    beat_type = child.findtext("time/beat-type")
                    if beats and beat_type:
                        bar_ql = 4.0 * float(beats) / float(beat_type)
                    continue
                if divisions is None:
                    continue
                if child.tag == "backup":
                    cursor -= int(child.findtext("duration") or 0) / divisions
                    continue
                if child.tag == "forward":
                    cursor += int(child.findtext("duration") or 0) / divisions
                    max_cursor = max(max_cursor, cursor)
                    continue
                if child.tag != "note":
                    continue

                raw = int(child.findtext("duration") or 0) / divisions
                chord_member = child.find("chord") is not None
                if not chord_member:
                    cursor += raw
                    max_cursor = max(max_cursor, cursor)
                pitch = _pitch_midi(child.find("pitch"))
                if pitch is None:
                    continue
                voice = child.findtext("voice") or "1"
                stream = (part_id, voice, pitch)
                coarse_stream = (part_id, pitch)
                tie_types = {tie.get("type") for tie in child.findall("tie")}
                if "stop" in tie_types:
                    if stream not in open_ties:
                        qa["tie_orphan_stop_count"] += 1
                    elif "start" not in tie_types:
                        del open_ties[stream]
                        voices = open_by_part_pitch.get(coarse_stream, set())
                        voices.discard(voice)
                        if voices:
                            open_by_part_pitch[coarse_stream] = voices
                        else:
                            open_by_part_pitch.pop(coarse_stream, None)
                if "start" in tie_types:
                    existing_voices = open_by_part_pitch.get(coarse_stream, set())
                    if existing_voices and voice not in existing_voices and "stop" in tie_types:
                        qa["tie_cross_voice_count"] += 1
                    open_ties[stream] = True
                    open_by_part_pitch.setdefault(coarse_stream, set()).add(voice)
            if max_cursor > bar_ql + 1e-6:
                qa["overfull_measure_count"] += 1
                qa["overfull_measures"].append({
                    "part_id": part_id,
                    "measure": measure_no,
                    "cursor_ql": round(max_cursor, 9),
                    "bar_ql": bar_ql,
                })
    qa["tie_unclosed_start_count"] = len(open_ties)
    qa["tie_complete"] = not any(
        qa[key] for key in ("tie_orphan_stop_count", "tie_unclosed_start_count", "tie_cross_voice_count")
    )
    return qa


def reconcile_to_json(args: argparse.Namespace, xml_path: Path) -> dict:
    divisors = tuple(int(item) for item in args.divisors.split(","))
    feature_scorer = None
    reference = "notation"
    if args.pipeline in {"P4-R", "P4-L"}:
        reference = "p4"
        if args.pipeline == "P4-L":
            from train_candidate_model import probability_from_model
            feature_scorer = probability_from_model(args.candidate_model)
            if getattr(feature_scorer, "score_features", None) is None:
                raise RuntimeError(f"P4-L 对账无法加载候选模型：{args.candidate_model}")
        input_events = p4_notation_input_notes(
            args.midi, divisors=divisors, max_voices=args.max_voices,
            feature_scorer=feature_scorer,
        )
    else:
        input_events = notation_input_notes(args.midi, divisors=divisors)
    output_events = xml_real_events(str(xml_path))
    extra, missing, onset_diffs, duration_diffs = reconcile(
        input_events, output_events, onset_tol=args.onset_tol, dur_tol=args.dur_tol,
    )
    return {
        "reference": reference,
        "input_event_count": len(input_events),
        "xml_tie_merged_event_count": len(output_events),
        "onset_tolerance_ql": args.onset_tol,
        "duration_tolerance_ql": args.dur_tol,
        "extra_count": len(extra),
        "missing_count": len(missing),
        "onset_drift_count": len(onset_diffs),
        "duration_drift_count": len(duration_diffs),
        "extra_examples": extra[:12],
        "missing_examples": missing[:12],
        "onset_drift_examples": onset_diffs[:12],
        "duration_drift_examples": duration_diffs[:12],
        "export_fidelity_pass": not extra and not missing,
    }


def warning_counts(stderr: str) -> dict:
    """从 Verovio stderr 提取告警数，而非只统计告警文本出现行数。"""
    import re

    lower = stderr.lower()
    tie_counts = [int(item) for item in re.findall(r"there are\s+(\d+)\s+ties left open", lower)]
    return {
        "ties_left_open": sum(tie_counts),
        "unclosed": lower.count("unclosed"),
        # 每条 Verovio 告警只计一次；例如 mixed beam 文本同时含 beam 和 space。
        "beam_or_layout": sum(
            1 for line in lower.splitlines()
            if "insufficient space" in line or "mixed beam" in line or "layout" in line
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行单曲 P3/P4 统一基线并写入结构化证据包")
    parser.add_argument("--pipeline", choices=("P3", "P4-R", "P4-L"), required=True)
    parser.add_argument("--midi", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--candidate-model")
    parser.add_argument("--max-voices", type=int, default=12)
    parser.add_argument("--divisors", default="8,4,3")
    parser.add_argument("--onset-tol", type=float, default=0.125)
    parser.add_argument("--dur-tol", type=float, default=0.25)
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    if args.pipeline == "P4-L" and not args.candidate_model:
        parser.error("P4-L 必须提供 --candidate-model")
    if args.pipeline != "P4-L" and args.candidate_model:
        parser.error("仅 P4-L 可提供 --candidate-model，防止基线身份混淆")

    midi_path = Path(args.midi).resolve()
    if not midi_path.is_file():
        parser.error(f"输入 MIDI 不存在：{midi_path}")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    render_dir = out_dir / "render"
    render_dir.mkdir(exist_ok=True)
    xml_path = out_dir / "output.musicxml"
    scripts_dir = Path(__file__).resolve().parent
    title = args.title or f"{args.pipeline} baseline: {midi_path.stem}"

    if args.pipeline == "P3":
        export_command = [sys.executable, str(scripts_dir / "midi_to_score.py"),
                          "--midi", str(midi_path), "--out", str(xml_path),
                          "--title", title, "--divisors", args.divisors]
    else:
        export_command = [sys.executable, str(scripts_dir / "p4_multivoice_score.py"),
                          "--midi", str(midi_path), "--out", str(xml_path),
                          "--title", title, "--divisors", args.divisors,
                          "--max-voices", str(args.max_voices)]
        if args.pipeline == "P4-L":
            export_command.extend(["--candidate-model", str(Path(args.candidate_model).resolve())])

    commands_log = out_dir / "commands.log"
    started_at = datetime.now(timezone.utc).isoformat()
    export_result = _command_result(export_command, out_dir / "export.stderr.log")
    with commands_log.open("w", encoding="utf-8") as log:
        log.write("EXPORT\t" + json.dumps(export_result["command"], ensure_ascii=False) +
                  f"\texit={export_result['returncode']}\n")

    metrics = {
        "schema_version": "B-baseline-v1",
        "pipeline": args.pipeline,
        "input_midi": str(midi_path),
        "input_midi_sha256": _sha256(midi_path),
        "started_at_utc": started_at,
        "parameters": {
            "divisors": args.divisors,
            "onset_tolerance_ql": args.onset_tol,
            "duration_tolerance_ql": args.dur_tol,
            "max_voices": args.max_voices if args.pipeline != "P3" else None,
            "candidate_model": str(Path(args.candidate_model).resolve()) if args.candidate_model else None,
            "candidate_model_sha256": _sha256(Path(args.candidate_model).resolve().with_suffix(".txt"))
            if args.candidate_model else None,
        },
        "export": {key: export_result[key] for key in ("command", "returncode")},
        "status": "failed",
    }
    if export_result["returncode"] != 0 or not xml_path.is_file():
        metrics["failure_reason"] = "MusicXML 导出失败"
        _write_json(out_dir / "metrics.json", metrics)
        return 1

    try:
        reconciliation = reconcile_to_json(args, xml_path)
        _write_json(out_dir / "reconcile.json", reconciliation)
        xml_qa = inspect_musicxml(xml_path)
        render_command = [sys.executable, str(scripts_dir / "render_score.py"),
                          "--musicxml", str(xml_path),
                          "--out-svg", str(render_dir / "score.svg"),
                          "--out-png", str(render_dir / "score.png")]
        render_result = _command_result(render_command, out_dir / "render.stderr.log")
        with commands_log.open("a", encoding="utf-8") as log:
            log.write("RENDER\t" + json.dumps(render_result["command"], ensure_ascii=False) +
                      f"\texit={render_result['returncode']}\n")
        page_svgs = sorted(render_dir.glob("score-p*.svg"))
        render_qa = {
            **xml_qa,
            "render_returncode": render_result["returncode"],
            "render_success": render_result["returncode"] == 0 and bool(page_svgs) and (render_dir / "score.png").is_file(),
            "page_count": len(page_svgs),
            "warnings": warning_counts(render_result["stderr"]),
        }
        _write_json(out_dir / "render_qa.json", render_qa)
        metrics.update({"reconciliation": reconciliation, "render_qa": render_qa})
        # status 只表示运行是否完整完成；基线出现可预期的结构/布局缺陷时仍必须
        # 留在汇总中，不能伪装成运行失败后被批处理静默遗漏。
        metrics["status"] = "completed"
        metrics["acceptance_pass"] = (
            reconciliation["export_fidelity_pass"] and render_qa["xml_parse_success"] and
            render_qa["render_success"] and render_qa["overfull_measure_count"] == 0 and
            render_qa["tie_complete"] and render_qa["warnings"]["ties_left_open"] == 0
        )
        if not metrics["acceptance_pass"]:
            metrics["acceptance_note"] = "导出、结构 QA 或渲染验收存在未通过项；结果仍保留用于基线比较。"
    except Exception as exc:  # 保留结构化失败信息，使批处理不会静默丢项。
        traceback_text = traceback.format_exc()
        (out_dir / "runner.stderr.log").write_text(traceback_text, encoding="utf-8")
        metrics["failure_reason"] = str(exc)
    finally:
        metrics["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_json(out_dir / "metrics.json", metrics)

    print(
        f"{args.pipeline} | {midi_path.name} | {metrics['status']} | "
        f"验收={'通过' if metrics.get('acceptance_pass') else '待整改'} | {out_dir}"
    )
    return 0 if metrics["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
