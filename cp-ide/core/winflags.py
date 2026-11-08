"""Windows 下启动子进程时的窗口标志。

打包后的 CP-IDE 是 GUI 程序（没有自己的控制台）。如果直接启动
g++.exe、用户编译出来的 exe 或 checker 这些「控制台程序」，
Windows 会给它们新开一个控制台窗口——于是编译时就会闪出一个黑框。

做法：**保留控制台，但把窗口隐藏**（STARTF_USESHOWWINDOW + SW_HIDE）。

⚠️ 这里**不能**用 ``CREATE_NO_WINDOW``：g++ 还会继续派生子进程
(cc1plus / as / ld)，一旦 g++ 自己没有控制台，这些子进程就会各自
新建一个**可见**的控制台窗口，黑框照样会闪出来。
保留控制台并隐藏窗口，子孙进程继承这个隐藏的控制台，才彻底没有黑框。
"""

from __future__ import annotations

import os
import subprocess

#: CREATE_NO_WINDOW 的数值（部分 Python 版本没有这个常量）
CREATE_NO_WINDOW = 0x08000000


def creation_flags(no_window: bool = False) -> int:
    """启动子进程时使用的 creationflags。

    * **编译器**（g++ 及其 cc1plus / as / ld 子孙）：只加
      CREATE_NEW_PROCESS_GROUP（方便按进程组结束），
      **不要**加 CREATE_NO_WINDOW，理由见模块说明；
    * **运行用户程序 / checker / 脚本**：加 CREATE_NO_WINDOW ——
      它们不需要控制台，直接不给分配，就彻底不会出现黑色控制台窗口
      （只靠 SW_HIDE 的话窗口仍可能先闪一下再消失）。

    两种情况都同时带 SW_HIDE 的 STARTUPINFO，双保险。
    """
    if os.name != "nt":
        return 0
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if no_window:
        flags |= CREATE_NO_WINDOW
    return flags


def startup_info():
    """让子进程（以及它的子孙进程）的控制台窗口保持隐藏。"""
    if os.name != "nt":
        return None
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        return info
    except Exception:  # pragma: no cover - 防御
        return None
