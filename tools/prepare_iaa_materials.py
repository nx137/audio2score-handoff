#!/usr/bin/env python3
"""Prepare inter-annotator agreement (IAA) re-annotation materials.

Deterministic 8-segment sample (20% of the 40-segment gold standard):
8 composers, train/validation stratified (6 train + 2 validation), and
mixed ambiguity levels.

    Bach_Prelude_bwv_846_2                 low-ambiguity anchor (baroque)
    Haydn_Keyboard_Sonatas_6-1_18          low-ambiguity anchor (classical)
    Beethoven_Piano_Sonatas_16-1_73        typical (classical-romantic)
    Ravel_Miroirs_3_Une_Barque_181         typical (impressionist pedal)
    Prokofiev_Toccata_197                  typical (percussive pedal)
    Chopin_Scherzos_20_254                 high ambiguity (no_output_match=15)
    Schubert_Wanderer_fantasie_1189        high ambiguity (no_output_match=13)
    Liszt_Transcendental_Etudes_10_71      high ambiguity + dense pedal

For each sampled segment an iaa_<sid>.csv is written with the full left
information columns of events.csv and the six annotation columns blank.
The annotator fills the six columns (see IAA_ANNOTATION_GUIDE.md) using the
segment's performance_segment.mid (audio) and reference_score.musicxml
(published score).  READ-ONLY with respect to the gold standard: events.csv
is never modified.

Usage:
    python tools/prepare_iaa_materials.py [--out-dir .../iaa] [--copy-media]
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"

SAMPLE = [
    ("Bach_Prelude_bwv_846_2", "low-ambiguity anchor (baroque)"),
    ("Haydn_Keyboard_Sonatas_6-1_18", "low-ambiguity anchor (classical)"),
    ("Beethoven_Piano_Sonatas_16-1_73", "typical (classical-romantic)"),
    ("Ravel_Miroirs_3_Une_Barque_181", "typical (impressionist pedal)"),
    ("Prokofiev_Toccata_197", "typical (percussive pedal)"),
    ("Chopin_Scherzos_20_254", "high ambiguity (no_output_match=15)"),
    ("Schubert_Wanderer_fantasie_1189", "high ambiguity (no_output_match=13)"),
    ("Liszt_Transcendental_Etudes_10_71", "high ambiguity + dense pedal"),
]

ANNOT_COLS = [
    "acoustic_sustain", "performance_pedal_action", "published_score_pedal",
    "notation_decision", "review_class", "review_note",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(BASE / "iaa"))
    ap.add_argument("--copy-media", action="store_true",
                    help="copy performance_segment.mid + reference_score.musicxml per segment")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bl = json.loads((BASE / "build_log.json").read_text(encoding="utf-8"))
    by_sid = {b["segment_id"]: b for b in bl}

    manifest_rows = []
    n_events_total = 0
    for sid, rationale in SAMPLE:
        if sid not in by_sid:
            raise SystemExit("sample segment not in build log: " + sid)
        sd = BASE / sid
        with (sd / "events.csv").open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            rows = list(reader)
        with (out_dir / ("iaa_" + sid + ".csv")).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                out = dict(r)
                for c in ANNOT_COLS:
                    out[c] = ""
                writer.writerow(out)
        mf = by_sid[sid]["manifest"]
        manifest_rows.append({
            "segment_id": sid, "composer": mf.get("composer", ""),
            "split": mf.get("split", ""), "n_events": len(rows),
            "rationale": rationale,
        })
        n_events_total += len(rows)
        if args.copy_media:
            for media in ("performance_segment.mid", "reference_score.musicxml"):
                src = sd / media
                if src.exists():
                    shutil.copy2(src, out_dir / (sid + "_" + media))

    with (out_dir / "iaa_sample_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["segment_id", "composer", "split", "n_events", "rationale"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    guide = _guide_text()
    (out_dir / "IAA_ANNOTATION_GUIDE.md").write_text(guide, encoding="utf-8")

    lines = ["# IAA 复标材料已生成", "",
             "- 抽样片段: %d / 40 (20%%)" % len(SAMPLE),
             "- 复标事件总数: %d" % n_events_total, ""]
    for m in manifest_rows:
        lines.append("- %s [%s/%s] %d 事件 - %s" % (
            m["segment_id"], m["composer"], m["split"], m["n_events"], m["rationale"]))
    lines += ["", "材料目录: " + str(out_dir)]
    print(chr(10).join(lines))
    return 0


def _guide_text() -> str:
    return chr(10).join([
        "# IAA 复标标注说明",
        "",
        "请为每个 iaa_<segment>.csv 的六列填写标注（与金标准同一套规则）：",
        "",
        "1. acoustic_sustain: yes / no / uncertain——该音符是否被 CC64 或共振声学延音。",
        "2. performance_pedal_action: hold / change / release / none / uncertain——CC64 在该事件附近的踏板动作。",
        "3. published_score_pedal: start / change / stop / none / uncertain——出版谱在该事件处的踏板标记。",
        "4. notation_decision: 记谱时值（QL 单位）——从候选时值中选择，或写明确时值。这是最关键的一列。",
        "5. review_class: independent-voice / notation-shortening / pedal-only / other / 留空。",
        "6. review_note: 自由文本说明决策理由。",
        "",
        "辅助材料：同片段目录下的 performance_segment.mid（音频）与 reference_score.musicxml（谱面）。",
        "不要参考原 events.csv 的标注值（避免记忆偏差）。",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
