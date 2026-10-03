#!/usr/bin/env python3
"""校验工具共用的摘要口径（单一事实源）——tools/verify_handoff.py 与 tools/diagnose_checksums.py 均须经此。

口径（2026-10-03 v2.3 冻结）：

1. `TEXT_EXTS` 白名单内的文件：以 universal newline 读文本（utf-8, errors=replace），再 encode("utf-8") 取 sha256。
   因此「仓库 blob 为 CRLF、工作树为 LF」时摘要仍然相同（本仓确实存在这类 blob，见交接文档坑 23）。
2. 其余文件：裸字节 sha256，不做任何转换。
3. Git LFS（v2.3 新增；修复 `frontend/.../*.pth` 的假失败）：若某路径被 `.gitattributes` 标记 `filter=lfs`，
   则取该文件的「指针语义」摘要 ——
     * 工作树是指针形态（以 LFS_POINTER_MAGIC 开头）-> 直接对指针字节取 sha256；
     * 工作树是已涂抹形态（git-lfs 检出的真实大文件）-> 用该文件的 sha256 与字节数重建仓库所钉的指针文本，再取 sha256。
   两种形态都等价于「仓库内容 == CHECKSUMS 记录」；已涂抹形态还额外证明了本地大文件与仓库 pin 的 oid/size 完全一致。
   文件若损坏或被截断，重建出的指针与记录不符 -> 仍然判失败（本模块不放松任何判定）。

本模块只读，不写任何文件。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTS = {
    ".txt", ".csv", ".py", ".md", ".json", ".sha256", ".sh", ".tex",
    ".musicxml", ".xml", ".yml", ".yaml", ".toml", ".rst", ".log",
    ".cfg", ".ini", ".gitignore", ".gitattributes", ".html", ".css",
}

LFS_POINTER_MAGIC = b"version https://git-lfs.github.com/spec/v1\n"

_PATTERN_CACHE: Dict[str, List["re.Pattern[str]"]] = {}


def is_text(path) -> bool:
    """该路径是否走「文本 + 换行归一」口径。"""
    return Path(path).suffix.lower() in TEXT_EXTS


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """把 .gitattributes 的通配模式转成正则（`**` 跨目录，`*`/`?` 不跨目录）。"""
    out: List[str] = []
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        elif ch == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(ch))
                i += 1
            else:
                out.append(pattern[i:j + 1])
                i = j + 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _compile(pattern: str) -> "re.Pattern[str]":
    # 含 `/` 的模式锚定仓库根；不含 `/` 的模式匹配任意层级的 basename。
    return _glob_to_regex(pattern if "/" in pattern else "**/" + pattern)


def lfs_patterns(root: Optional[Path] = None) -> List["re.Pattern[str]"]:
    """从 <root>/.gitattributes 取出所有 `filter=lfs` 模式（结果按 root 缓存）。"""
    key = str(Path(root) if root else ROOT)
    cached = _PATTERN_CACHE.get(key)
    if cached is not None:
        return cached
    patterns: List["re.Pattern[str]"] = []
    attr = Path(key) / ".gitattributes"
    if attr.is_file():
        for line in attr.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2 or "filter=lfs" not in parts[1:]:
                continue
            patterns.append(_compile(parts[0]))
    _PATTERN_CACHE[key] = patterns
    return patterns


def rel_posix(path, root: Optional[Path] = None) -> str:
    """返回相对仓库根的 POSIX 路径；不在仓库内时退回原样路径。"""
    p = Path(path)
    r = Path(root) if root else ROOT
    try:
        return p.resolve().relative_to(r.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def is_lfs_tracked(path, root: Optional[Path] = None) -> bool:
    patterns = lfs_patterns(root)
    if not patterns:
        return False
    return any(p.match(rel_posix(path, root)) for p in patterns)


def rebuild_lfs_pointer(data: bytes) -> bytes:
    """按 git-lfs 指针格式，从实体内容重建仓库所钉的指针文本（oid + size）。"""
    return (LFS_POINTER_MAGIC
            + b"oid sha256:" + hashlib.sha256(data).hexdigest().encode("ascii") + b"\n"
            + b"size " + str(len(data)).encode("ascii") + b"\n")


def digest_ex(path, root: Optional[Path] = None) -> Tuple[str, str]:
    """返回 (sha256, 口径标签)。标签：lfs-pointer / lfs-smudged / text-normalized / raw。"""
    p = Path(path)
    if is_lfs_tracked(p, root):
        data = p.read_bytes()
        if data.startswith(LFS_POINTER_MAGIC):
            return hashlib.sha256(data).hexdigest(), "lfs-pointer"
        return hashlib.sha256(rebuild_lfs_pointer(data)).hexdigest(), "lfs-smudged"
    if is_text(p):
        with p.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return hashlib.sha256(text.encode("utf-8")).hexdigest(), "text-normalized"
    return hashlib.sha256(p.read_bytes()).hexdigest(), "raw"


def digest(path, root: Optional[Path] = None) -> str:
    """与旧版 verify_handoff.digest() 兼容的签名（只返回摘要）。"""
    return digest_ex(path, root)[0]
