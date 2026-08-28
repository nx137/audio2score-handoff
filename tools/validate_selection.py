#!/usr/bin/env python3
"""Validate reference-score coverage of selection candidates (resumable).

The frozen selection must satisfy the same constraint that
``build_pedal_gold_standard.build_segment`` enforces: at least 10 reference
(MusicXML) events inside the segment's QL range.  The performance measure
timeline (measure x performance bar_ql) and the score timeline (measure x score
bar_ql) diverge when the detected time signature differs from the published
score, so windows near the end of a piece can fall past the score's last event.

This helper walks ``selection_progress.json``, counts reference events for every
windowed candidate (resumable, time-budgeted), then re-runs the shared selection
policy on the validated subset and overwrites ``selection.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from build_pedal_gold_standard import ROOT, load_train_validation, stratified_pool
from select_gold_standard import PILOT_PIECE_KEYS, finalize_selection
from auto_label_candidates import reference_score_events

EPS = 1e-7
MIN_REF_EVENTS = 10


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="outputs/pedal_gold_standard/formal_20260828_v1")
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--per-composer", type=int, default=6)
    parser.add_argument("--time-budget", type=float, default=20.0)
    parser.add_argument("--no-exclude-pilots", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    progress_path = out_dir / "selection_progress.json"
    selection_path = out_dir / "selection.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))

    # rebuild pool exactly as select_gold_standard did
    rows = load_train_validation(ROOT / "data" / "asap_piece_manifest.csv")
    if not args.no_exclude_pilots:
        excluded = set(PILOT_PIECE_KEYS)
        rows = [row for row in rows if row["piece_key"] not in excluded]
    pool = stratified_pool(rows, per_composer=args.per_composer, seed=args.seed)
    if progress.get("pool_size") != len(pool):
        raise SystemExit(f"progress pool mismatch: {progress.get('pool_size')} vs {len(pool)}")

    results = progress["results"]
    start = time.time()
    for index in range(len(pool)):
        entry = results.get(str(index))
        if entry is None or not entry.get("window"):
            continue
        if entry.get("ref_count") is not None:
            continue
        xml = ROOT / "data" / "ASAP" / pool[index]["xml_score"]
        start_ql = entry["window"][0] * entry["bar_ql"]
        end_ql = (entry["window"][1] + 1) * entry["bar_ql"]
        try:
            events = reference_score_events(str(xml))
            ref_count = sum(1 for e in events if start_ql - EPS <= e.start_ql < end_ql)
            entry["ref_count"] = ref_count
        except Exception as exc:  # noqa: BLE001
            entry["ref_count"] = 0
            entry["validation_error"] = str(exc)[:200]
        if time.time() - start > args.time_budget:
            break

    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")

    missing = sum(1 for i in range(len(pool))
                  if results.get(str(i)) and results[str(i)].get("window")
                  and results[str(i)].get("ref_count") is None)
    if missing:
        print(f"[partial] {missing} windowed candidates still unvalidated", file=sys.stderr)
        return 2

    selected = finalize_selection(pool, results, 40, min_ref_events=MIN_REF_EVENTS)
    payload = {
        "seed": args.seed,
        "per_composer": args.per_composer,
        "count": len(selected),
        "excluded_pilot_pieces": not args.no_exclude_pilots,
        "validated": True,
        "min_ref_events": MIN_REF_EVENTS,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "segments": [
            {"row": item.row, "start_measure": item.start_measure,
             "end_measure": item.end_measure, "score": item.score,
             "bar_ql": item.bar_ql, "time_sig": list(item.time_sig),
             "tempo_bpm": item.tempo_bpm}
            for item in selected
        ],
    }
    selection_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
    print(f"[done] {len(selected)} validated segments -> {selection_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
