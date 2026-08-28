#!/usr/bin/env python3
"""Auto-annotate the three decision columns of gold-standard events.csv.

Fills `notation_decision` / `review_class` / `review_note` on top of the
prefilled semantic columns (`tools/prefill_events.py`), implementing the
decision rules of ANNOTATION_RULES (v1.1 + pilot v2 calibration):

  notation_decision
    - reference_duration_ql present  -> use it verbatim (score convention wins)
    - otherwise -> shortest candidate >= key_duration_ql ("shortest readable");
      fall back to key_duration_ql when no candidate qualifies

  review_class (first match wins)
    - ref present and notation > key_duration + 0.05
      -> notation-shortening
         (score note is longer than the keyboard touch; the pedal carries the
          extension -- the paper's core written-vs-performed tension)
    - no ref and acoustic_sustain != 'no' and notation <= key_duration + 1e-9
      -> pedal-only (pedal carries the sustain; keep the short written note)
    - notation >= 0.5 and next_voice_gap_ql + 1e-6 >= notation
      -> independent-voice (long written note covers the following onset)
    - otherwise -> '' (blank)

  review_note: one explanatory sentence for every row.

Columns 27-29 only.  Left 24 columns and the three semantic columns are never
touched.  Only EMPTY cells are filled unless --overwrite.

Usage:
    python tools/annotate_events.py SEGMENT_DIR [SEGMENT_DIR ...] [--dry-run] [--overwrite]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ANNOT_COLS = ["acoustic_sustain", "performance_pedal_action", "published_score_pedal",
              "notation_decision", "review_class", "review_note"]
DECISION_COLS = ANNOT_COLS[3:]
EPS = 1e-9


def read_rows(path: Path):
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(text.splitlines()))
    return rows[0], rows[1:], has_bom, newline


def f(x):
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")


def shortest_readable(cand_str: str, key: float) -> float:
    values = sorted({float(v) for v in cand_str.split(";") if v.strip()})
    for v in values:
        if v >= key - EPS:
            return v
    return key


def decide(row: dict) -> tuple[str, str, str]:
    ref = f(row.get("reference_duration_ql"))
    key = f(row.get("key_duration_ql")) or 0.0
    acou = f(row.get("acoustic_duration_ql"))
    acou = acou if acou is not None else key
    cand = row.get("candidate_durations", "") or ""
    acoust = (row.get("acoustic_sustain") or "").strip()
    ngap = f(row.get("next_voice_gap_ql"))

    if ref is not None:
        notation = ref
        notation_str = str(row.get("reference_duration_ql")).strip()
    else:
        notation = shortest_readable(cand, key)
        notation_str = fmt(notation)

    cls, note = "", ""
    if ref is not None and notation > key + 0.05:
        cls = "notation-shortening"
        note = (f"reference duration {notation_str}; shorten acoustic extension "
                f"to {notation_str} (score convention; pedal carries the tail)")
    elif not ref and acoust != "no" and notation <= key + EPS:
        cls = "pedal-only"
        note = "pedal carries sustain; keep short written note"
    elif notation >= 0.5 and ngap is not None and ngap + EPS >= notation:
        cls = "independent-voice"
        note = (f"independent voice: written {notation_str} covers following "
                f"{row.get('hand')} onset (gap {ngap:.3f})")
    else:
        if acoust == "uncertain":
            note = "boundary/uncertain event; decision follows score/readability"
        elif ref is not None and notation <= key - 0.05:
            note = (f"key duration {key:.3f} exceeds notation {notation_str} "
                    f"(pedal/sustain hold); score convention kept")
        else:
            note = "routine; written duration follows score/readability"

    return notation_str, cls, note


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    changed_any = False
    for d in args.dirs:
        path = Path(d) / "events.csv"
        hdr, rows, bom, nl = read_rows(path)
        if hdr[-6:] != ANNOT_COLS:
            raise SystemExit(f"{path}: 6 annotation columns missing from header")
        idx = {name: i for i, name in enumerate(hdr)}
        out = [list(r) for r in rows]
        changed = 0
        for r in out:
            for col in DECISION_COLS:
                i = idx[col]
                if not args.overwrite and i < len(r) and r[i].strip():
                    continue
                if i >= len(r):
                    r.extend([""] * (i + 1 - len(r)))
            rowd = {hdr[j]: (r[j] if j < len(r) else "") for j in range(len(hdr))}
            nd, cls, note = decide(rowd)
            r[idx["notation_decision"]] = nd
            if cls != r[idx["review_class"]]:
                r[idx["review_class"]] = cls
            if note != r[idx["review_note"]]:
                r[idx["review_note"]] = note
            changed += 1
        if changed:
            changed_any = True
            if not args.dry_run:
                blob = ("\ufeff" if bom else "") + nl.join(
                    [",".join(hdr)] + [",".join(r) for r in out]) + nl
                path.write_bytes(blob.encode("utf-8"))
        print(f"{path}: {changed} rows decided")
    return 0 if not changed_any else 1


if __name__ == "__main__":
    raise SystemExit(main())
