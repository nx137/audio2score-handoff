#!/usr/bin/env python3
"""Precompute external alignment CSVs for all frozen segments (resumable).

The frozen gold-standard build should not depend on network or on re-deriving
ASAP beat alignments.  This helper runs ``build_asap_alignment`` once per frozen
segment and writes ``<out>/_alignments/<segment_id>.csv``.  It is
time-budgeted and skips segments whose alignment already exists, so it can be
resumed after any interruption.

The build driver (build_formal_segments.py) copies these CSVs into each
segment's ``_work/`` directory and skips alignment recomputation.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from build_pedal_gold_standard import ROOT, Segment, build_asap_alignment

DEFAULT_SELECTION = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1" / "selection.json"
DEFAULT_OUT = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", default=str(DEFAULT_SELECTION))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--time-budget", type=float, default=20.0)
    args = parser.parse_args()

    payload = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    segments = [Segment(**item) for item in payload["segments"]]
    out_root = Path(args.out)
    align_dir = out_root / "_alignments"
    align_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    for index, segment in enumerate(segments):
        dst = align_dir / f"{segment.row['composer']}_{segment.row['title']}_{segment.start_measure + 1}.csv"
        if dst.exists():
            continue
        build_asap_alignment(
            ROOT / "data" / "ASAP",
            segment.row["midi_performance"],
            dst,
            None,
            divisors=(8, 4, 3),
        )
        print(f"[align] {dst.name}", flush=True)
        if time.time() - start > args.time_budget:
            break

    done = sum(1 for segment in segments
               if (align_dir / f"{segment.row['composer']}_{segment.row['title']}_{segment.start_measure + 1}.csv").exists())
    print(f"[progress] {done}/{len(segments)} alignments", flush=True)
    return 0 if done == len(segments) else 2


if __name__ == "__main__":
    raise SystemExit(main())
