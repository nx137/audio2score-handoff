#!/usr/bin/env python3
"""本交接包的相对路径 WAV -> MIDI 前端入口。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "piano_transcription"
sys.path.insert(0, str(FRONTEND))

from piano_transcription_inference import PianoTranscription, load_audio, sample_rate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="WAV 转钢琴 MIDI（CPU）")
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    audio, sr = load_audio(str(args.wav), sr=sample_rate, mono=True)
    print(f"已读取 {args.wav}：{len(audio) / sr:.2f} 秒，采样率 {sr}")
    transcriptor = PianoTranscription(device=args.device)
    result = transcriptor.transcribe(audio, str(args.out))
    print(f"已写出 {args.out}；音符={len(result['est_note_events'])}，踏板={len(result['est_pedal_events'])}")


if __name__ == "__main__":
    main()
