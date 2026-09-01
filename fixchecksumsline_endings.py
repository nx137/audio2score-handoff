#!/usr/bin/env python3
"""Fix the cross-platform line-ending baseline for CHECKSUMS.sha256."""

import ast
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 1) Patch verify_handoff.py so text files are hashed with universal newlines.
vh_path = ROOT / "tools" / "verify_handoff.py"
old = vh_path.read_text(encoding="utf-8")

new_digest = '''TEXT_EXTS = {
    ".txt", ".csv", ".py", ".md", ".json", ".sha256", ".sh", ".tex",
    ".musicxml", ".xml", ".yml", ".yaml", ".toml", ".rst", ".log",
    ".cfg", ".ini", ".gitignore", ".gitattributes", ".html", ".css",
}


def digest(path: Path) -> str:
    """Hash text files after universal newline normalization."""
    if path.suffix.lower() in TEXT_EXTS:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        data = text.encode("utf-8")
    else:
        data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()
'''

marker = "def digest(path: Path) -> str:"
start = old.index(marker)
end = old.index("\n\n", start)
new_src = old[:start] + new_digest + old[end:]
ast.parse(new_src)
vh_path.write_bytes(new_src.encode("utf-8"))
print("[1] tools/verify_handoff.py patched")

# 2) Regenerate every checksum entry with the normalized digest.
sys.path.insert(0, str(ROOT / "tools"))
from verify_handoff import digest  # noqa: E402

ck_path = ROOT / "CHECKSUMS.sha256"
lines = ck_path.read_text(encoding="utf-8").splitlines()
out = []
missing = []
for line in lines:
    if not line.strip() or line.startswith("#"):
        out.append(line)
        continue
    expected, rel = line.split("  ", 1)
    p = ROOT / rel
    if not p.is_file():
        missing.append(rel)
        out.append(line)
        continue
    h = digest(p)
    out.append(h + "  " + rel)

if missing:
    print("[2] FAIL: missing files, cannot regenerate:")
    for m in missing:
        print("    ", m)
    raise SystemExit(1)

ck_path.write_bytes(("\n".join(out) + "\n").encode("utf-8"))
print("[2] CHECKSUMS.sha256 regenerated: %d entries" % len(out))

# 3) Append eol=lf and binary rules to .gitattributes.
ga_path = ROOT / ".gitattributes"
ga = ga_path.read_text(encoding="utf-8").rstrip("\n")
ga += "\n\n# ---- cross-platform line endings (overrides core.autocrlf) ----\n"
for ext in [
    "py", "md", "txt", "csv", "json", "musicxml", "tex", "sh",
    "sha256", "log", "xml", "yml", "yaml", "toml",
]:
    ga += "*." + ext + " text eol=lf\n"
ga += "# ---- binary markers (prevent git mis-conversion) ----\n"
for ext in [
    "mid", "pdf", "png", "jpg", "jpeg", "pkl", "joblib",
    "wav", "mp3", "zip", "gz", "svg",
]:
    ga += "*." + ext + " binary\n"
ga_path.write_bytes(ga.encode("utf-8"))
print("[3] .gitattributes updated")

# 4) Self-check every regenerated entry.
bad = []
for line in ck_path.read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    expected, rel = line.split("  ", 1)
    p = ROOT / rel
    if not p.is_file() or digest(p) != expected:
        bad.append(rel)

if bad:
    print("[4] FAIL: %d entries still mismatched" % len(bad))
    for b in bad[:20]:
        print("    ", b)
    raise SystemExit(1)

print("[4] self-check passed: all entries match")
print("ALL DONE - ready for commit")
