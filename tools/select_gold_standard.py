#!/usr/bin/env python3
"""Compute and freeze the gold-standard segment selection (resumable).

The build script (build_pedal_gold_standard.py) recomputes the selection from the
manifest on every run, which is expensive.  This helper computes it once against a
fixed seed, persists partial progress so it can be resumed after any interruption,
and writes a frozen ``selection.json`` that the build script can consume with
``--selection``.  The frozen selection makes the gold-standard build reproducible
without re-running the whole selection pass.

Progress model
--------------
- ``--progress-json`` stores one entry per stratified-pool row index: the best
  window (or an error marker).  Pool construction is deterministic given
  ``--seed`` and ``--per-composer``, so row indices are stable across resumes.
- ``--time-budget`` bounds each invocation; exit code 0 means the selection is
  complete and ``selection.json`` was written, 2 means more runs are needed.
- The five pilot pieces are excluded by default (see ``--no-exclude-pilots``).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from build_pedal_gold_standard import (  # same-directory import
    Segment,
    analyze_performance,
    best_window,
    load_train_validation,
    stratified_pool,
)

PILOT_PIECE_KEYS = (
    "Chopin\x1fEtudes_op_25_10",
    "Balakirev\x1fIslamey",
    "Rachmaninoff\x1fPreludes_op_32_10",
    "Liszt\x1fMephisto_Waltz",
    "Beethoven\x1fPiano_Sonatas_3-1",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/asap_piece_manifest.csv")
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--per-composer", type=int, default=6)
    parser.add_argument("--count", type=int, default=40, help="segments to freeze")
    parser.add_argument("--time-budget", type=float, default=18.0,
                        help="seconds of selection work per invocation")
    parser.add_argument("--out-dir", default="outputs/pedal_gold_standard/formal_20260828_v1")
    parser.add_argument("--no-exclude-pilots", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / "selection_progress.json"
    selection_path = out_dir / "selection.json"

    rows = load_train_validation(Path(args.manifest))
    if not args.no_exclude_pilots:
        excluded = set(PILOT_PIECE_KEYS)
        rows = [row for row in rows if row["piece_key"] not in excluded]
    pool = stratified_pool(rows, per_composer=args.per_composer, seed=args.seed)

    progress: dict = {}
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    if progress.get("pool_size") != len(pool):
        # pool changed (different manifest/seed/per-composer): restart
        progress = {"seed": args.seed, "per_composer": args.per_composer,
                    "pool_size": len(pool), "results": {}}

    start = time.time()
    results = progress.setdefault("results", {})
    for index, row in enumerate(pool):
        key = str(index)
        if key in results:
            continue
        try:
            records, pedals, time_sig, bar_ql, measure_count, tempo_bpm = analyze_performance(row)
            window = best_window(records, pedals, bar_ql, measure_count)
            results[key] = {"window": window, "error": None}
        except Exception as exc:  # noqa: BLE001 - record and continue
            results[key] = {"window": None, "error": str(exc)[:300]}
        if time.time() - start > args.time_budget:
            break

    progress_path.write_text(
        json.dumps(progress, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    if len(results) < len(pool):
        print(f"[partial] {len(results)}/{len(pool)} rows analysed", file=sys.stderr)
        return 2

    # ---- finalize: same selection policy as build_pedal_gold_standard.select_segments
    candidates = []
    for index, row in enumerate(pool):
        entry = results.get(str(index), {})
        window = entry.get("window")
        if not window:
            continue
        start_measure, end_measure, score = window
        try:
            records, pedals, time_sig, bar_ql, measure_count, tempo_bpm = analyze_performance(row)
        except Exception:  # noqa: BLE001
            continue
        candidates.append(Segment(
            row=row, start_measure=start_measure, end_measure=end_measure,
            score=score, bar_ql=bar_ql, time_sig=time_sig, tempo_bpm=tempo_bpm,
        ))
    candidates.sort(key=lambda item: item.score, reverse=True)

    selected = []
    used_pieces: set[str] = set()
    used_composers: set[str] = set()
    for candidate in candidates:
        piece, composer = candidate.row["piece_key"], candidate.row["composer"]
        if piece in used_pieces or composer in used_composers:
            continue
        selected.append(candidate)
        used_pieces.add(piece)
        used_composers.add(composer)
        if len(selected) == args.count:
            break
    if len(selected) < args.count:
        for candidate in candidates:
            if candidate in selected or candidate.row["piece_key"] in used_pieces:
                continue
            selected.append(candidate)
            used_pieces.add(candidate.row["piece_key"])
            if len(selected) == args.count:
                break

    payload = {
        "seed": args.seed,
        "per_composer": args.per_composer,
        "count": args.count,
        "excluded_pilot_pieces": not args.no_exclude_pilots,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "segments": [
            {"row": item.row, "start_measure": item.start_measure,
             "end_measure": item.end_measure, "score": item.score,
             "bar_ql": item.bar_ql, "time_sig": list(item.time_sig),
             "tempo_bpm": item.tempo_bpm}
            for item in selected
        ],
    }
    selection_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"[done] {len(selected)} segments frozen -> {selection_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
