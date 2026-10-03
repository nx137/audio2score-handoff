#!/usr/bin/env python3
"""Phase 2A: apply annotator-A verdicts to a fill-in review CSV, touching only the last two columns.

WHY
---
The Phase 2A gate needs ``reviewer_confirm`` / ``reviewer_note`` filled in for each sampled row
(209 rows over 5 segments) while every other column must stay byte-identical to the committed
sheet.  Editing 19-column CSV lines by hand is error-prone, so this tool appends to the two
trailing columns text-wise (minimal diff) and refuses any edit that would alter another column.

Verdicts file (UTF-8; blank lines and lines starting with '#' are ignored):
    <row_no> ok
    <row_no> incorrect <free-text note, single line>

Usage:
    python tools/phase2a_fill_review.py --csv <sample.csv> --verdicts <verdicts.txt> [--dry-run]
    python tools/phase2a_fill_review.py --csv <sample.csv> --check

Exit codes: 0 = ok; 2 = validation error (nothing written).  Counts are data, not errors.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

TAGS = ("ok", "incorrect")
LAST_TWO = ("reviewer_confirm", "reviewer_note")


def split_lines(text):
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing = text.endswith(newline)
    body = text[: -len(newline)] if trailing else text
    return body.split(newline), newline, trailing


def parse_row(line):
    return next(csv.reader(io.StringIO(line)))


def render(fields):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(list(fields))
    return buf.getvalue()


def parse_verdicts(path):
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 2)
        if len(parts) < 2:
            raise ValueError("line %d: expected '<row_no> <ok|incorrect> [note]'" % n)
        row_no, tag = parts[0], parts[1].lower()
        note = parts[2].strip() if len(parts) > 2 else ""
        if not row_no.isdigit():
            raise ValueError("line %d: row_no must be an integer" % n)
        if tag not in TAGS:
            raise ValueError("line %d: tag must be one of %s" % (n, "/".join(TAGS)))
        if tag == "incorrect" and not note:
            raise ValueError("line %d: 'incorrect' requires a note" % n)
        if row_no in out:
            raise ValueError("line %d: duplicate row_no %s" % (n, row_no))
        out[row_no] = (tag, note)
    return out


def load(path):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    lines, newline, trailing = split_lines(raw.decode("utf-8-sig"))
    return bom, lines, newline, trailing


def survey(lines, header):
    idx = {name: i for i, name in enumerate(header)}
    for name in ("row_no",) + LAST_TWO:
        if name not in idx:
            raise ValueError("missing column %s" % name)
    if idx[LAST_TWO[0]] != len(header) - 2 or idx[LAST_TWO[1]] != len(header) - 1:
        raise ValueError("reviewer_confirm / reviewer_note must be the last two columns")
    stat = dict(rows=0, ok=0, incorrect=0, pending=0, problems=[])
    for n, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        rec = parse_row(line)
        if len(rec) != len(header):
            stat["problems"].append("line %d: %d fields, expected %d" % (n, len(rec), len(header)))
            continue
        confirm = rec[idx["reviewer_confirm"]].strip()
        note = rec[idx["reviewer_note"]].strip()
        stat["rows"] += 1
        if confirm == "":
            stat["pending"] += 1
        elif confirm == "ok":
            stat["ok"] += 1
        elif confirm == "incorrect":
            stat["incorrect"] += 1
            if not note:
                stat["problems"].append("line %d: 'incorrect' without a note" % n)
        else:
            stat["problems"].append("line %d: reviewer_confirm=%r not in %s" % (n, confirm, TAGS))
    return idx, stat


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--verdicts")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    path = Path(a.csv)
    bom, lines, newline, trailing = load(path)
    header = parse_row(lines[0])
    try:
        idx, stat = survey(lines, header)
    except ValueError as exc:
        print("[error] %s" % exc)
        return 2

    if not a.verdicts:
        print("rows=%d ok=%d incorrect=%d pending=%d" % (stat["rows"], stat["ok"], stat["incorrect"], stat["pending"]))
        for pr in stat["problems"]:
            print("[problem] %s" % pr)
        print("CHECK: %s" % ("CLEAN" if not stat["problems"] else "ISSUES"))
        return 0 if not stat["problems"] else 2

    try:
        verdicts = parse_verdicts(Path(a.verdicts))
    except ValueError as exc:
        print("[error] verdicts: %s" % exc)
        return 2
    if not verdicts:
        print("[error] verdicts file has no entries")
        return 2

    c_row, c_conf, c_note = idx["row_no"], idx["reviewer_confirm"], idx["reviewer_note"]
    keep = len(header) - 2
    by_rownum = {}
    for i, line in enumerate(lines[1:], 1):
        if line.strip():
            by_rownum.setdefault(parse_row(line)[c_row].strip(), []).append(i)
    missing = [r for r in verdicts if r not in by_rownum]
    if missing:
        print("[error] row_no not in this sheet: %s" % ", ".join(sorted(missing, key=int)))
        return 2
    for r, rows in by_rownum.items():
        if len(rows) > 1:
            print("[error] duplicate row_no in sheet: %s" % r)
            return 2

    out = list(lines)
    target = set()
    for row_no, (tag, note) in verdicts.items():
        i = by_rownum[row_no][0]
        rec = parse_row(lines[i])
        if (rec[c_conf] != "" or rec[c_note] != "") and not a.overwrite:
            print("[error] row_no %s already filled (%r/%r); pass --overwrite to replace" % (row_no, rec[c_conf], rec[c_note]))
            return 2
        prefix = render(rec[:keep])
        if lines[i][: -2] != prefix and not (a.overwrite and lines[i].startswith(prefix)):
            print("[error] row_no %s: last two columns are not a plain trailing ',,'; refusing to edit" % row_no)
            return 2
        out[i] = prefix + "," + render([tag, note])
        if len(parse_row(out[i])) != len(header):
            print("[error] row_no %s: rebuilt line has %d fields, expected %d" % (row_no, len(parse_row(out[i])), len(header)))
            return 2
        target.add(i)

    stray = [n for n, (old, new) in enumerate(zip(lines, out), 1) if old != new and (n - 1) not in target]
    if stray:
        print("[error] refusing to write: unrelated lines would change: %s" % stray[:5])
        return 2

    changed = sorted(verdicts, key=int)
    if a.dry_run:
        print("[dry-run] would fill %d rows: %s" % (len(changed), ",".join(changed)))
        return 0

    text = newline.join(out) + (newline if trailing else "")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))

    bom2, lines2, _, _ = load(path)
    diff = [n for n, (x, y) in enumerate(zip(lines, lines2), 1) if x != y]
    ok_prefix = all(parse_row(lines2[n - 1])[:keep] == parse_row(lines[n - 1])[:keep] for n in diff)
    print("filled %d rows: %s" % (len(changed), ",".join(changed)))
    print("verify: bom_preserved=%s line_count_unchanged=%s (total %d) changed_lines=%d first17_columns_untouched=%s"
          % (bom2, len(lines2) == len(lines), len(lines), len(diff), ok_prefix))
    _, st2 = survey(lines2, header)
    print("after: rows=%d ok=%d incorrect=%d pending=%d" % (st2["rows"], st2["ok"], st2["incorrect"], st2["pending"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
