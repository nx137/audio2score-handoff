#!/usr/bin/env python3
"""Prefill the three semantic annotation columns of gold-standard events.csv.

Implements rules 2.1-2.4 of ANNOTATION_RULES.md:

    acoustic_sustain          yes | no | uncertain                      (2.1)
    performance_pedal_action  hold | change | release | none | uncertain (2.2)
    published_score_pedal     start | change | stop | none | uncertain   (2.3)

Boundary rule (2.4): an event with onset within 0.25 ql of either segment
edge is `uncertain` in all three columns.

FIX (found during pilot v2 annotation, Liszt segment):
For a note near the END of pedal interval k, the quick-retake test must use
the gap to the NEXT interval (ivs[k+1].start - ivs[k].end), NOT the current
interval's own `retake_gap_ql` column (which records the gap *before* it and
is empty for the first interval).  The old behaviour mislabeled 7 Liszt rows
as `release` instead of `change`.

Usage:
    python tools/prefill_events.py SEGMENT_DIR [SEGMENT_DIR ...] [--dry-run] [--overwrite]

Inputs per segment dir: events.csv, pedal_intervals.csv, reference_pedals.csv,
segment_metadata.json (start_ql / end_ql).
Output: events.csv with the first three annotation columns filled.
Columns 27-29 (notation_decision / review_class / review_note) and all left
columns are never touched.  By default only EMPTY cells are filled; use
--overwrite to recompute every row (e.g. for a fresh build).  --dry-run
prints what would change without writing anything.  Exit code 1 means the
prefill is not yet applied (cells would change).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

BOUNDARY_QL = 0.25      # rule 2.4
RETAKE_QL = 0.25        # rule 2.2: quick re-press threshold
SCORE_QL = 0.25         # rule 2.3: pedal-mark matching window

ANNOT_COLS = [
    "acoustic_sustain", "performance_pedal_action", "published_score_pedal",
    "notation_decision", "review_class", "review_note",
]
PREFILL_COLS = ANNOT_COLS[:3]


def read_rows(path: Path) -> tuple[list[str], list[list[str]], bool, str]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise SystemExit(f"{path}: empty file")
    return rows[0], rows[1:], has_bom, newline


def parse_pedal_intervals(path: Path) -> list[tuple[float, float]]:
    if not path.exists():
        return []
    rows = list(csv.reader(path.open(newline="", encoding="utf-8-sig")))
    ivs = []
    for r in rows[1:]:
        if len(r) >= 3 and r[1].strip() and r[2].strip():
            ivs.append((float(r[1]), float(r[2])))
    return sorted(ivs)


def parse_ref_pedals(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = list(csv.reader(path.open(newline="", encoding="utf-8-sig")))
    if len(rows) <= 1:
        return []
    hdr = rows[0]
    idx = {name: i for i, name in enumerate(hdr)}
    out = []
    for r in rows[1:]:
        d = {name: (r[i] if i < len(r) else "") for name, i in idx.items()}
        if d.get("position_ql", "").strip():
            out.append(d)
    return out


def load_segment_bounds(path: Path) -> tuple[float, float]:
    meta = json.loads(path.read_text(encoding="utf-8"))
    return float(meta["start_ql"]), float(meta["end_ql"])


def is_boundary(onset: float, s0: float, s1: float) -> bool:
    return onset < s0 + BOUNDARY_QL or onset > s1 - BOUNDARY_QL


def classify_acoustic(pe: float, onset: float, s0: float, s1: float) -> str:
    if is_boundary(onset, s0, s1):
        return "uncertain"
    return "yes" if pe > RETAKE_QL else "no"


def classify_perf(onset: float, ivs: list[tuple[float, float]], s0: float, s1: float) -> str:
    """Rule 2.2.  For a note near the end of interval k the quick-retake test
    uses the gap to the NEXT interval (ivs[k+1].start - ivs[k].end)."""
    if is_boundary(onset, s0, s1):
        return "uncertain"
    for k, (s, e) in enumerate(ivs):
        if s <= onset <= e:
            if e - onset > RETAKE_QL:
                return "hold"
            nxt = ivs[k + 1] if k + 1 < len(ivs) else None
            if nxt is not None and (nxt[0] - e) < RETAKE_QL:
                return "change"
            return "release"
    for k in range(len(ivs) - 1):
        e, s2 = ivs[k][1], ivs[k + 1][0]
        if e < onset < s2:
            near_release = (onset - e) <= RETAKE_QL
            near_press = (s2 - onset) <= RETAKE_QL
            if near_release and (s2 - e) < RETAKE_QL:
                return "change"
            if near_release:
                return "release"
            if near_press:
                return "change"
            return "none"
    return "none"


def classify_score(onset: float, ref_pedals: list[dict]) -> str:
    """Rule 2.3: nearest pedal mark within 0.25 ql decides the event type."""
    if not ref_pedals:
        return "none"
    best, best_d = None, float("inf")
    for p in ref_pedals:
        d = abs(float(p["position_ql"]) - onset)
        if d < best_d:
            best_d, best = d, p
    if best is not None and best_d <= SCORE_QL:
        return best.get("event_type", "")
    return "none"


def prefill_segment(seg_dir: Path, overwrite: bool, dry_run: bool) -> dict:
    seg_dir = Path(seg_dir)
    events_path = seg_dir / "events.csv"
    if not events_path.exists():
        raise SystemExit(f"missing {events_path}")
    header, rows, has_bom, newline = read_rows(events_path)

    col = {name: i for i, name in enumerate(header)}
    missing = [c for c in ANNOT_COLS if c not in col]
    if missing:
        raise SystemExit(f"{events_path}: missing columns {missing}")
    if any(c not in col for c in ["onset_ql", "pedal_extension_ql"]):
        raise SystemExit(f"{events_path}: missing onset_ql / pedal_extension_ql")

    ivs = parse_pedal_intervals(seg_dir / "pedal_intervals.csv")
    ref_pedals = parse_ref_pedals(seg_dir / "reference_pedals.csv")
    s0, s1 = load_segment_bounds(seg_dir / "segment_metadata.json")

    changes = []
    stats = {
        "acoustic": {v: 0 for v in ("yes", "no", "uncertain")},
        "perf": {v: 0 for v in ("hold", "change", "release", "none", "uncertain")},
        "score": {v: 0 for v in ("start", "change", "stop", "none", "uncertain")},
    }
    for r in rows:
        if not r:
            continue
        onset, pe = float(r[col["onset_ql"]]), float(r[col["pedal_extension_ql"]])
        computed = [
            classify_acoustic(pe, onset, s0, s1),
            classify_perf(onset, ivs, s0, s1),
            classify_score(onset, ref_pedals),
        ]
        for key, value in zip(("acoustic", "perf", "score"), computed):
            stats[key][value] += 1
        for c, value in zip(PREFILL_COLS, computed):
            i = col[c]
            if not overwrite and r[i].strip():
                continue
            if r[i] != value:
                changes.append((r[col["event_id"]], c, r[i], value))
                if not dry_run:
                    r[i] = value

    if changes and not dry_run:
        with events_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\r\n" if newline == "\r\n" else "\n")
            first = header[0]
            writer.writerow([("\ufeff" if has_bom else "") + first] + header[1:])
            for r in rows:
                writer.writerow(r)

    return {"changes": changes, "stats": stats}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("segments", nargs="+", help="gold-standard segment directories")
    ap.add_argument("--dry-run", action="store_true", help="report only, do not write")
    ap.add_argument("--overwrite", action="store_true", help="recompute filled cells too")
    args = ap.parse_args()

    total_changes = 0
    for seg in args.segments:
        result = prefill_segment(Path(seg), args.overwrite, args.dry_run)
        st = result["stats"]
        mode = "DRY-RUN" if args.dry_run else ("OVERWRITE" if args.overwrite else "FILL-EMPTY")
        print(f"[{mode}] {seg}")
        print(f"    acoustic: {st['acoustic']}")
        print(f"    perf    : {st['perf']}")
        print(f"    score   : {st['score']}")
        if result["changes"]:
            total_changes += len(result["changes"])
            print(f"    {len(result['changes'])} changes:")
            for eid, colname, old, new in result["changes"][:12]:
                print(f"        {eid}  {colname}: {old!r} -> {new!r}")
            if len(result["changes"]) > 12:
                print(f"        ... and {len(result['changes']) - 12} more")
        else:
            print("    no changes")
    return 1 if total_changes else 0


if __name__ == "__main__":
    sys.exit(main())
