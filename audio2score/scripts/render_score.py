#!/usr/bin/env python3
"""
render_score.py — MusicXML → 五线谱 SVG/PNG(P1b:可视化)。

用 Verovio 把 MusicXML 渲染成 SVG。输出约定:
  * 每页独立 SVG:`<stem>-pN.svg`(N = 1..page_count),可在浏览器直接查看
  * 总 SVG:`<out_svg>` 本体 —— 各页竖排(translate)合并的一张长图
  * 总 PNG:`--out-png` —— 各页经 cairosvg 转 PNG 后竖排拼接的白底长图

用法:
  python3 render_score.py --musicxml ../samples/test_score.musicxml \
      --out-svg ../samples/test_score.svg [--out-png ../samples/test_score.png]
"""
from __future__ import annotations

import argparse
import io
import os
import re

import verovio

DEFAULT_OPTS = {
    "pageWidth": 2100,
    "pageHeight": 2970,
    "scale": 65,
    "font": "Leland",
    "justifyVertically": True,
    "spacingSystem": 6,
    "breaks": "auto",
}
PNG_WIDTH = 1400  # cairosvg 转换宽度(高度按页面比例)


def _strip_outer_svg(s: str) -> str:
    """去掉最外层 <svg ...> / </svg> 标签(保留内部嵌套结构),便于嵌入 <g>。"""
    s = re.sub(r"^<\?xml[^>]*\?>\s*", "", s)
    s = re.sub(r"^\s*<svg[^>]*>", "", s, count=1)
    s = re.sub(r"</svg>\s*$", "", s, count=1)
    return s


def render(musicxml_path: str, out_svg: str, out_png: str | None = None,
           options: dict | None = None) -> int:
    data_dir = os.path.join(os.path.dirname(verovio.__file__), "data")
    tk = verovio.toolkit(False)
    if os.path.isdir(data_dir):
        tk.setResourcePath(data_dir)
    if not tk.loadFile(musicxml_path):
        raise RuntimeError(f"Verovio 无法加载: {musicxml_path}")

    opts = dict(DEFAULT_OPTS)
    if options:
        opts.update(options)
    tk.setOptions(opts)

    page_count = tk.getPageCount()
    pages = [tk.renderToSVG(p) for p in range(1, page_count + 1)]

    # 每页独立 SVG(浏览器可单页查看)
    stem, ext = os.path.splitext(out_svg)
    for i, s in enumerate(pages, 1):
        with open(f"{stem}-p{i}{ext}", "w", encoding="utf-8") as f:
            f.write(s)

    # 总 SVG:各页竖排合并为一张长图(坐标连续,浏览器可直接滚动查看)
    page_h = opts["pageHeight"]
    combined = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{opts["pageWidth"]}" '
        f'height="{page_h * page_count}" viewBox="0 0 {opts["pageWidth"]} {page_h * page_count}">\n'
    )
    for i, s in enumerate(pages):
        inner = _strip_outer_svg(s)
        combined += f'<g transform="translate(0,{i * page_h})">\n{inner}\n</g>\n'
    combined += "</svg>\n"
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write(combined)

    # 总 PNG:逐页 cairosvg 转换,白底竖排拼接
    if out_png:
        import cairosvg
        from PIL import Image
        imgs = []
        for s in pages:
            png = cairosvg.svg2png(bytestring=s.encode("utf-8"),
                                   output_width=PNG_WIDTH)
            imgs.append(Image.open(io.BytesIO(png)).convert("RGBA"))
        w = max(im.size[0] for im in imgs)
        total_h = sum(im.size[1] for im in imgs)
        canvas = Image.new("RGB", (w, total_h), "white")
        y = 0
        for im in imgs:
            # 透明背景合成到白底
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            canvas.paste(Image.alpha_composite(bg, im).convert("RGB"), (0, y))
            y += im.size[1]
        canvas.save(out_png, "PNG")

    print(f"渲染完成: {page_count} 页 -> 独立 SVG({stem}-p1..p{page_count}{ext})"
          f" + 总 SVG({out_svg})" + (f" + 总 PNG({out_png})" if out_png else ""))
    return page_count


def main():
    ap = argparse.ArgumentParser(description="MusicXML → SVG/PNG 渲染")
    ap.add_argument("--musicxml", required=True)
    ap.add_argument("--out-svg", required=True)
    ap.add_argument("--out-png")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out_svg)) or ".", exist_ok=True)
    render(args.musicxml, args.out_svg, args.out_png)


if __name__ == "__main__":
    main()
