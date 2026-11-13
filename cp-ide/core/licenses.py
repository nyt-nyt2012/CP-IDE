"""第三方组件的许可清单。

CP-IDE 是一个「单文件 exe」，里面打包了不少别人的代码。为了让这份
exe 的分发是合规的，这里把每一个随 exe 一起分发的组件登记在册：

* 组件叫什么、什么版本、什么许可证、版权归谁；
* 它的许可证全文放在 ``static/licenses/`` 下，**会一起打进 exe**，
  用户在「设置 → 关于 → 开源许可」里可以直接点开查看。

``EXTERNAL`` 里的组件不随 exe 分发（只是运行期用到），单独列出来，
免得让人误以为 exe 里带了编译器。
"""

from __future__ import annotations

import io
import os
from typing import Dict, List, Optional

from .paths import resource_dir
from .version import VERSION

#: 许可证全文所在目录（会随 exe 一起打包）
LICENSE_DIR = os.path.join(resource_dir(), "static", "licenses")

#: 随 exe 一起分发的第三方组件
COMPONENTS: List[Dict[str, str]] = [
    {
        "name": "CodeMirror",
        "version": "5.65.16",
        "license": "MIT",
        "holder": "Marijn Haverbeke and others",
        "usage": "代码编辑器内核：语法高亮、查找替换、括号补全、注释切换",
        "url": "https://codemirror.net/5/",
        "file": "codemirror-LICENSE.txt",
    },
    {
        "name": "KaTeX",
        "version": "0.16.11",
        "license": "MIT",
        "holder": "Khan Academy and other contributors",
        "usage": "Markdown 预览里的 LaTeX 公式渲染（代码与字体）",
        "url": "https://katex.org/",
        "file": "katex-LICENSE.txt",
    },
    {
        "name": "marked",
        "version": "12.0.2",
        "license": "MIT",
        "holder": "Christopher Jeffrey",
        "usage": "Markdown 解析",
        "url": "https://marked.js.org/",
        "file": "marked-LICENSE.txt",
    },
    {
        "name": "PDF.js",
        "version": "3.11.174",
        "license": "Apache-2.0",
        "holder": "Mozilla Foundation",
        "usage": "内置 PDF 阅读器",
        "url": "https://mozilla.github.io/pdf.js/",
        "file": "pdfjs-LICENSE.txt",
        "notice": "pdfjs-NOTICE.txt",
    },
    {
        "name": "testlib",
        "version": "0.9.45",
        "license": "testlib 自带的宽松许可",
        "holder": "Mike Mirzayanov",
        "usage": "内置 testlib.h：自定义 Checker、测试点生成",
        "url": "https://github.com/MikeMirzayanov/testlib",
        "file": "testlib-LICENSE.txt",
    },
    {
        "name": "Python",
        "version": "3.14",
        "license": "PSF-2.0",
        "holder": "Python Software Foundation",
        "usage": "打包进 exe 的解释器运行时",
        "url": "https://www.python.org/",
        "file": "python-LICENSE.txt",
    },
    {
        "name": "Flask",
        "version": "3.1.3",
        "license": "BSD-3-Clause",
        "holder": "Pallets",
        "usage": "本地 HTTP 服务",
        "url": "https://flask.palletsprojects.com/",
        "file": "flask-LICENSE.txt",
    },
    {
        "name": "Werkzeug",
        "version": "3.1.9",
        "license": "BSD-3-Clause",
        "holder": "Pallets",
        "usage": "Flask 的 WSGI 工具库",
        "url": "https://werkzeug.palletsprojects.com/",
        "file": "werkzeug-LICENSE.txt",
    },
    {
        "name": "Jinja2",
        "version": "3.1.6",
        "license": "BSD-3-Clause",
        "holder": "Pallets",
        "usage": "页面模板渲染",
        "url": "https://jinja.palletsprojects.com/",
        "file": "jinja2-LICENSE.txt",
    },
    {
        "name": "MarkupSafe",
        "version": "3.0.4",
        "license": "BSD-3-Clause",
        "holder": "Pallets",
        "usage": "Jinja2 的转义工具",
        "url": "https://markupsafe.palletsprojects.com/",
        "file": "markupsafe-LICENSE.txt",
    },
    {
        "name": "Click",
        "version": "8.5.0",
        "license": "BSD-3-Clause",
        "holder": "Pallets",
        "usage": "命令行参数解析",
        "url": "https://click.palletsprojects.com/",
        "file": "click-LICENSE.txt",
    },
    {
        "name": "Blinker",
        "version": "1.9.0",
        "license": "MIT",
        "holder": "Pallets",
        "usage": "Flask 的信号机制",
        "url": "https://blinker.palletsprojects.com/",
        "file": "blinker-LICENSE.txt",
    },
    {
        "name": "itsdangerous",
        "version": "2.2.0",
        "license": "BSD-3-Clause",
        "holder": "Pallets",
        "usage": "Flask 的签名与数据保护",
        "url": "https://itsdangerous.palletsprojects.com/",
        "file": "itsdangerous-LICENSE.txt",
    },
    {
        "name": "pywebview",
        "version": "6.2.1",
        "license": "BSD-3-Clause",
        "holder": "Ranchive Team and contributors",
        "usage": "桌面版窗口（内嵌 Edge / WebView2）",
        "url": "https://pywebview.flowrl.com/",
        "file": "pywebview-LICENSE.txt",
    },
    {
        "name": "PyInstaller",
        "version": "6.22.3",
        "license": "GPL-2.0-or-later（引导器带 PyInstaller 例外条款）",
        "holder": "PyInstaller Development Team",
        "usage": "把 Python 程序打包成单文件 exe 的引导器",
        "url": "https://pyinstaller.org/",
        "file": "pyinstaller-COPYING.txt",
    },
]

