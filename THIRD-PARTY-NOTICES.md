# 第三方组件与开源许可声明

CP-IDE 是一个**完全离线**的本地 C++ / Python 竞赛编程 IDE 与评测机，
最终交付形态是单个 `CP-IDE.exe`。这个 exe 里打包了不少别人的代码，
本文件把它们逐一登记在册，说明**名称、版本、许可证、版权归谁、许可证全文在哪**，
以保证这份 exe 的分发是合规的。

- 本项目自身的许可证：见仓库根目录的 [`LICENSE`](LICENSE)（MIT）。
- 所有随 exe 分发的许可证全文：见 [`cp-ide/static/licenses/`](cp-ide/static/licenses/)，
  这些文件**会被打包进 exe**，用户也可以在 **设置 → 外观 → 关于 → 开源许可**里点开查看。
- 界面里显示的清单与本文件同源（后端 `cp-ide/core/licenses.py`）。

---

## 一、随 exe 一起分发的第三方组件

| 组件 | 版本 | 许可证 | 版权 | 用途 | 许可证全文 |
| --- | --- | --- | --- | --- | --- |
| CodeMirror | 5.65.16 | MIT | Marijn Haverbeke and others | 编辑器内核：语法高亮、查找替换、括号补全、注释切换 | `codemirror-LICENSE.txt` |
| KaTeX | 0.16.11 | MIT | Khan Academy and other contributors | Markdown 预览里的 LaTeX 公式渲染（代码与字体） | `katex-LICENSE.txt` |
| marked | 12.0.2 | MIT | Christopher Jeffrey | Markdown 解析 | `marked-LICENSE.txt` |
| PDF.js | 3.11.174 | Apache-2.0 | Mozilla Foundation | 内置 PDF 阅读器 | `pdfjs-LICENSE.txt` + `pdfjs-NOTICE.txt` |
| testlib | 0.9.45 | testlib 自带的宽松许可 | Mike Mirzayanov | 内置 `testlib.h`：自定义 Checker、测试点生成 | `testlib-LICENSE.txt` |
| Python | 3.14 | PSF-2.0 | Python Software Foundation | 打包进 exe 的解释器运行时 | `python-LICENSE.txt` |
| Flask | 3.1.3 | BSD-3-Clause | Pallets | 本地 HTTP 服务 | `flask-LICENSE.txt` |
| Werkzeug | 3.1.9 | BSD-3-Clause | Pallets | Flask 的 WSGI 工具库 | `werkzeug-LICENSE.txt` |
| Jinja2 | 3.1.6 | BSD-3-Clause | Pallets | 页面模板渲染 | `jinja2-LICENSE.txt` |
| MarkupSafe | 3.0.4 | BSD-3-Clause | Pallets | Jinja2 的转义工具 | `markupsafe-LICENSE.txt` |
| Click | 8.5.0 | BSD-3-Clause | Pallets | 命令行参数解析 | `click-LICENSE.txt` |
| Blinker | 1.9.0 | MIT | Pallets | Flask 的信号机制 | `blinker-LICENSE.txt` |
| itsdangerous | 2.2.0 | BSD-3-Clause | Pallets | Flask 的签名与数据保护 | `itsdangerous-LICENSE.txt` |
| pywebview | 6.2.1 | BSD-3-Clause | Ranchive Team and contributors | 桌面版窗口（内嵌 Edge / WebView2） | `pywebview-LICENSE.txt` |
| PyInstaller | 6.22.3 | GPL-2.0-or-later（**引导器带 PyInstaller 例外条款**，允许与任意程序一同分发） | PyInstaller Development Team | 把 Python 程序打包成单文件 exe 的引导器 | `pyinstaller-COPYING.txt` |

> MIT / BSD-3-Clause / PSF 组件都要求「随分发附带版权声明与许可声明」，
> Apache-2.0 额外要求「随分发附带 NOTICE 并注明修改」——
> 上表中的 `static/licenses/` 就是为此准备的，它们已经打进 exe 里。

## 二、运行期用到、但**不随 exe 分发**的组件

| 组件 | 版本 | 许可证 | 说明 |
| --- | --- | --- | --- |
| MinGW-w64 g++（winlibs） | 15.2.0 | GPL-3.0-or-later + GCC Runtime Library Exception | 编译用户提交的 C++ 代码。用户自行解压放置，exe 只**调用**它，不把它打包进来 |
| CP Editor | — | GPL-3.0-or-later（Copyright © 2019-2021 Ashar Khan） | **仅作为设计参考阅读**，详见下一节 |

## 三、关于参考项目 CP Editor 的说明

CP-IDE 在设计阶段参考了 **CP Editor**（<https://github.com/cpeditor/cpeditor>，
Copyright © 2019-2021 Ashar Khan）的 `src/Core/` 下的
`Checker.cpp` / `Compiler.cpp` / `Runner.cpp` 等文件，了解竞赛评测机的
整体流程与 Checker 约定。

CP Editor 采用 **GPL-3.0-or-later** 授权。为避免把 GPL 代码引入本项目：

- CP-IDE 的后端是**用 Python 独立重写**的（`cp-ide/core/checker.py`、
  `cp-ide/core/runner.py`、`cp-ide/core/toolchain.py` 等），
  **没有复制、改写或翻译** CP Editor 的 GPL 源码；
- CP Editor 的源码只保存在本机 `_ref/` 目录（已被 `.gitignore` 排除），
  **不随 exe、也不随本仓库分发**；
- 因此 CP-IDE 可以采用宽松许可证（MIT）发布。
  若日后需要直接引用或移植 CP Editor 的代码，则必须同时把 CP-IDE
  改为 GPL-3.0-or-later，并附上 CP Editor 的版权声明与许可证全文。

## 四、字体与图标

- 界面字体使用系统已安装的字体（Consolas、JetBrains Mono、Cascadia Code 等），
  **不随 exe 分发字体文件**；
- 图标使用 Unicode 字符与少量内联 SVG，**不引入第三方图标库**。

## 五、修改声明

CP-IDE 未对上述任何第三方组件的源码做修改（vendor 目录里的文件为上游原样拷贝）。
若后续修改了某个 vendored 文件，请在对应 `LICENSE` 文件中注明修改内容。
