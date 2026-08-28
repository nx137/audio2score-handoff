#!/usr/bin/env python3
"""Build one gold-standard segment from the frozen selection.

Used for incremental, resumable builds in constrained environments:

    python tools/build_formal_segments.py --index 3

Behaviour
---------
1. Loads ``outputs/pedal_gold_standard/formal_20260828_v1/selection.json``.
2. Builds the ``--index``-th segment with the same code path as
   ``build_pedal_gold_standard.py`` (alignment -> candidates -> slices ->
   P4 rule/learned/no-pedal -> renders).
3. Applies the lean policy by default: removes ``_work/`` and ``*.svg``
   (regenerable intermediates), keeping events.csv, candidate_options.csv,
   pedal_intervals.csv, the reference files, the three P4 MusicXML outputs,
   performance_segment.mid and segment_metadata.json.
4. Appends a build record to ``build_log.json`` (id, index, timestamp,
   elapsed, selection score, segment metadata).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from build_pedal_gold_standard import ROOT, Segment, build_segment

DEFAULT_SELECTION = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1" / "selection.json"
DEFAULT_OUT = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--selection", default=str(DEFAULT_SELECTION))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--keep-svg", action="store_true", help="keep render SVGs (default: delete)")
    parser.add_argument("--keep-work", action="store_true", help="keep _work intermediates (default: delete)")
    parser.add_argument("--skip-render", action="store_true",
                        help="skip MusicXML->SVG rendering (lean policy removes SVGs anyway)")
    args = parser.parse_args()

    payload = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    segments = [Segment(**item) for item in payload["segments"]]
    if not (0 <= args.index < len(segments)):
        raise SystemExit(f"index {args.index} out of range 0..{len(segments)-1}")

    segment = segments[args.index]
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    started = time.time()
    seg_id = f"{segment.row['composer']}_{segment.row['title']}_{segment.start_measure + 1}"
    align_src = out_root / '_alignments' / f'{seg_id}.csv'
    copied = False
    if align_src.exists():
        work_dir = out_root / seg_id / '_work'
        work_dir.mkdir(parents=True, exist_ok=True)
        dst = work_dir / 'alignment.csv'
        if not dst.exists():
            shutil.copy2(align_src, dst)
        copied = True
    metadata = build_segment(segment, out_root,
                             skip_align_if_present=copied,
                             skip_render=args.skip_render)
    elapsed = time.time() - started

    segment_dir = out_root / metadata["segment_id"]
    if not args.keep_work:
        work = segment_dir / "_work"
        if work.exists():
            shutil.rmtree(work)
    if not args.keep_svg:
        for path in segment_dir.glob("*.svg"):
            path.unlink()

    log_path = out_root / "build_log.json"
    log = []
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
    record = {
        "index": args.index,
        "segment_id": metadata["segment_id"],
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_sec": round(elapsed, 1),
        "selection_score": segment.score,
        "manifest": segment.row,
        "metadata": {key: value for key, value in metadata.items()
                     if key not in ("segment_id", "manifest")},
    }
    log = [item for item in log if item["index"] != args.index]
    log.append(record)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"[built] {metadata['segment_id']} in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
