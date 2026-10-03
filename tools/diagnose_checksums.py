#!/usr/bin/env python3
"""只读诊断 CHECKSUMS.sha256：不做 20 条截断、输出纯 ASCII 转义（防中文控制台乱码）。

与 tools/verify_handoff.py::check_checksums 使用完全相同的 digest 口径，但额外给出
每条不匹配的成因分类，供主控定位（本工具**不修改任何文件**）：

  MISSING        -- 该路径在本地不存在（典型成因：本地做过 git mv / 未拉取）
  DIGEST_RAW_OK  -- digest() 不符，但**裸字节**摘要与记录相符（说明记录是用裸字节算的）
  DIGEST_NORM_OK -- digest() 不符，但**换行归一后**摘要与记录相符（仅换行差异）
  DIGEST         -- 内容确实不同（三者皆不符）

用法：
  python tools/diagnose_checksums.py
  python tools/diagnose_checksums.py --out diagnose_checksums_report.txt
  python tools/diagnose_checksums.py --basename-hints      # 为 MISSING 项列出同名候选路径
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTS = {
    ".txt", ".csv", ".py", ".md", ".json", ".sha256", ".sh", ".tex",
    ".musicxml", ".xml", ".yml", ".yaml", ".toml", ".rst", ".log",
    ".cfg", ".ini", ".gitignore", ".gitattributes", ".html", ".css",
}


def digest(path: Path) -> str:
    """与 verify_handoff.py 完全一致：文本走 universal newline，其余走裸字节。"""
    if path.suffix.lower() in TEXT_EXTS:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_digest(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def esc(text: str) -> str:
    """纯 ASCII 输出，避免中文 Windows 控制台把路径渲染成乱码。"""
    return text.encode("unicode_escape").decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checksums", type=Path, default=ROOT / "CHECKSUMS.sha256")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--basename-hints", action="store_true",
                    help="为 MISSING 项列出工作树中的同名候选路径")
    ap.add_argument("--max", type=int, default=10 ** 9,
                    help="最多打印多少条不匹配（默认不限）")
    args = ap.parse_args()

    lines = args.checksums.read_text(encoding="utf-8").splitlines()
    total = 0
    bad = []
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        expected, rel = line.split("  ", 1)
        total += 1
        path = ROOT / rel
        if not path.is_file():
            bad.append(("MISSING", rel, expected, "", ""))
            continue
        got = digest(path)
        if got == expected:
            continue
        raw = raw_digest(path)
        norm = norm_digest(path)
        kind = ("DIGEST_RAW_OK" if raw == expected
                else "DIGEST_NORM_OK" if norm == expected
                else "DIGEST")
        bad.append((kind, rel, expected, raw, norm))

    hints = {}
    if args.basename_hints and any(k == "MISSING" for k, *_ in bad):
        need = {Path(rel).name for k, rel, *_ in bad if k == "MISSING"}
        for p in ROOT.rglob("*"):
            if p.is_file() and p.name in need:
                rel = p.relative_to(ROOT).as_posix()
                if rel.split("/")[0] != ".git":
                    hints.setdefault(p.name, []).append(rel)

    out = []
    out.append("[diagnose] checksums = %s" % esc(str(args.checksums)))
    out.append("[diagnose] total entries = %d" % total)
    out.append("[diagnose] matching       = %d" % (total - len(bad)))
    out.append("[diagnose] NOT matching   = %d" % len(bad))
    out.append("[diagnose] breakdown      = %s" % dict(Counter(k for k, *_ in bad)))
    out.append("")
    for kind, rel, exp, raw, norm in bad[: args.max]:
        out.append("%s  %s" % (kind, esc(rel)))
        out.append("    expected   = %s" % exp)
        if raw:
            out.append("    raw_bytes  = %s" % raw)
            out.append("    normalized = %s" % norm)
        if hints:
            for cand in hints.get(Path(rel).name, []):
                if cand != rel:
                    out.append("    hint -> %s" % esc(cand))
    text = "\n".join(out) + "\n"
    sys.stdout.write(text)
    if args.out:
        args.out.write_text(text, encoding="ascii")
        sys.stdout.write("[diagnose] report written -> %s\n" % esc(str(args.out)))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
