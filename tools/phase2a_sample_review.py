#!/usr/bin/env python3
"""Phase 2A S8: stratified sample of F-group rows from per-segment review CSVs
into an annotator-A fill-in sheet.

F-group (Phase 2A): rows whose ``groups`` field contains "F"
    i.e. published_score_pedal (3) is start/change/stop -- the rows annotator A
    checks against reference_score.musicxml (expansion plan 2.4; exec S7/S8).

Sampling method (reproducible, proportional stratified sampling):
  per segment, n_target = max(min_per_seg, round_half_up(frac * n_F));
  if n_F <= min_per_seg the segment is taken in full (Miroirs F=4 -> all 4).
  stratum key = (published_score_pedal, performance_pedal_action,
                 review_class or "(none)").
  Forced layer first (always included):
     - rows with review_priority == "high";
     - whole strata of size <= 3 (covers disputed core cells & class-less rows
       that live in small strata).
  Remaining budget over non-forced strata by largest-remainder allocation
  (quota_i = frac * size_i); within-stratum draws are random.sample with a
  fixed seed (default 20260907) -> reproducible.

Output per segment (working artifact; do NOT commit, exec S3/S7 policy):
  <out>/phase2A_A_review_<sid>_sample.csv      (17 review cols + reviewer_confirm
                                               + reviewer_note, both empty)
  <out>/phase2A_A_review_<sid>_sample.manifest.json

Usage:
  python tools/phase2a_sample_review.py \
      --dir outputs/pedal_expansion/review --out outputs/pedal_expansion/review/sampled \
      [--frac 0.30] [--min-per-seg 10] [--seed 20260907] [--report]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REVIEW_COLS = ["segment_id", "row_no", "event_id", "hand", "pitch", "onset_ql",
               "onset_location", "groups", "acoustic_sustain",
               "performance_pedal_action", "published_score_pedal",
               "notation_decision", "review_class", "review_note",
               "baseline_published_score_pedal", "review_priority",
               "reference_tie_start"]
FILL_COLS = REVIEW_COLS + ["reviewer_confirm", "reviewer_note"]


def round_half_up(x: float) -> int:
    return int(x + 0.5)


def load_review_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    if header != REVIEW_COLS:
        raise SystemExit(f"{path.name}: header mismatch with REVIEW_COLS")
    idx = {c: i for i, c in enumerate(header)}
    data = []
    for rn, row in enumerate(rows[1:], start=1):
        rec = {c: (row[idx[c]] if idx[c] < len(row) else "") for c in REVIEW_COLS}
        rec["_rn"] = rn
        data.append(rec)
    return data


def stratum_key(rec: dict) -> tuple:
    return (rec["published_score_pedal"].strip() or "(empty)",
            rec["performance_pedal_action"].strip() or "(empty)",
            (rec["review_class"].strip() or "(none)"))


def allocate(frac: float, remaining: int, strata):
    """largest-remainder allocation of `remaining` over strata = [(key,size)]."""
    alloc = OrderedDict()
    if remaining <= 0 or not strata:
        return alloc
    quotas = [(k, frac * s) for k, s in strata]
    for k, q in quotas:
        alloc[k] = int(q)
    rem = {k: q - int(q) for k, q in quotas}
    deficit = remaining - sum(alloc.values())
    if deficit > 0:
        for k, _ in sorted(rem.items(), key=lambda kv: -kv[1])[:deficit]:
            alloc[k] += 1
    elif deficit < 0:
        for k, _ in sorted(alloc.items(), key=lambda kv: -kv[1]):
            if alloc[k] > 0:
                alloc[k] -= 1
                deficit += 1
                if deficit == 0:
                    break
    sizes = dict(strata)
    for k in list(alloc):
        alloc[k] = min(alloc[k], sizes[k])
    return alloc


def sample_segment(recs, frac, min_per_seg, seed):
    rng = random.Random(seed)
    n_F = len(recs)
    if n_F == 0:
        return None
    n_target = max(min_per_seg, round_half_up(frac * n_F))
    n_target = min(n_target, n_F)          # can never exceed population
    full_take = n_F <= min_per_seg         # e.g. Miroirs F=4 -> all rows

    # --- group rows by stratum ---
    strata = OrderedDict()
    for rec in recs:
        strata.setdefault(stratum_key(rec), []).append(rec)

    forced_rows, forced_reason = [], []
    nonforced = []                         # [(key, rows)]
    for key, rows in strata.items():
        if full_take or len(rows) <= 3:
            forced_rows.extend(rows)
            forced_reason.extend(["full-take" if full_take else "small-stratum"] * len(rows))
            continue
        hi = [r for r in rows if r["review_priority"].strip().lower() == "high"]
        for r in hi:
            forced_rows.append(r)
            forced_reason.append("priority-high")
        rest = [r for r in rows if r not in hi]
        if rest:
            nonforced.append((key, rest))

    # de-dup forced (a high row may sit in a <=3 stratum already taken)
    seen = set()
    forced_clean, forced_reason_clean = [], []
    for r, why in zip(forced_rows, forced_reason):
        if id(r) not in seen:
            seen.add(id(r))
            forced_clean.append(r)
            forced_reason_clean.append(why)
    forced_rows, forced_reason = forced_clean, forced_reason_clean

    # --- largest remainder over non-forced strata ---
    budget = n_target - len(forced_rows)
    drawn_rows, drawn_reason = list(forced_rows), list(forced_reason)
    if budget > 0 and nonforced:
        sizes = [(k, len(rows)) for k, rows in nonforced]
        alloc = allocate(frac, budget, sizes)
        rows_by_key = {k: rows for k, rows in nonforced}
        for key, k in alloc.items():
            if k <= 0:
                continue
            sample = rng.sample(rows_by_key[key], k)
            drawn_rows.extend(sample)
            drawn_reason.extend(["stratum-random"] * len(sample))

    # deterministic order back to file order
    pair = sorted(zip(drawn_rows, drawn_reason), key=lambda pr: pr[0]["_rn"])
    drawn_rows = [p[0] for p in pair]
    drawn_reason = [p[1] for p in pair]
    return {"n_F": n_F, "n_target": n_target, "full_take": full_take,
            "rows": drawn_rows, "reasons": drawn_reason}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="dir containing phase2A_A_review_*.csv")
    ap.add_argument("--out", required=True, help="output dir for fill-in sheets")
    ap.add_argument("--frac", type=float, default=0.30)
    ap.add_argument("--min-per-seg", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260907)
    ap.add_argument("--report", action="store_true", help="print per-stratum draw summary")
    a = ap.parse_args()

    in_dir = Path(a.dir)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(glob.glob(str(in_dir / "phase2A_A_review_*.csv")))
    if not files:
        raise SystemExit(f"no review CSVs found under {in_dir}")
    grand = 0
    for f in files:
        sid = Path(f).stem[len("phase2A_A_review_"):]
        recs = [r for r in load_review_csv(Path(f)) if "F" in r["groups"]]
        res = sample_segment(recs, a.frac, a.min_per_seg, a.seed)
        if res is None:
            print(f"{sid}: no F rows, skipped")
            continue
        rows, reasons = res["rows"], res["reasons"]
        grand += len(rows)
        csv_path = out_dir / f"phase2A_A_review_{sid}_sample.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(FILL_COLS)
            for r in rows:
                w.writerow([r[c] for c in REVIEW_COLS] + ["", ""])
        manifest = {k: res[k] for k in ("n_F", "n_target", "full_take")}
        manifest["seed"] = a.seed
        manifest["frac"] = a.frac
        manifest["min_per_seg"] = a.min_per_seg
        manifest["strata_drawn"] = Counter(stratum_key(r) for r in rows)
        manifest["strata_drawn"] = {f"{k[0]}|{k[1]}|{k[2]}": v
                                    for k, v in manifest["strata_drawn"].items()}
        manifest["rows"] = [{"row_no": r["row_no"], "stratum": "|".join(stratum_key(r)),
                             "method": why} for r, why in zip(rows, reasons)]
        mpath = out_dir / f"phase2A_A_review_{sid}_sample.manifest.json"
        with mpath.open("w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=1)
        print(f"{sid}: n_F={res['n_F']} n_target={res['n_target']} "
              f"full_take={res['full_take']} drawn={len(rows)} "
              f"(forced={sum(1 for x in reasons if x!='stratum-random')}, "
              f"random={sum(1 for x in reasons if x=='stratum-random')})")
        if a.report:
            cnt = Counter(reasons)
            for k, v in sorted(cnt.items()):
                print(f"    method {k}: {v}")
            sc = Counter(stratum_key(r) for r in rows)
            for k, v in sorted(sc.items()):
                print(f"    stratum {k[0]}|{k[1]}|{k[2]}: {v}")
    print(f"TOTAL sampled rows across {len(files)} segments: {grand}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
