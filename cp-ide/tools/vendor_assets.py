"""把 Markdown / LaTeX / PDF 渲染所需的前端库下载到本地（一次性，之后完全离线）。

下载来源是 unpkg（npm 包镜像）。脚本会把 KaTeX 的字体裁剪成只保留 woff2
并同步改写 CSS，避免浏览器去请求一堆用不到的 woff / ttf。

用法::

    python tools/vendor_assets.py
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.request

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_DIR = os.path.join(APP_DIR, "static", "vendor")
UNPKG = "https://unpkg.com"

FILES = [
    # (url, 目标相对路径)
    ("marked@12.0.2/marked.min.js", "marked/marked.min.js"),
    ("katex@0.16.11/dist/katex.min.js", "katex/katex.min.js"),
    ("katex@0.16.11/dist/katex.min.css", "katex/katex.min.css"),
    ("katex@0.16.11/dist/contrib/auto-render.min.js", "katex/auto-render.min.js"),
    ("pdfjs-dist@3.11.174/build/pdf.min.js", "pdfjs/pdf.min.js"),
    ("pdfjs-dist@3.11.174/build/pdf.worker.min.js", "pdfjs/pdf.worker.min.js"),
]

# CodeMirror 5 的语法模式不在 npm 包里（只有 GitHub 仓库有），
# 这里从 cdnjs 取，unpkg 作为备选。
CODE_MIRRORS = (
    "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/%s",
    "https://unpkg.com/codemirror@5.65.16/mode/%s",
)

CODE_MODES = [
    ("python/python.min.js", "codemirror/mode/python/python.min.js"),
    ("markdown/markdown.min.js", "codemirror/mode/markdown/markdown.min.js"),
    ("xml/xml.min.js", "codemirror/mode/xml/xml.min.js"),
    ("gfm/gfm.min.js", "codemirror/mode/gfm/gfm.min.js"),
]

FONT_BASE = "katex@0.16.11/dist/fonts/"


def download(url: str, target: str, retries: int = 4) -> int:
    """下载一个文件，失败时重试（CDN 偶尔会抽风）。"""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "cp-ide-vendor/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            with open(target, "wb") as fh:
                fh.write(data)
            return len(data)
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise last_error if last_error else RuntimeError("下载失败")


def vendor_fonts(css_path: str) -> int:
    """把 CSS 里引用的 woff2 字体下载下来，并把 src 精简成只保留 woff2。"""
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()

    names = sorted(set(re.findall(r"fonts/([A-Za-z0-9_\-]+\.woff2)", css)))
    font_dir = os.path.join(VENDOR_DIR, "katex", "fonts")
    os.makedirs(font_dir, exist_ok=True)

    total = 0
    for name in names:
        target = os.path.join(font_dir, name)
        if os.path.isfile(target):
            continue
        try:
            total += download(UNPKG + "/" + FONT_BASE + name, target)
        except Exception as exc:
            print("  ! 字体下载失败 %s：%s" % (name, exc))

    # src 里去掉 woff / ttf 的备选，只留 woff2
    css = re.sub(
        r",url\(fonts/[^)]+\.(?:woff|ttf)\)\s*format\(\"(?:woff|truetype)\"\)",
        "",
        css,
    )
    with open(css_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(css)
    return total


def download_code_mode(relative: str, target: str) -> int:
    """CodeMirror 的语法模式：依次尝试各个镜像。"""
    last_error = None
    for template in CODE_MIRRORS:
        url = template % relative
        try:
            return download(url, target)
        except Exception as exc:
            last_error = exc
    raise last_error if last_error else RuntimeError("下载失败")


def main() -> int:
    print("下载前端渲染库到 %s" % VENDOR_DIR)
    for url, rel in FILES:
        target = os.path.join(VENDOR_DIR, rel)
        try:
            size = download(UNPKG + "/" + url, target)
            print("  ok  %-46s %8d B" % (rel, size))
        except Exception as exc:
            print("  !!  %-46s 失败：%s" % (rel, exc))
            return 1

    for relative, rel in CODE_MODES:
        target = os.path.join(VENDOR_DIR, rel)
        try:
            size = download_code_mode(relative, target)
            print("  ok  %-46s %8d B" % (rel, size))
        except Exception as exc:
            print("  !!  %-46s 失败：%s" % (rel, exc))
            return 1

    css_path = os.path.join(VENDOR_DIR, "katex", "katex.min.css")
    total = vendor_fonts(css_path)
    print("  ok  katex 字体                        %8d B" % total)
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
