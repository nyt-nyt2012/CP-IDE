"""Python 脚本的语法检查与运行命令。

「编译」对 Python 来说就是语法检查：通过 ``compile()`` 找出语法错误并给出
行号列号，界面上的诊断列表因此和 C++ 的编译错误一样可以点击跳转。
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

from .paths import FROZEN


def interpreter(custom: str = "") -> str:
    """用来运行用户 Python 脚本的解释器。

    优先级：请求里指定的路径 > 环境变量 ``CPIDE_PYTHON`` > 当前解释器。
    """
    if custom and os.path.isfile(custom):
        return custom
    env = os.environ.get("CPIDE_PYTHON")
    if env and os.path.isfile(env):
        return env
    return sys.executable


def script_command(script_path: str, custom: str = "") -> List[str]:
    """运行脚本的命令行。

    打包成 exe 之后 ``sys.executable`` 就是 exe 自己，这时要用一个特殊参数
    让它把脚本当成普通程序跑起来（见 desktop.py 的 ``--cpide-run`` 分支）。
    """
    exe = interpreter(custom)
    if FROZEN:
        return [exe, "--cpide-run", script_path]
    return [exe, script_path]


def write_script(code: str, directory: str, filename: str = "main.py") -> str:
    """把代码写成脚本文件，返回脚本路径。"""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(code)
    return path


def check_syntax(code: str, filename: str = "main.py") -> Dict:
    """语法检查，返回 ``{ok, diagnostics, message}``。"""
    try:
        compile(code, filename, "exec")
    except SyntaxError as exc:
        line = exc.lineno or 1
        col = exc.offset or 1
        message = exc.msg or str(exc)
        return {
            "ok": False,
            "diagnostics": [
                {
                    "severity": "error",
                    "line": line,
                    "col": col,
                    "message": message,
                    "file": filename,
                }
            ],
            "message": "语法错误：第 %d 行 %s" % (line, message),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "diagnostics": [],
            "message": "无法解析代码：%s" % exc,
        }
    return {"ok": True, "diagnostics": [], "message": "语法检查通过"}


def run_script_file(path: str, extra_args: Optional[List[str]] = None) -> int:
    """把脚本当作主程序运行，返回退出码。

    打包成 exe 之后，用户脚本是通过 ``CP-IDE.exe --cpide-run 脚本.py``
    启动的：同一个可执行文件既当 IDE 又当 Python 解释器。
    """
    import runpy

    # 窗口模式下标准句柄可能无效，补一个可写流，避免脚本里的 print 崩溃
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    sys.argv = [path] + list(extra_args or [])
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    return 0
