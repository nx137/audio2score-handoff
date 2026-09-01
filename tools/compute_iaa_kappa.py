#!/usr/bin/env python3
"""Compute inter-annotator agreement (Cohen's kappa) between the frozen
gold standard (annotator A, events.csv) and the IAA re-annotation
(annotator B, iaa/iaa_<sid>.csv), aligned by event_id.

Per column:
  - categorical columns (review_class, performance_pedal_action,
    published_score_pedal, acoustic_sustain): standard Cohen's kappa
  - notation_decision (continuous duration): linear-weighted kappa plus
    exact / tol0.05 / tol0.25 agreement rates

Bootstrap 95% CI on each kappa (resample events, fixed seed).

Usage:
    python tools/compute_iaa_kappa.py [--iaa-dir .../iaa] [--out .../iaa_kappa.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "pedal_gold_standard" / "formal_20260828_v1"

CAT_COLS = ["review_class", "performance_pedal_action",
            "published_score_pedal", "acoustic_sustain"]
N_BOOT = 200
SEED = 20260828


def cohen_kappa(a: list, b: list) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    labels = sorted(set(a) | set(b))
    idx = {lab: i for i, lab in enumerate(labels)}
    cm = [[0] * len(labels) for _ in labels]
    for x, y in zip(a, b):
        cm[idx[x]][idx[y]] += 1
    po = sum(cm[i][i] for i in range(len(labels))) / n
    row = [sum(r) for r in cm]
    col = [sum(cm[i][j] for i in range(len(labels))) for j in range(len(labels))]
    pe = sum(row[i] * col[i] for i in range(len(labels))) / (n * n)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


def weighted_kappa_linear(a: list, b: list) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    labels = sorted(set(a) | set(b))
    k = len(labels)
    idx = {lab: i for i, lab in enumerate(labels)}
    cm = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        cm[idx[x]][idx[y]] += 1
    n = float(n)
    po = 0.0
    pe = 0.0
    row = [sum(r) for r in cm]
    col = [sum(cm[i][j] for i in range(k)) for j in range(k)]
    for i in range(k):
        for j in range(k):
            w = 1.0 - abs(i - j) / (k - 1) if k > 1 else 1.0
            po += w * cm[i][j] / n
            pe += w * (row[i] * col[j]) / (n * n)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


def agreement_rates(a: list, b: list) -> dict:
    exact = sum(1 for x, y in zip(a, b) if x == y)
    t05 = sum(1 for x, y in zip(a, b) if abs(x - y) <= 0.05)
    t25 = sum(1 for x, y in zip(a, b) if abs(x - y) <= 0.25)
    n = len(a)
    return {"n": n, "exact": round(exact / n, 4),
            "tol0.05": round(t05 / n, 4), "tol0.25": round(t25 / n, 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iaa-dir", default=str(BASE / "iaa"))
    ap.add_argument("--out", default=str(BASE / "evaluation" / "iaa_kappa.json"))
    args = ap.parse_args()

    iaa_dir = Path(args.iaa_dir)
    manifest = list(csv.DictReader((iaa_dir / "iaa_sample_manifest.csv").open(encoding="utf-8-sig", newline="")))

    pairs = {"cat": {c: [] for c in CAT_COLS}, "dur": {"a": [], "b": []}}
    n_aligned = 0
    n_missing = 0
    for m in manifest:
        sid = m["segment_id"]
        gold_path = BASE / sid / "events.csv"
        iaa_path = iaa_dir / ("iaa_" + sid + ".csv")
        with gold_path.open(encoding="utf-8-sig", newline="") as f:
            gold = {r["event_id"]: r for r in csv.DictReader(f)}
        with iaa_path.open(encoding="utf-8-sig", newline="") as f:
            iaa = {r["event_id"]: r for r in csv.DictReader(f)}
        for eid, g in gold.items():
            if eid not in iaa:
                continue
            b = iaa[eid]
            for c in CAT_COLS:
                gv = (g.get(c) or "").strip()
                bv = (b.get(c) or "").strip()
                if not gv or not bv:
                    continue
                pairs["cat"][c].append((gv, bv))
            gd = (g.get("notation_decision") or "").strip()
            bd = (b.get("notation_decision") or "").strip()
            if gd and bd:
                pairs["dur"]["a"].append(float(gd))
                pairs["dur"]["b"].append(float(bd))
                n_aligned += 1
            else:
                n_missing += 1

    result = {"n_aligned_duration": n_aligned, "n_unfilled": n_missing}
    for c in CAT_COLS:
        vals = pairs["cat"][c]
        a = [v[0] for v in vals]
        b = [v[1] for v in vals]
        k = cohen_kappa(a, b)
        result[c] = {"n": len(vals), "kappa": round(k, 4),
                     "ci95": _boot_ci(a, b, cohen_kappa)}
    da, db = pairs["dur"]["a"], pairs["dur"]["b"]
    wk = weighted_kappa_linear(da, db)
    result["notation_decision"] = {
        "n": len(da), "weighted_kappa_linear": round(wk, 4),
        "ci95": _boot_ci(da, db, weighted_kappa_linear),
        "agreement": agreement_rates(da, db),
    }

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# IAA（标注者一致性）", "",
             "- 对齐时值事件: %d, 未填: %d" % (n_aligned, n_missing), "",
             "| 列 | n | kappa | 95% CI |", "|---|---|---|---|"]
    for c in CAT_COLS:
        r = result[c]
        lines.append("| %s | %d | %.3f | [%.3f, %.3f] |" % (
            c, r["n"], r["kappa"], r["ci95"][0], r["ci95"][1]))
    r = result["notation_decision"]
    ag = r["agreement"]
    lines.append("| notation_decision (weighted) | %d | %.3f | [%.3f, %.3f] |" % (
        r["n"], r["weighted_kappa_linear"], r["ci95"][0], r["ci95"][1]))
    lines += ["", "notation_decision 一致率: exact=%.3f, tol0.05=%.3f, tol0.25=%.3f" % (
                  ag["exact"], ag["tol0.05"], ag["tol0.25"]), "",
              "（Landis-Koch: <0 差 / 0-0.2 轻微 / 0.2-0.4 一般 / 0.4-0.6 中等 /",
              " 0.6-0.8 显著 / 0.8-1.0 几乎完全一致）", "", "输出: " + str(path)]
    print(chr(10).join(lines))
    return 0


def _boot_ci(a: list, b: list, fn, n_boot: int = N_BOOT, seed: int = SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(a)
    if n == 0:
        return [0.0, 0.0]
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        aa = [a[i] for i in idx]
        bb = [b[i] for i in idx]
        vals.append(fn(aa, bb))
    vals.sort()
    lo = vals[int(0.025 * n_boot)]
    hi = vals[int(0.975 * n_boot) - 1]
    return [round(lo, 4), round(hi, 4)]

