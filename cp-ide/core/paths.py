"""运行路径解析：同时兼容「源码直接运行」与「PyInstaller 打包成单文件 exe」。

打包之后有三类路径：

``resource_dir()``
    只读资源（页面模板、样式脚本、testlib、示例数据）。打包后位于
    PyInstaller 解包出来的临时目录 ``sys._MEIPASS``。
``data_dir()``
    需要写入的目录（用户自建代码片段）。打包后放在
    ``%LOCALAPPDATA%\\CP-IDE``，不写进 exe 旁边，避免只读或权限问题。
``exe_dir()``
    exe 所在目录，找编译器（winlibs）时用。
"""

from __future__ import annotations

import os
import sys

#: 是否运行在 PyInstaller 打包出来的 exe 里
FROZEN = bool(getattr(sys, "frozen", False))


def resource_dir() -> str:
    """只读资源所在目录。"""
    if FROZEN:
        return getattr(sys, "_MEIPASS", "") or os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """可写数据目录。"""
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "CP-IDE")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exe_dir() -> str:
    """可执行文件所在目录。"""
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure_dir(path: str) -> str:
    """确保目录存在，返回该目录。"""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path