#: 运行期用到、但**不**随 exe 分发的组件
EXTERNAL: List[Dict[str, str]] = [
    {
        "name": "MinGW-w64 g++（winlibs）",
        "version": "15.2.0",
        "license": "GPL-3.0-or-later + GCC Runtime Library Exception",
        "holder": "GCC contributors / winlibs",
        "usage": "编译用户提交的 C++ 代码（用户自行解压放置，exe 只调用它）",
        "url": "https://winlibs.com/",
    },
    {
        "name": "CP Editor（参考项目）",
        "version": "—",
        "license": "GPL-3.0-or-later",
        "holder": "Ashar Khan",
        "usage": "仅作为设计参考阅读；CP-IDE 未复制其 GPL 源码，代码为独立实现",
        "url": "https://github.com/cpeditor/cpeditor",
    },
]


def self_entry() -> Dict[str, str]:
    """CP-IDE 自己的许可信息。"""
    return {
        "name": "CP-IDE",
        "version": VERSION,
        "license": "MIT",
        "holder": "nyt-nyt2012（CP-IDE 项目作者）",
        "usage": "本项目自身的源代码",
        "url": "https://github.com/nyt-nyt2012/CP-IDE",
        "file": "cpide-LICENSE.txt",
    }


def manifest() -> Dict[str, object]:
    """给前端的完整清单。"""
    return {
        "self": self_entry(),
        "components": COMPONENTS,
        "external": EXTERNAL,
        "license_dir": "static/licenses",
    }


def read_license(filename: str) -> Optional[str]:
    """读某个许可证文件的全文；文件名非法或文件不存在时返回 None。"""
    if not filename:
        return None
    # 只允许纯文件名，杜绝 ../ 之类的路径穿越
    safe = os.path.basename(filename)
    if safe != filename or not safe.lower().endswith((".txt", ".md")):
        return None
    path = os.path.join(LICENSE_DIR, safe)
    if not os.path.isfile(path):
        return None
    try:
        with io.open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None
