#!/usr/bin/env bash
# 最小可运行验证：不重跑冻结评测，不写入 evals/。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="outputs/handoff_smoke"
rm -rf "$OUT"
mkdir -p "$OUT"

python tools/verify_handoff.py
python -m unittest discover -s audio2score/scripts -p 'test_*.py' -v
python audio2score/scripts/p4_multivoice_score.py \
  --midi audio2score/samples/test_performance.mid \
  --out "$OUT/p4_learned.musicxml" \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --max-voices 12 --divisors 8,4,3
python audio2score/scripts/reconcile_midi_xml.py \
  --midi audio2score/samples/test_performance.mid \
  --xml "$OUT/p4_learned.musicxml" --reference p4 \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --max-voices 12
python audio2score/scripts/render_score.py \
  --musicxml "$OUT/p4_learned.musicxml" --out-svg "$OUT/p4_learned.svg"
printf '\n[完成] smoke 输出位于 %s\n' "$OUT"
